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
from datetime import datetime
from typing import Dict, List, Optional, Tuple
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
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import score_configuration as cfg
from .assessment_results import AssessmentResults


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
