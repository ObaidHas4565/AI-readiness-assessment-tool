"""
Export service

Turns a finished AssessmentResults into something the company can take away:
a PDF report to read, or an Excel workbook to dig into.

Everything here works in memory and returns bytes. That's deliberate -- the
dashboard hands those bytes straight to a download button, and nothing ever
touches the server's disk, which is what keeps the no-database, nothing-stored
design intact. The write_pdf/write_excel helpers exist for testing and for
running from the command line.

Note on what goes in the file: the export carries the company's answers and
scores but no company name, contact details or anything else identifying,
because CompanyProfile never collects those in the first place.
"""

from __future__ import annotations

import io
import math
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.chart import BarChart, RadarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, String
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import score_configuration as cfg
from .assessment_results import AssessmentResults, FactorScore, ItemScore


# ---------------------------------------------------------------------------
# Shared look-up tables
# ---------------------------------------------------------------------------
# One place for the colours so the PDF and the spreadsheet agree with each
# other. If a band colour changes it changes in both.

BAND_COLOURS: Dict[str, str] = {
    "Emerging": "C0392B",    # red
    "Developing": "D68910",  # amber
    "Advanced": "1E8449",    # green
}

SEVERITY_COLOURS: Dict[str, str] = {
    "critical": "C0392B",
    "moderate": "D68910",
    "refine": "2874A6",
}

SEVERITY_LABELS: Dict[str, str] = {
    "critical": "Critical",
    "moderate": "Moderate",
    "refine": "Refine",
}

# Nicer headings than the raw field names for the context block.
# Full factor names don't fit round a radar, so each gets a one-word label.
SHORT_FACTOR_LABELS: Dict[str, str] = {
    "budget": "Budget", "workforce": "Workforce", "leadership": "Leadership",
    "data": "Data", "technology": "Technology", "culture": "Culture",
    "governance": "Governance",
}

CONTEXT_LABELS: Dict[str, str] = {
    "industry_sector": "Industry sector",
    "employee_band": "Company size",
    "years_in_operation": "Years in operation",
    "region": "Region",
    "current_ai_stage": "Current AI adoption stage",
}

# Excel mangles "1-9" and "10-49" into dates when the sheet is opened, the same
# way it does with a CSV. The workbook writes these spelled-out forms instead.
EXCEL_SAFE_SIZES: Dict[str, str] = {
    "1-9": "1 to 9 employees",
    "10-49": "10 to 49 employees",
    "50-249": "50 to 249 employees",
    "250+": "250+ employees",
}


def _safe_size(value: Optional[str]) -> Optional[str]:
    return EXCEL_SAFE_SIZES.get(str(value), value)


def _timestamp() -> str:
    return datetime.now().strftime("%d %B %Y, %H:%M")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=20, spaceAfter=2, leading=24,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontSize=9.5,
            textColor=colors.HexColor("#666666"), spaceAfter=14,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=13, spaceBefore=16,
            spaceAfter=7, textColor=colors.HexColor("#1A1A1A"),
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontSize=9.5, leading=13.5,
            alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"], fontSize=8.5, leading=11.5,
            textColor=colors.HexColor("#555555"),
        ),
        "rec_title": ParagraphStyle(
            "rec_title", parent=base["Normal"], fontSize=10, leading=13,
            fontName="Helvetica-Bold",
        ),
    }


def _score_bar(score: float, width: float, colour: str) -> Table:
    """
    A horizontal bar drawn as a two-cell table.

    Using a table rather than reportlab's chart classes keeps it simple and it
    flows with the rest of the document instead of needing absolute placement.
    """
    filled = max(0.0, min(1.0, score / 100.0)) * width
    empty = width - filled

    # A zero-width column still draws a hairline, so drop the empty cell when
    # the score is full, and the filled cell when it's zero.
    if filled <= 0.01:
        widths, cells = [width], [[""]]
        style = [("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#E8E8E8"))]
    elif empty <= 0.01:
        widths, cells = [width], [[""]]
        style = [("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#" + colour))]
    else:
        widths, cells = [filled, empty], [["", ""]]
        style = [
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#" + colour)),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#E8E8E8")),
        ]

    bar = Table(cells, colWidths=widths, rowHeights=[5 * mm])
    bar.setStyle(TableStyle(style + [
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return bar


def _radar_drawing(scores: List[Tuple[str, float]], colour: str,
                   size: float = 175.0) -> Drawing:
    """
    The profile shape, drawn for the PDF.

    The bar chart ranks the factors; this shows whether readiness is even or
    lopsided, which is a different question and the one people tend to ask
    first when they see the report. The dashboard shows it, so the report
    people take away should show it too.
    """
    drawing = Drawing(size, size)
    centre = size / 2.0
    radius = size * 0.32
    count = len(scores)

    def point(index: int, value: float) -> Tuple[float, float]:
        # Clockwise from the top. reportlab's y axis points up where the
        # dashboard's SVG points down, so the sign is flipped here to keep
        # the report and the screen showing the same shape the same way round.
        angle = (math.pi / 2) - (2 * math.pi * index / count)
        distance = radius * max(0.0, min(100.0, value)) / 100.0
        return (centre + distance * math.cos(angle),
                centre + distance * math.sin(angle))

    for fraction in (0.25, 0.5, 0.75, 1.0):
        drawing.add(Circle(centre, centre, radius * fraction,
                           fillColor=None,
                           strokeColor=colors.HexColor("#E4E4E4"),
                           strokeWidth=0.5))

    for index, (name, _) in enumerate(scores):
        end_x, end_y = point(index, 100)
        drawing.add(Line(centre, centre, end_x, end_y,
                         strokeColor=colors.HexColor("#E4E4E4"), strokeWidth=0.5))

        label_x, label_y = point(index, 133)
        label = String(label_x, label_y - 2, name, fontSize=6.2,
                       fillColor=colors.HexColor("#666666"))
        if label_x < centre - 6:
            label.textAnchor = "end"
        elif label_x > centre + 6:
            label.textAnchor = "start"
        else:
            label.textAnchor = "middle"
        drawing.add(label)

    outline: List[float] = []
    for index, (_, value) in enumerate(scores):
        x, y = point(index, value)
        outline.extend([x, y])

    drawing.add(Polygon(outline,
                        fillColor=colors.HexColor("#" + colour),
                        fillOpacity=0.22,
                        strokeColor=colors.HexColor("#" + colour),
                        strokeWidth=1.4))
    return drawing


def to_pdf_bytes(results: AssessmentResults) -> bytes:
    """Build the PDF report and return it as bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="AI Adoption Readiness Assessment",
        author="AI Adoption Readiness Assessment Tool",
    )

    s = _styles()
    content_width = doc.width
    story: List = []

    # --- header -----------------------------------------------------------
    story.append(Paragraph("AI Adoption Readiness Assessment", s["title"]))
    story.append(Paragraph(f"Generated {_timestamp()}", s["subtitle"]))

    # --- headline score ---------------------------------------------------
    band_colour = BAND_COLOURS.get(results.readiness_tier, "555555")
    headline = Table(
        [[
            Paragraph(
                f'<font size="30"><b>{results.overall_score:.1f}</b></font>'
                f'<font size="12" color="#777777">/100</font>',
                s["body"],
            ),
            Paragraph(
                f'<font size="15" color="#{band_colour}"><b>'
                f'{escape(results.readiness_tier)}</b></font><br/><br/>'
                f'{escape(results.tier_description)}',
                s["body"],
            ),
        ]],
        colWidths=[38 * mm, content_width - 38 * mm],
    )
    headline.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F7F7")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("LINEBEFORE", (0, 0), (0, 0), 3, colors.HexColor("#" + band_colour)),
    ]))
    story.append(headline)

    # --- company context --------------------------------------------------
    context_pairs: List[str] = []
    for field, label in CONTEXT_LABELS.items():
        value = results.context.get(field)
        if value:
            shown = _safe_size(value) if field == "employee_band" else value
            context_pairs.append(f"<b>{escape(label)}:</b> {escape(str(shown))}")
    if context_pairs:
        story.append(Spacer(1, 7))
        story.append(Paragraph("&nbsp;&nbsp;|&nbsp;&nbsp;".join(context_pairs), s["small"]))

    # --- factor scores ----------------------------------------------------
    story.append(Paragraph("Readiness by factor", s["h2"]))

    label_w = 62 * mm
    score_w = 16 * mm
    band_w = 22 * mm
    bar_w = content_width - label_w - score_w - band_w

    rows: List[List] = []
    for factor in results.ordered_factors():
        colour = BAND_COLOURS.get(factor.band_label, "555555")
        rows.append([
            Paragraph(escape(factor.name), s["body"]),
            Paragraph(f"<b>{factor.score:.1f}</b>", s["body"]),
            _score_bar(factor.score, bar_w - 4 * mm, colour),
            Paragraph(
                f'<font color="#{colour}">{escape(factor.band_label)}</font>',
                s["small"],
            ),
        ])

    factor_table = Table(rows, colWidths=[label_w, score_w, bar_w, band_w])
    factor_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#EAEAEA")),
    ]))
    story.append(factor_table)

    # --- profile shape ----------------------------------------------------
    ordered = results.ordered_factors()
    shape = _radar_drawing(
        [(SHORT_FACTOR_LABELS.get(f.factor_id, f.name), f.score) for f in ordered],
        band_colour,
    )
    shape_row = Table(
        [[shape, Paragraph(
            "<b>Profile shape</b><br/><br/>"
            "An even shape means readiness is spread across the seven areas. "
            "A lopsided one means some areas are far ahead of others, which "
            "usually matters more than the overall number: adoption tends to "
            "be held back by the weakest area rather than helped by the "
            "strongest.",
            s["small"])]],
        colWidths=[76 * mm, content_width - 76 * mm],
    )
    shape_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
    ]))
    story.append(Spacer(1, 6))
    story.append(shape_row)

    # --- strengths and barriers ------------------------------------------
    if results.strengths:
        story.append(Paragraph("Strengths", s["h2"]))
        for factor in results.strengths:
            story.append(Paragraph(
                f"<b>{escape(factor.name)}</b> &mdash; {factor.score:.0f}/100",
                s["body"],
            ))

    if results.barriers:
        story.append(Paragraph("Main barriers", s["h2"]))
        for factor in results.barriers:
            story.append(Paragraph(
                f"<b>{escape(factor.name)}</b> &mdash; {factor.score:.0f}/100",
                s["body"],
            ))

    if results.item_barriers:
        story.append(Paragraph("Specific gaps", s["h2"]))
        gap_rows = []
        for item in results.item_barriers:
            # Reverse-worded questions describe a problem, so agreeing with one
            # is what produces the low score. Without saying so, the statement
            # and the score next to it look like they contradict each other.
            note = (
                ' <i><font color="#888888">(barrier statement &mdash; agreeing '
                'lowers readiness)</font></i>'
                if item.reverse else ""
            )
            gap_rows.append([
                Paragraph(f"<b>{escape(item.item_id)}</b>", s["small"]),
                Paragraph(escape(item.text) + note, s["small"]),
                Paragraph(f"{item.score:.0f}/100", s["small"]),
            ])

        gap_table = Table(gap_rows, colWidths=[18 * mm, content_width - 40 * mm, 22 * mm])
        gap_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(gap_table)

    # --- recommendations --------------------------------------------------
    story.append(Paragraph("Recommended actions", s["h2"]))

    if not results.recommendations:
        story.append(Paragraph(
            "No actions are flagged. Every factor scored at or above the "
            "Advanced threshold.",
            s["body"],
        ))
    else:
        story.append(Paragraph(
            "Listed in priority order. Priority reflects how much closing each "
            "gap would move the overall readiness score.",
            s["small"],
        ))
        story.append(Spacer(1, 8))

        for index, rec in enumerate(results.recommendations, start=1):
            colour = SEVERITY_COLOURS.get(rec.severity, "555555")
            label = SEVERITY_LABELS.get(rec.severity, rec.severity.title())
            source = rec.factor_name
            if rec.triggered_by_item:
                source += f" &middot; {escape(rec.triggered_by_item)}"

            block = Table(
                [[Paragraph(
                    f'<font color="#{colour}"><b>{index}. {escape(label)}</b></font>'
                    f'&nbsp;&nbsp;<font color="#777777" size="8">{source}</font><br/>'
                    f'<b>{escape(rec.title)}</b><br/>'
                    f'{escape(rec.action)}',
                    s["body"],
                )]],
                colWidths=[content_width],
            )
            block.setStyle(TableStyle([
                ("LINEBEFORE", (0, 0), (0, 0), 2.5, colors.HexColor("#" + colour)),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
            ]))
            story.append(KeepTogether(block))
            story.append(Spacer(1, 6))

    # --- every question ---------------------------------------------------
    # The factor scores say which area is weak. This says which question
    # inside it is, which is the level an action can actually be taken at.
    story.append(Paragraph("Every question", s["h2"]))
    story.append(Paragraph(
        "All answers, grouped by factor. Barrier-worded questions are marked "
        "&mdash; on those, agreeing lowers readiness, and the score shown is "
        "after that has been accounted for.",
        s["small"],
    ))
    story.append(Spacer(1, 5))

    detail_rows: List[List] = []
    for factor in ordered:
        detail_rows.append([
            Paragraph(f"<b>{escape(factor.name)}</b>", s["small"]),
            Paragraph(f"<b>{factor.score:.0f}</b>", s["small"]),
            "",
        ])
        for item in factor.item_scores:
            marker = " <font color='#999999'>(barrier-worded)</font>" if item.reverse else ""
            band = "Advanced" if item.score >= 70 else (
                "Developing" if item.score >= 40 else "Emerging")
            detail_rows.append([
                Paragraph(
                    f"<font color='#888888'>{escape(item.item_id)}</font> "
                    f"{escape(item.text)}{marker}", s["small"]),
                Paragraph(f"{item.score:.0f}", s["small"]),
                _score_bar(item.score, 28 * mm, BAND_COLOURS.get(band, "555555")),
            ])

    detail = Table(detail_rows,
                   colWidths=[content_width - 46 * mm, 12 * mm, 34 * mm])
    detail.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(detail)

    # --- what they wrote --------------------------------------------------
    if results.notes:
        story.append(Paragraph("In your own words", s["h2"]))
        story.append(Paragraph(
            "Not scored, and deliberately so &mdash; but this is usually where "
            "the reason behind a low score sits.",
            s["small"],
        ))
        story.append(Spacer(1, 4))
        for question, answer in results.notes.items():
            story.append(Paragraph(f"<b>{escape(question)}</b>", s["small"]))
            story.append(Paragraph(escape(answer), s["body"]))
            story.append(Spacer(1, 5))

    # --- how to read it ---------------------------------------------------
    story.append(Paragraph("How the score is calculated", s["h2"]))
    story.append(Paragraph(
        f"Each of the {len(cfg.FACTORS)} factors is scored from the answers "
        f"given to its questions, on a 1&ndash;5 agreement scale, converted to "
        f"a 0&ndash;100 scale. Questions worded as barriers are reversed first, "
        f"so a higher score always means more ready. The overall score is the "
        f"weighted average of the factor scores. Bands: Emerging 0&ndash;40, "
        f"Developing 40&ndash;70, Advanced 70&ndash;100.",
        s["small"],
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "This assessment is based on self-reported answers and is intended to "
        "support planning, not to replace professional advice.",
        s["small"],
    ))

    doc.build(story)
    return buffer.getvalue()


def write_pdf(results: AssessmentResults, path: str) -> str:
    """Write the PDF report to disk. Returns the path."""
    with open(path, "wb") as handle:
        handle.write(to_pdf_bytes(results))
    return path


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

_HEADER_FILL = PatternFill("solid", fgColor="2C3E50")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_TITLE_FONT = Font(bold=True, size=14)
_THIN = Side(style="thin", color="D5D5D5")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _write_header(sheet, row: int, headers: List[str]) -> None:
    for column, heading in enumerate(headers, start=1):
        cell = sheet.cell(row=row, column=column, value=heading)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.row_dimensions[row].height = 26


def _set_widths(sheet, widths: List[Tuple[int, int]]) -> None:
    for column, width in widths:
        sheet.column_dimensions[get_column_letter(column)].width = width


def to_excel_bytes(results: AssessmentResults) -> bytes:
    """Build the Excel workbook and return it as bytes."""
    workbook = Workbook()

    # --- Summary ----------------------------------------------------------
    summary = workbook.active
    summary.title = "Summary"
    _set_widths(summary, [(1, 32), (2, 62)])

    summary["A1"] = "AI Adoption Readiness Assessment"
    summary["A1"].font = _TITLE_FONT
    summary["A2"] = f"Generated {_timestamp()}"
    summary["A2"].font = Font(size=9, color="777777")

    row = 4
    summary.cell(row=row, column=1, value="Overall readiness score").font = Font(bold=True)
    score_cell = summary.cell(row=row, column=2, value=round(results.overall_score, 1))
    score_cell.font = Font(bold=True, size=13,
                           color=BAND_COLOURS.get(results.readiness_tier, "000000"))
    row += 1

    summary.cell(row=row, column=1, value="Readiness tier").font = Font(bold=True)
    tier_cell = summary.cell(row=row, column=2, value=results.readiness_tier)
    tier_cell.font = Font(bold=True,
                          color=BAND_COLOURS.get(results.readiness_tier, "000000"))
    row += 1

    summary.cell(row=row, column=1, value="What that means").font = Font(bold=True)
    meaning = summary.cell(row=row, column=2, value=results.tier_description)
    meaning.alignment = Alignment(wrap_text=True, vertical="top")
    summary.row_dimensions[row].height = 46
    row += 2

    summary.cell(row=row, column=1, value="Company context").font = _TITLE_FONT
    row += 1
    for field, label in CONTEXT_LABELS.items():
        value = results.context.get(field)
        if not value:
            continue
        summary.cell(row=row, column=1, value=label)
        shown = _safe_size(value) if field == "employee_band" else value
        summary.cell(row=row, column=2, value=shown)
        row += 1

    row += 1
    if results.strengths:
        summary.cell(row=row, column=1, value="Strengths").font = _TITLE_FONT
        row += 1
        for factor in results.strengths:
            summary.cell(row=row, column=1, value=factor.name)
            summary.cell(row=row, column=2, value=f"{factor.score:.0f}/100")
            row += 1
        row += 1

    if results.barriers:
        summary.cell(row=row, column=1, value="Main barriers").font = _TITLE_FONT
        row += 1
        for factor in results.barriers:
            summary.cell(row=row, column=1, value=factor.name)
            summary.cell(row=row, column=2, value=f"{factor.score:.0f}/100")
            row += 1

    # --- Factor scores ----------------------------------------------------
    factors = workbook.create_sheet("Factor scores")
    _set_widths(factors, [(1, 40), (2, 12), (3, 14), (4, 10), (5, 14), (6, 20)])
    _write_header(factors, 1, [
        "Factor", "Score /100", "Mean (1-5)", "Weight",
        "Contribution", "Band",
    ])

    for index, factor in enumerate(results.ordered_factors(), start=2):
        factors.cell(row=index, column=1, value=factor.name)
        factors.cell(row=index, column=2, value=round(factor.score, 1))
        factors.cell(row=index, column=3, value=round(factor.mean_likert, 2))
        factors.cell(row=index, column=4, value=round(factor.weight, 4))
        factors.cell(row=index, column=5, value=round(factor.weighted_contribution, 2))
        band = factors.cell(row=index, column=6, value=factor.band_label)
        band.font = Font(bold=True,
                         color=BAND_COLOURS.get(factor.band_label, "000000"))
        for column in range(1, 7):
            factors.cell(row=index, column=column).border = _BORDER

    total_row = len(results.factor_scores) + 2
    factors.cell(row=total_row, column=1, value="Overall").font = Font(bold=True)
    factors.cell(row=total_row, column=2,
                 value=round(results.overall_score, 1)).font = Font(bold=True)
    factors.cell(row=total_row, column=6,
                 value=results.readiness_tier).font = Font(bold=True)
    factors.freeze_panes = "A2"

    # A chart, because a workbook of bare numbers is worse than the PDF at the
    # one thing a spreadsheet should be good at. Two views: the factor bars,
    # and a radar that shows the shape of the profile at a glance.
    last = len(results.factor_scores) + 1
    labels = Reference(factors, min_col=1, min_row=2, max_row=last)
    values = Reference(factors, min_col=2, min_row=1, max_row=last)

    bars = BarChart()
    bars.type = "bar"
    bars.title = "Readiness by factor"
    bars.y_axis.title = "Score /100"
    bars.add_data(values, titles_from_data=True)
    bars.set_categories(labels)
    bars.dataLabels = DataLabelList()
    bars.dataLabels.showVal = True
    bars.height, bars.width = 9, 20
    bars.legend = None
    factors.add_chart(bars, f"A{last + 3}")

    shape = RadarChart()
    shape.type = "filled"
    shape.title = "Profile shape"
    shape.add_data(values, titles_from_data=True)
    shape.set_categories(labels)
    shape.height, shape.width = 11, 11
    shape.y_axis.scaling.min = 0
    shape.y_axis.scaling.max = 100
    factors.add_chart(shape, f"H{last + 3}")

    # --- Responses --------------------------------------------------------
    # Both the raw answer and the re-coded one, because the difference between
    # them on reverse-worded questions is the thing people query most.
    responses = workbook.create_sheet("Responses")
    _set_widths(responses, [(1, 10), (2, 34), (3, 62), (4, 12), (5, 16), (6, 14), (7, 12)])
    _write_header(responses, 1, [
        "Item", "Factor", "Question", "Answer (1-5)",
        "Answer label", "Reverse worded?", "Score /100",
    ])

    row = 2
    for factor in results.ordered_factors():
        for item in factor.item_scores:
            responses.cell(row=row, column=1, value=item.item_id)
            responses.cell(row=row, column=2, value=item.factor_name)
            question = responses.cell(row=row, column=3, value=item.text)
            question.alignment = Alignment(wrap_text=True, vertical="top")
            responses.cell(row=row, column=4, value=item.raw_value)
            responses.cell(row=row, column=5,
                           value=cfg.LIKERT_LABELS.get(item.raw_value, ""))
            responses.cell(row=row, column=6, value="Yes" if item.reverse else "No")
            responses.cell(row=row, column=7, value=round(item.score, 1))
            for column in range(1, 8):
                responses.cell(row=row, column=column).border = _BORDER
            row += 1
    responses.freeze_panes = "A2"

    # Every question on one chart. This is the view that shows a factor with a
    # decent average hiding one weak question inside it, which the factor-level
    # numbers alone can't show.
    item_rows = row - 1
    item_chart = BarChart()
    item_chart.type = "bar"
    item_chart.title = "Every question, scored 0-100"
    item_chart.add_data(
        Reference(responses, min_col=7, min_row=1, max_row=item_rows),
        titles_from_data=True,
    )
    item_chart.set_categories(
        Reference(responses, min_col=1, min_row=2, max_row=item_rows)
    )
    item_chart.height, item_chart.width = 20, 20
    item_chart.legend = None
    responses.add_chart(item_chart, f"I2")

    # --- Recommendations --------------------------------------------------
    recs = workbook.create_sheet("Recommendations")
    _set_widths(recs, [(1, 9), (2, 12), (3, 32), (4, 40), (5, 70), (6, 14)])
    _write_header(recs, 1, [
        "Priority", "Severity", "Factor", "Action", "Detail", "Triggered by",
    ])

    if results.recommendations:
        for index, rec in enumerate(results.recommendations, start=1):
            row = index + 1
            recs.cell(row=row, column=1, value=index)
            severity = recs.cell(row=row, column=2,
                                 value=SEVERITY_LABELS.get(rec.severity, rec.severity))
            severity.font = Font(bold=True,
                                 color=SEVERITY_COLOURS.get(rec.severity, "000000"))
            recs.cell(row=row, column=3, value=rec.factor_name)
            recs.cell(row=row, column=4, value=rec.title)
            detail = recs.cell(row=row, column=5, value=rec.action)
            detail.alignment = Alignment(wrap_text=True, vertical="top")
            recs.cell(row=row, column=6, value=rec.triggered_by_item or "factor overall")
            for column in range(1, 7):
                recs.cell(row=row, column=column).border = _BORDER
            recs.row_dimensions[row].height = 42
    else:
        recs.cell(row=2, column=1,
                  value="No actions flagged -- every factor is at or above the "
                        "Advanced threshold.")
    recs.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def write_excel(results: AssessmentResults, path: str) -> str:
    """Write the Excel workbook to disk. Returns the path."""
    with open(path, "wb") as handle:
        handle.write(to_excel_bytes(results))
    return path


# ---------------------------------------------------------------------------
# Filenames
# ---------------------------------------------------------------------------

def suggested_filename(results: AssessmentResults, extension: str) -> str:
    """
    A filename for the download button.

    Uses the tier and the date rather than anything identifying, since there's
    no company name collected to use.
    """
    stamp = datetime.now().strftime("%Y-%m-%d")
    tier = results.readiness_tier.lower()
    return f"ai-readiness-{tier}-{stamp}.{extension.lstrip('.')}"


class ExportService:
    """
    Thin object wrapper over the functions above.

    The functions are the real interface; this exists because the class diagram
    names an ExportService, and the dashboard reads more clearly with one.
    """

    def to_pdf(self, results: AssessmentResults) -> bytes:
        return to_pdf_bytes(results)

    def to_excel(self, results: AssessmentResults) -> bytes:
        return to_excel_bytes(results)

    def write_pdf(self, results: AssessmentResults, path: str) -> str:
        return write_pdf(results, path)

    def write_excel(self, results: AssessmentResults, path: str) -> str:
        return write_excel(results, path)

    def filename(self, results: AssessmentResults, extension: str) -> str:
        return suggested_filename(results, extension)


# ---------------------------------------------------------------------------
# Whole-dataset reporting
# ---------------------------------------------------------------------------
# Everything above describes one company. This part describes a set of them,
# and it lives here rather than in the dashboard so that the screen and the
# downloads are computed once, from the same code. When a report disagrees
# with the page that produced it, this is usually why.

from dataclasses import dataclass as _dataclass, field as _field  # noqa: E402


@_dataclass
class GroupProfile:
    """Mean factor scores for one slice of the data (a country, a sector)."""

    label: str
    count: int
    overall: float
    factor_means: List[Tuple[str, float]]   # (factor_id, mean score)


@_dataclass
class DatasetSummary:
    """Everything the dataset report needs, computed once."""

    count: int = 0
    scores: List[float] = _field(default_factory=list)
    mean: float = 0.0
    lowest: float = 0.0
    highest: float = 0.0
    partial: bool = False
    factors_present: List[str] = _field(default_factory=list)
    factors_absent: List[str] = _field(default_factory=list)
    tier_counts: Dict[str, int] = _field(default_factory=dict)
    factor_means: List[Tuple[str, float]] = _field(default_factory=list)
    by_country: List[GroupProfile] = _field(default_factory=list)
    by_sector: List[GroupProfile] = _field(default_factory=list)
    common_barriers: List[Tuple[str, int]] = _field(default_factory=list)
    recommendations: List = _field(default_factory=list)
    recommendation_counts: List[Tuple[str, int]] = _field(default_factory=list)
    themes: List[Tuple[str, int, List[str]]] = _field(default_factory=list)
    notes: List[Tuple[str, Dict[str, str]]] = _field(default_factory=list)
    source_name: str = ""

    @property
    def split_profiles(self) -> bool:
        """
        Whether the shape should be drawn per group rather than once.

        One averaged shape across several countries or industries hides the
        thing worth seeing. It is only the right picture when the data really
        is one group -- a single company, a single country, or a file that
        never said.
        """
        return len(self.by_country) > 1 or len(self.by_sector) > 1


def _group_profiles(scored, profiles_by_id, attribute: str,
                    minimum: int = 1) -> List[GroupProfile]:
    buckets: Dict[str, List] = {}
    for identifier, result in scored:
        value = getattr(profiles_by_id.get(identifier), attribute, None)
        if value:
            buckets.setdefault(str(value), []).append(result)

    groups: List[GroupProfile] = []
    for label, results in buckets.items():
        if len(results) < minimum:
            continue
        overall = sum(r.overall_score for r in results) / len(results)
        means: List[Tuple[str, float]] = []
        for factor in cfg.FACTORS:
            values = [r.factor(factor.id).score for r in results
                      if factor.id in r.factor_scores]
            if values:
                means.append((factor.id, sum(values) / len(values)))
        groups.append(GroupProfile(label, len(results), overall, means))

    return sorted(groups, key=lambda g: -g.count)


def extract_themes(notes: Sequence[Tuple[str, Dict[str, str]]],
                   limit: int = 7) -> List[Tuple[str, int, List[str]]]:
    """
    Pull recurring subjects out of the written answers.

    The comments are the part of a survey that usually explains the numbers,
    and reading 300 of them by hand is not realistic. This groups them by the
    readiness concepts they mention -- using the same lexicon that matches
    questions -- and reports how many people raised each, with a couple of
    their own sentences as evidence.

    Counting concepts rather than words matters: "cost", "budget", "expensive"
    and "can't afford it" are one concern, and a raw word count would report
    them as four small ones.
    """
    from .survey_import import CONCEPT_LEXICON, _terms

    readable = {
        "money": "Cost and funding",
        "people": "Skills and training",
        "leader": "Leadership and strategy",
        "data": "Data quality and access",
        "govern": "Governance, privacy and trust",
        "culture": "Culture and resistance to change",
        "infra": "Technology and infrastructure",
        "adopt": "Getting started with adoption",
    }

    counts: Dict[str, int] = {}
    examples: Dict[str, List[str]] = {}

    for _, answers in notes:
        text = " ".join(answers.values())
        mentioned = {
            term[1:] for term in _terms(text)
            if term.startswith("~") and term[1:] in readable
        }
        for concept in mentioned:
            counts[concept] = counts.get(concept, 0) + 1
            if len(examples.setdefault(concept, [])) < 2:
                snippet = " ".join(text.split())
                examples[concept].append(
                    snippet[:160] + ("…" if len(snippet) > 160 else "")
                )

    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return [(readable[c], n, examples.get(c, [])) for c, n in ranked]


def cohort_results(scored) -> AssessmentResults:
    """
    Build a single results object representing the average company.

    This exists so the cohort gets recommendations from exactly the same rules
    a single company does, rather than a second set written separately that
    would drift out of step with the first.
    """
    results = [r for _, r in scored]
    factor_scores: Dict[str, FactorScore] = {}

    for factor in cfg.FACTORS:
        present = [r.factor(factor.id) for r in results if factor.id in r.factor_scores]
        if not present:
            continue

        mean_score = sum(f.score for f in present) / len(present)
        items: List[ItemScore] = []
        for item in factor.items:
            values = [
                i.score for f in present for i in f.item_scores if i.item_id == item.id
            ]
            if not values:
                continue
            mean_item = sum(values) / len(values)
            items.append(ItemScore(
                item_id=item.id, text=item.text, factor_id=factor.id,
                factor_name=factor.name,
                raw_value=round(mean_item / 25) + 1,
                adjusted_value=round(mean_item / 25) + 1,
                reverse=item.reverse, score=mean_item,
            ))

        factor_scores[factor.id] = FactorScore(
            factor_id=factor.id, name=factor.name, weight=factor.weight,
            mean_likert=mean_score / 25 + 1, score=mean_score,
            band_label=cfg.band_for_score(mean_score).label,
            weighted_contribution=mean_score * factor.weight,
            item_scores=items, answered=len(items), expected=len(factor.items),
        )

    total_weight = sum(f.weight for f in factor_scores.values()) or 1.0
    overall = sum(f.weighted_contribution for f in factor_scores.values()) / total_weight
    band = cfg.band_for_score(overall)

    strong = sorted((f for f in factor_scores.values()
                     if f.score >= cfg.STRENGTH_THRESHOLD),
                    key=lambda f: -f.score)[:cfg.MAX_STRENGTHS]
    weak = sorted((f for f in factor_scores.values()
                   if f.score < cfg.BARRIER_THRESHOLD),
                  key=lambda f: -f.impact)[:cfg.MAX_BARRIERS]

    gaps: List[ItemScore] = []
    per_factor: Dict[str, int] = {}
    for item in sorted((i for f in factor_scores.values() for i in f.item_scores
                        if i.score < cfg.ITEM_BARRIER_THRESHOLD),
                       key=lambda i: i.score):
        if per_factor.get(item.factor_id, 0) >= cfg.MAX_ITEM_BARRIERS_PER_FACTOR:
            continue
        gaps.append(item)
        per_factor[item.factor_id] = per_factor.get(item.factor_id, 0) + 1
        if len(gaps) >= cfg.MAX_ITEM_BARRIERS:
            break

    return AssessmentResults(
        overall_score=overall, readiness_tier=band.label,
        tier_description=band.description, factor_scores=factor_scores,
        strengths=strong, barriers=weak, item_barriers=gaps,
        partial=any(f.is_partial for f in factor_scores.values())
        or len(factor_scores) < len(cfg.FACTORS),
    )


def summarise_dataset(scored, profiles_by_id,
                      notes: Optional[Sequence[Tuple[str, Dict[str, str]]]] = None,
                      source_name: str = "") -> DatasetSummary:
    """Compute everything the dataset report and the dashboard both need."""
    from .recommendation_engine import RecommendationEngine

    results = [r for _, r in scored]
    overall = [r.overall_score for r in results]
    notes = list(notes or [])

    present = [f.id for f in cfg.FACTORS
               if any(f.id in r.factor_scores for r in results)]

    factor_means: List[Tuple[str, float]] = []
    for factor_id in present:
        values = [r.factor(factor_id).score for r in results
                  if factor_id in r.factor_scores]
        factor_means.append((factor_id, sum(values) / len(values)))

    barrier_counts: Dict[str, int] = {}
    rec_counts: Dict[str, int] = {}
    for result in results:
        for factor in result.barriers:
            barrier_counts[factor.name] = barrier_counts.get(factor.name, 0) + 1
        for rec in result.recommendations:
            rec_counts[rec.title] = rec_counts.get(rec.title, 0) + 1

    average = cohort_results(scored)
    RecommendationEngine().recommend(average)

    return DatasetSummary(
        count=len(results),
        scores=list(overall),
        mean=sum(overall) / len(overall) if overall else 0.0,
        lowest=min(overall) if overall else 0.0,
        highest=max(overall) if overall else 0.0,
        partial=any(r.partial for r in results),
        factors_present=present,
        factors_absent=[f.id for f in cfg.FACTORS if f.id not in present],
        tier_counts={
            band.label: sum(1 for r in results if r.readiness_tier == band.label)
            for band in cfg.READINESS_BANDS
        },
        factor_means=sorted(factor_means, key=lambda kv: -kv[1]),
        by_country=_group_profiles(scored, profiles_by_id, "region"),
        by_sector=_group_profiles(scored, profiles_by_id, "industry_sector"),
        common_barriers=sorted(barrier_counts.items(), key=lambda kv: -kv[1]),
        recommendations=average.recommendations,
        recommendation_counts=sorted(rec_counts.items(), key=lambda kv: -kv[1])[:10],
        themes=extract_themes(notes),
        notes=notes,
        source_name=source_name,
    )


def dataset_pdf_bytes(summary: DatasetSummary) -> bytes:
    """The whole-dataset report, as a PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="AI Adoption Readiness — dataset analysis",
    )
    s = _styles()
    width = doc.width
    story: List = []

    story.append(Paragraph("AI Adoption Readiness", s["title"]))
    story.append(Paragraph(
        f"Dataset analysis &middot; {summary.count} responses &middot; "
        f"generated {_timestamp()}", s["subtitle"]))

    band_colour = BAND_COLOURS.get(cfg.band_for_score(summary.mean).label, "555555")
    headline = Table([[
        Paragraph(f'<font size="30"><b>{summary.mean:.1f}</b></font>'
                  f'<font size="12" color="#777777">/100</font>', s["body"]),
        Paragraph(
            f'<b>Mean readiness across {summary.count} companies</b><br/>'
            f'Lowest {summary.lowest:.1f} &nbsp;&middot;&nbsp; '
            f'Highest {summary.highest:.1f}<br/>'
            + "&nbsp;&middot;&nbsp; ".join(
                f"{label} {count}" for label, count in summary.tier_counts.items()),
            s["body"]),
    ]], colWidths=[38 * mm, width - 38 * mm])
    headline.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F7F7")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("LINEBEFORE", (0, 0), (0, 0), 3, colors.HexColor("#" + band_colour)),
    ]))
    story.append(headline)

    if summary.partial:
        story.append(Spacer(1, 8))
        absent = ", ".join(cfg.FACTORS_BY_ID[f].name for f in summary.factors_absent)
        story.append(Paragraph(
            "<b>Partial coverage.</b> This dataset does not answer every "
            "question, so the scores below are built from the factors it does "
            "cover and re-weighted across them."
            + (f" No reading was possible for: {escape(absent)}." if absent else ""),
            s["small"]))

    # --- factor averages --------------------------------------------------
    story.append(Paragraph("Average score by factor", s["h2"]))
    rows: List[List] = []
    for factor_id, mean in summary.factor_means:
        factor = cfg.FACTORS_BY_ID[factor_id]
        band = cfg.band_for_score(mean).label
        rows.append([
            Paragraph(escape(factor.name), s["body"]),
            Paragraph(f"<b>{mean:.1f}</b>", s["body"]),
            _score_bar(mean, width - 100 * mm, BAND_COLOURS.get(band, "555555")),
            Paragraph(f'<font color="#{BAND_COLOURS.get(band, "555555")}">'
                      f'{band}</font>', s["small"]),
        ])
    table = Table(rows, colWidths=[62 * mm, 16 * mm, width - 100 * mm, 22 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#EAEAEA")),
    ]))
    story.append(table)

    # --- profile shapes ---------------------------------------------------
    # One shape per country and per sector when the data holds more than one,
    # because a single averaged shape across several of them shows a company
    # that does not exist.
    def shapes_for(groups: List[GroupProfile], heading: str) -> None:
        if not groups:
            return
        story.append(Paragraph(heading, s["h2"]))
        cells, labels = [], []
        for group in groups[:6]:
            scores = [(SHORT_FACTOR_LABELS.get(fid, fid), value)
                      for fid, value in group.factor_means]
            colour = BAND_COLOURS.get(cfg.band_for_score(group.overall).label, "555555")
            cells.append(_radar_drawing(scores, colour, size=118))
            labels.append(Paragraph(
                f"<b>{escape(group.label)}</b><br/>"
                f"{group.overall:.1f}/100 &middot; n={group.count}", s["small"]))

        for start in range(0, len(cells), 3):
            chunk = cells[start:start + 3]
            chunk_labels = labels[start:start + 3]
            while len(chunk) < 3:
                chunk.append("")
                chunk_labels.append("")
            grid = Table([chunk, chunk_labels], colWidths=[width / 3.0] * 3)
            grid.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
            ]))
            story.append(grid)

    if summary.split_profiles:
        shapes_for(summary.by_country, "Profile shape by country")
        shapes_for(summary.by_sector, "Profile shape by sector")
    else:
        story.append(Paragraph("Profile shape", s["h2"]))
        scores = [(SHORT_FACTOR_LABELS.get(fid, fid), value)
                  for fid, value in summary.factor_means]
        story.append(_radar_drawing(scores, band_colour, size=175))

    # --- recommendations --------------------------------------------------
    story.append(Paragraph("Recommended actions for this group", s["h2"]))
    if not summary.recommendations:
        story.append(Paragraph(
            "No actions flagged — every factor averages at or above the "
            "Advanced threshold.", s["body"]))
    else:
        story.append(Paragraph(
            "Generated from the average profile across the dataset, using the "
            "same rules applied to an individual assessment.", s["small"]))
        story.append(Spacer(1, 6))
        for index, rec in enumerate(summary.recommendations, start=1):
            colour = SEVERITY_COLOURS.get(rec.severity, "555555")
            label = SEVERITY_LABELS.get(rec.severity, rec.severity.title())
            block = Table([[Paragraph(
                f'<font color="#{colour}"><b>{index}. {escape(label)}</b></font>'
                f'&nbsp;&nbsp;<font color="#777777" size="8">'
                f'{escape(rec.factor_name)}</font><br/>'
                f'<b>{escape(rec.title)}</b><br/>{escape(rec.action)}', s["body"])]],
                colWidths=[width])
            block.setStyle(TableStyle([
                ("LINEBEFORE", (0, 0), (0, 0), 2.5, colors.HexColor("#" + colour)),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
            ]))
            story.append(KeepTogether(block))
            story.append(Spacer(1, 5))

    # --- what people wrote ------------------------------------------------
    if summary.themes:
        story.append(Paragraph("What respondents raised themselves", s["h2"]))
        story.append(Paragraph(
            f"Grouped from the written answers in {len(summary.notes)} "
            f"responses. These are not scored, and they often name things the "
            f"scored questions do not reach.", s["small"]))
        story.append(Spacer(1, 5))
        for name, count, examples in summary.themes:
            share = count / max(1, len(summary.notes)) * 100
            story.append(Paragraph(
                f"<b>{escape(name)}</b> &mdash; raised by {count} "
                f"({share:.0f}%)", s["body"]))
            for example in examples:
                story.append(Paragraph(
                    f'<i>&ldquo;{escape(example)}&rdquo;</i>', s["small"]))
            story.append(Spacer(1, 5))

    story.append(Paragraph("How to read this", s["h2"]))
    story.append(Paragraph(
        "Each factor is scored from its questions on a 1&ndash;5 agreement "
        "scale converted to 0&ndash;100, with barrier-worded questions "
        "reversed first. Group figures are means, and a group of one company "
        "is that company rather than an average. Bands: Emerging 0&ndash;40, "
        "Developing 40&ndash;70, Advanced 70&ndash;100.", s["small"]))

    doc.build(story)
    return buffer.getvalue()


def dataset_excel_bytes(summary: DatasetSummary) -> bytes:
    """The whole-dataset analysis, as a workbook with charts."""
    workbook = Workbook()

    overview = workbook.active
    overview.title = "Overview"
    _set_widths(overview, [(1, 34), (2, 22), (3, 14)])
    overview["A1"] = "AI Adoption Readiness — dataset analysis"
    overview["A1"].font = _TITLE_FONT
    overview["A2"] = f"Generated {_timestamp()}"
    overview["A2"].font = Font(size=9, color="777777")

    row = 4
    for label, value in (
        ("Responses scored", summary.count),
        ("Mean readiness", round(summary.mean, 1)),
        ("Lowest", round(summary.lowest, 1)),
        ("Highest", round(summary.highest, 1)),
        ("Coverage", "partial" if summary.partial else "all 32 questions"),
        ("Source file", summary.source_name or "—"),
    ):
        overview.cell(row=row, column=1, value=label).font = Font(bold=True)
        overview.cell(row=row, column=2, value=value)
        row += 1

    row += 1
    overview.cell(row=row, column=1, value="Tier split").font = _TITLE_FONT
    row += 1
    tier_start = row
    _write_header(overview, row, ["Tier", "Companies", "Share %"])
    row += 1
    for label, count in summary.tier_counts.items():
        overview.cell(row=row, column=1, value=label)
        overview.cell(row=row, column=2, value=count)
        overview.cell(row=row, column=3,
                      value=round(count / max(1, summary.count) * 100, 1))
        row += 1

    tiers = BarChart()
    tiers.type = "col"
    tiers.title = "Companies by readiness tier"
    tiers.add_data(Reference(overview, min_col=2, min_row=tier_start,
                             max_row=row - 1), titles_from_data=True)
    tiers.set_categories(Reference(overview, min_col=1, min_row=tier_start + 1,
                                   max_row=row - 1))
    tiers.height, tiers.width, tiers.legend = 8, 14, None
    overview.add_chart(tiers, f"E{tier_start}")

    # --- factors ----------------------------------------------------------
    factors = workbook.create_sheet("Factor averages")
    _set_widths(factors, [(1, 42), (2, 14), (3, 14)])
    _write_header(factors, 1, ["Factor", "Mean score", "Band"])
    for index, (factor_id, mean) in enumerate(summary.factor_means, start=2):
        band = cfg.band_for_score(mean).label
        factors.cell(row=index, column=1, value=cfg.FACTORS_BY_ID[factor_id].name)
        factors.cell(row=index, column=2, value=round(mean, 1))
        cell = factors.cell(row=index, column=3, value=band)
        cell.font = Font(bold=True, color=BAND_COLOURS.get(band, "000000"))
        for column in range(1, 4):
            factors.cell(row=index, column=column).border = _BORDER

    last = len(summary.factor_means) + 1
    labels = Reference(factors, min_col=1, min_row=2, max_row=last)
    values = Reference(factors, min_col=2, min_row=1, max_row=last)

    bars = BarChart()
    bars.type = "bar"
    bars.title = "Average score by factor"
    bars.add_data(values, titles_from_data=True)
    bars.set_categories(labels)
    bars.dataLabels = DataLabelList()
    bars.dataLabels.showVal = True
    bars.height, bars.width, bars.legend = 9, 20, None
    factors.add_chart(bars, f"A{last + 3}")

    shape = RadarChart()
    shape.type = "filled"
    shape.title = "Average profile shape"
    shape.add_data(values, titles_from_data=True)
    shape.set_categories(labels)
    shape.y_axis.scaling.min, shape.y_axis.scaling.max = 0, 100
    shape.height, shape.width = 11, 11
    factors.add_chart(shape, f"H{last + 3}")

    # --- groups -----------------------------------------------------------
    for title, groups in (("By country", summary.by_country),
                          ("By sector", summary.by_sector)):
        if not groups:
            continue
        sheet = workbook.create_sheet(title)
        headers = [title.replace("By ", "").title(), "Companies", "Mean"]
        headers += [cfg.FACTORS_BY_ID[f.id].name for f in cfg.FACTORS]
        _set_widths(sheet, [(1, 26), (2, 12), (3, 10)]
                    + [(i, 20) for i in range(4, 11)])
        _write_header(sheet, 1, headers)

        for index, group in enumerate(groups, start=2):
            means = dict(group.factor_means)
            sheet.cell(row=index, column=1, value=group.label)
            sheet.cell(row=index, column=2, value=group.count)
            sheet.cell(row=index, column=3, value=round(group.overall, 1))
            for offset, factor in enumerate(cfg.FACTORS):
                value = means.get(factor.id)
                sheet.cell(row=index, column=4 + offset,
                           value=round(value, 1) if value is not None else None)

        end = len(groups) + 1
        chart = BarChart()
        chart.type = "col"
        chart.title = f"Mean readiness {title.lower()}"
        chart.add_data(Reference(sheet, min_col=3, min_row=1, max_row=end),
                       titles_from_data=True)
        chart.set_categories(Reference(sheet, min_col=1, min_row=2, max_row=end))
        chart.height, chart.width, chart.legend = 8, 18, None
        sheet.add_chart(chart, f"A{end + 3}")
        sheet.freeze_panes = "A2"

    # --- recommendations and themes ---------------------------------------
    advice = workbook.create_sheet("Recommendations")
    _set_widths(advice, [(1, 9), (2, 12), (3, 32), (4, 40), (5, 70)])
    _write_header(advice, 1, ["Priority", "Severity", "Factor", "Action", "Detail"])
    for index, rec in enumerate(summary.recommendations, start=1):
        row = index + 1
        advice.cell(row=row, column=1, value=index)
        cell = advice.cell(row=row, column=2,
                           value=SEVERITY_LABELS.get(rec.severity, rec.severity))
        cell.font = Font(bold=True, color=SEVERITY_COLOURS.get(rec.severity, "000000"))
        advice.cell(row=row, column=3, value=rec.factor_name)
        advice.cell(row=row, column=4, value=rec.title)
        detail = advice.cell(row=row, column=5, value=rec.action)
        detail.alignment = Alignment(wrap_text=True, vertical="top")
        advice.row_dimensions[row].height = 42

    if summary.themes:
        themes = workbook.create_sheet("Written answers")
        _set_widths(themes, [(1, 36), (2, 12), (3, 90)])
        _write_header(themes, 1, ["Theme", "Mentions", "Example"])
        row = 2
        for name, count, examples in summary.themes:
            themes.cell(row=row, column=1, value=name)
            themes.cell(row=row, column=2, value=count)
            example = themes.cell(row=row, column=3,
                                  value=examples[0] if examples else "")
            example.alignment = Alignment(wrap_text=True, vertical="top")
            row += 1

        row += 1
        themes.cell(row=row, column=1, value="All written answers").font = _TITLE_FONT
        row += 1
        _write_header(themes, row, ["Response", "Question", "Answer"])
        row += 1
        for identifier, answers in summary.notes:
            for question, answer in answers.items():
                themes.cell(row=row, column=1, value=identifier)
                themes.cell(row=row, column=2, value=question)
                cell = themes.cell(row=row, column=3, value=answer)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                row += 1

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
