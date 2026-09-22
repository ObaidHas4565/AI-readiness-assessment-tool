"""
AI Adoption Readiness Assessment -- dashboard

Run it with:

    streamlit run app.py

The front end for everything in src/. It collects the answers, hands them to
the scoring engine, shows the result, and offers the PDF and Excel downloads.
Nothing is written to a database or to disk -- answers live in Streamlit's
session state and disappear when the browser tab closes.

A note on the questions: the barrier-worded ones are shown exactly as written,
with nothing to mark them out. Telling a respondent which questions are scored
backwards would change how they answer them, and the engine flips them
afterwards anyway.
"""

from __future__ import annotations

import html
import math
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import streamlit as st

from src import score_configuration as cfg
from src.company_profile import CompanyProfile
from src.export_service import (
    BAND_COLOURS,
    SEVERITY_COLOURS,
    SEVERITY_LABELS,
    ExportService,
    dataset_excel_bytes,
    dataset_pdf_bytes,
    summarise_dataset,
)
from src.recommendation_engine import RecommendationEngine
from src.scoring_engine import ScoringEngine
from src.survey_import import import_survey, profiles_from_report


st.set_page_config(
    page_title="AI Adoption Readiness Assessment",
    page_icon="📊",
    layout="centered",
)

SCORING = ScoringEngine()
ADVICE = RecommendationEngine()
EXPORTS = ExportService()

CONTEXT_QUESTIONS: Dict[str, str] = {
    "industry_sector": "Which sector does your company operate in?",
    "employee_band": "How many people does your company employ?",
    "years_in_operation": "How long has the company been operating?",
    "region": "Which country does the company mainly operate in?",
    "current_ai_stage": "Where is the company with AI at the moment?",
}

SPECIFY = "Other (please specify)"

# The full factor names don't fit round the edge of a radar chart, so each one
# gets a one-word label there. Everywhere else uses the real name.
SHORT_FACTOR_NAMES: Dict[str, str] = {
    "budget": "Budget",
    "workforce": "Workforce",
    "leadership": "Leadership",
    "data": "Data",
    "technology": "Technology",
    "culture": "Culture",
    "governance": "Governance",
}


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def band_colour(label: str) -> str:
    return "#" + BAND_COLOURS.get(label, "555555")


def esc(text: object) -> str:
    """Escape anything a respondent typed before it goes into markup."""
    return html.escape(str(text), quote=True)


def evidence_html(rec, single: bool = False) -> str:
    """
    The respondents' own words, under the recommendation they support.

    Shown so a reader can see whether an action agrees with what people
    actually wrote. The quotes support the recommendation; they are not part
    of the score, and never move it.
    """
    if not getattr(rec, "evidence", None):
        return ""

    if single:
        lead = "In your own words:"
    else:
        people = "respondent" if rec.evidence_count == 1 else "respondents"
        lead = f"Raised in writing by {rec.evidence_count} {people}:"

    quotes = "".join(
        f"<div style='margin-top:2px'>“{esc(quote)}”</div>"
        for quote in rec.evidence
    )
    return (
        f"<div style='font-size:.78rem;color:#777;margin-top:8px;"
        f"padding-top:6px;border-top:1px solid #E6E6E6'>"
        f"<b>{lead}</b>{quotes}</div>"
    )


def render_written_answers(results) -> None:
    """
    The company's own written answers, and what reading them found.

    Shown after the recommendations rather than buried at the end, because on
    a single assessment these three answers are the only place the respondent
    could say something the 32 questions never asked.
    """
    if not results.notes:
        return

    st.divider()
    st.subheader("In your own words")

    insights = results.text_insights
    if insights is not None and insights.by_factor:
        named = ", ".join(signal.factor_name for signal in insights.by_factor)
        st.caption(
            f"Read as being about: **{named}**. Anything here that the scores "
            f"did not already flag appears in the actions above, marked as "
            f"raised in comments. Written answers never change a score."
        )
    elif insights is not None and insights.answers_used == 0:
        st.caption(
            "Nothing specific enough to analyse — answers like “N/A”, “none” "
            "or a blank are set aside rather than counted."
        )
    else:
        st.caption("Never scored, and shown here as written.")

    for question, answer in results.notes.items():
        st.markdown(f"**{esc(question)}**")
        st.markdown(
            f"<div style='background:#FAFAFA;border-left:3px solid #E0E0E0;"
            f"padding:8px 12px;margin-bottom:8px;font-size:.9rem'>"
            f"{esc(answer)}</div>",
            unsafe_allow_html=True,
        )


def score_bar(label: str, score: float, band: str, caption: Optional[str] = None) -> None:
    """
    One labelled bar. Plain HTML so it matches the colours in the PDF.

    `caption` overrides the text on the right, for the places where the number
    is a percentage of companies rather than a score.
    """
    right = caption if caption is not None else f"/100 &middot; {esc(band)}"
    st.markdown(
        f"""
        <div style="margin-bottom:9px">
          <div style="display:flex;justify-content:space-between;font-size:0.86rem">
            <span>{esc(label)}</span>
            <span style="color:{band_colour(band)}"><b>{score:.0f}</b>
              <span style="opacity:.55;font-weight:400">{right}</span>
            </span>
          </div>
          <div style="background:#E8E8E8;border-radius:3px;height:9px;margin-top:3px">
            <div style="background:{band_colour(band)};width:{max(score, 0):.1f}%;
                        height:9px;border-radius:3px"></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def radar(scores: Sequence[Tuple[str, float]], colour: str, size: int = 340) -> None:
    """
    A radar chart drawn as inline SVG.

    Hand-drawn rather than pulled from a charting library because the whole
    tool runs on the standard library plus three packages, and one shape does
    not justify a fourth. It answers a different question from the bar chart:
    the bars rank the factors, this shows whether the profile is balanced or
    spiky.
    """
    if not scores:
        return

    centre = size / 2
    # Small charts sit in narrow columns, so the web needs to shrink to leave
    # room for the labels around it -- otherwise "Governance" runs off the edge.
    radius = size * (0.28 if size < 250 else 0.34)
    count = len(scores)

    def point(index: int, value: float) -> Tuple[float, float]:
        angle = (2 * math.pi * index / count) - (math.pi / 2)
        distance = radius * max(0.0, min(100.0, value)) / 100.0
        return centre + distance * math.cos(angle), centre + distance * math.sin(angle)

    rings = "".join(
        f'<circle cx="{centre}" cy="{centre}" r="{radius * fraction:.1f}" '
        f'fill="none" stroke="#E4E4E4" stroke-width="1"/>'
        for fraction in (0.25, 0.5, 0.75, 1.0)
    )

    spokes, labels = "", ""
    for index, (name, _) in enumerate(scores):
        end_x, end_y = point(index, 100)
        spokes += (f'<line x1="{centre}" y1="{centre}" x2="{end_x:.1f}" '
                   f'y2="{end_y:.1f}" stroke="#E4E4E4" stroke-width="1"/>')
        label_x, label_y = point(index, 124)
        anchor = "middle"
        if label_x < centre - 12:
            anchor = "end"
        elif label_x > centre + 12:
            anchor = "start"
        labels += (f'<text x="{label_x:.1f}" y="{label_y:.1f}" font-size="10.5" '
                   f'fill="#666" text-anchor="{anchor}">{esc(name)}</text>')

    polygon = " ".join(
        f"{x:.1f},{y:.1f}" for x, y in
        (point(index, value) for index, (_, value) in enumerate(scores))
    )
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{colour}"/>'
        for x, y in (point(i, v) for i, (_, v) in enumerate(scores))
    )

    st.markdown(
        f"""
        <div style="display:flex;justify-content:center">
        <svg viewBox="0 0 {size} {size}" width="{size}" height="{size}"
             xmlns="http://www.w3.org/2000/svg">
          {rings}{spokes}
          <polygon points="{polygon}" fill="{colour}" fill-opacity="0.22"
                   stroke="{colour}" stroke-width="2"/>
          {dots}{labels}
        </svg></div>
        """,
        unsafe_allow_html=True,
    )


def item_strip(results) -> None:
    """
    Every question as a small coloured block, grouped by factor.

    Shows something the factor averages hide: a factor sitting on a decent
    average while one question inside it is on the floor.
    """
    for factor in results.ordered_factors():
        blocks = ""
        for item in factor.item_scores:
            band = cfg.band_for_score(item.score).label
            blocks += (
                f'<span title="{esc(item.item_id)}: {esc(item.text)} '
                f'({item.score:.0f}/100)" '
                f'style="display:inline-block;width:30px;height:16px;margin-right:3px;'
                f'border-radius:2px;background:{band_colour(band)};'
                f'opacity:{0.35 + 0.65 * item.score / 100:.2f}"></span>'
            )
        st.markdown(
            f'<div style="margin-bottom:7px;font-size:.8rem">'
            f'<span style="display:inline-block;width:250px;'
            f'vertical-align:middle">{esc(factor.name)}</span>{blocks}</div>',
            unsafe_allow_html=True,
        )
    st.caption("One block per question, Green - Strong, Yellow - Neutral, Red - Weak. Hover to read it.")


def histogram(values: Sequence[float], bins: int = 10) -> None:
    """Distribution of overall scores, drawn as stacked HTML bars."""
    if not values:
        return
    counts = [0] * bins
    for value in values:
        index = min(bins - 1, int(value / (100 / bins)))
        counts[index] += 1
    tallest = max(counts) or 1

    columns = ""
    for index, count in enumerate(counts):
        low = index * (100 // bins)
        band = cfg.band_for_score(low + (100 // bins) / 2).label
        height = int(90 * count / tallest)
        columns += (
            f'<div style="flex:1;text-align:center">'
            f'<div style="height:92px;display:flex;align-items:flex-end;'
            f'justify-content:center">'
            f'<div style="width:80%;height:{height}px;'
            f'background:{band_colour(band)};border-radius:2px 2px 0 0"></div>'
            f'</div>'
            f'<div style="font-size:.66rem;color:#888;margin-top:3px">{low}</div>'
            f'<div style="font-size:.7rem"><b>{count}</b></div></div>'
        )
    st.markdown(f'<div style="display:flex;gap:2px">{columns}</div>',
                unsafe_allow_html=True)


def grouped_bars(title: str, groups: Dict[str, List[float]], minimum: int = 1) -> bool:
    """
    Mean score per group, biggest group first.

    Returns False without drawing anything when there's only one group worth
    showing -- a chart comparing a category against itself is noise, and which
    charts are worth drawing depends on what's actually in the file.
    """
    usable = {name: values for name, values in groups.items() if len(values) >= minimum}
    if len(usable) < 2:
        return False

    st.markdown(f"**{esc(title)}**")
    ordered = sorted(usable.items(), key=lambda kv: -len(kv[1]))
    for name, values in ordered:
        mean = sum(values) / len(values)
        score_bar(
            name, mean, cfg.band_for_score(mean).label,
            caption=f"/100 &middot; n={len(values)}",
        )
    return True


def answer_label(value: int) -> str:
    return f"{value} — {cfg.LIKERT_LABELS[value]}"


def reset_assessment() -> None:
    for key in list(st.session_state.keys()):
        if (key.startswith(("item_", "ctx_", "specify_", "open_"))
                or key == "results"):
            del st.session_state[key]


# ---------------------------------------------------------------------------
# The assessment form
# ---------------------------------------------------------------------------

def context_value(field: str) -> Optional[str]:
    """
    The answer to one context question.

    For the open fields, picking "Other (please specify)" means the typed
    answer is the value. "Other" on its own would tell us nothing, and a tool
    meant to work across countries and industries can't rely on a fixed list
    covering everyone.
    """
    chosen = st.session_state.get(f"ctx_{field}")
    if chosen == SPECIFY:
        typed = st.session_state.get(f"specify_{field}")
        return typed.strip() if typed and typed.strip() else None
    return chosen


def render_form() -> None:
    st.markdown(
        "Please answer every question based on how your company is today, rather than how you would like it to be. The assessment takes about 5 minutes, and nothing you enter is saved."
    )

    answered = sum(
        1 for item in cfg.ALL_ITEMS if st.session_state.get(f"item_{item.id}") is not None
    )
    st.progress(answered / len(cfg.ALL_ITEMS),
                text=f"{answered} of {len(cfg.ALL_ITEMS)} questions answered")

    st.divider()
    st.subheader("About your company")

    for field, options in cfg.CATEGORICAL_FIELDS.items():
        choices = list(options)
        if field in cfg.OPEN_FIELDS:
            # The list is a shortcut, not a limit. Anything not on it is typed
            # in instead of being squeezed into "Other".
            choices = [c for c in choices if c.lower() != "other"] + [SPECIFY]

        st.selectbox(
            CONTEXT_QUESTIONS[field],
            options=choices,
            index=None,
            placeholder="Choose an option",
            key=f"ctx_{field}",
        )
        if st.session_state.get(f"ctx_{field}") == SPECIFY:
            st.text_input(
                "Please specify",
                key=f"specify_{field}",
                placeholder="Type your answer",
                label_visibility="collapsed",
            )

    st.divider()
    st.subheader("Readiness questions")
    st.caption(
        "Each section covers one area of readiness. Answer how strongly you "
        "agree with each statement."
    )

    for number, factor in enumerate(cfg.FACTORS, start=1):
        done = sum(
            1 for item in factor.items
            if st.session_state.get(f"item_{item.id}") is not None
        )
        mark = "✓" if done == len(factor.items) else f"{done}/{len(factor.items)}"

        # Every section stays open. Streamlit re-runs the whole script on each
        # answer, so anything driving `expanded` from a fixed value snaps the
        # section shut the moment someone picks an option -- which loses their
        # place and makes it impossible to tell what's been completed.
        with st.expander(f"{number}. {factor.name}  ·  {mark}", expanded=True):
            for item in factor.items:
                st.radio(
                    item.text,
                    options=[1, 2, 3, 4, 5],
                    format_func=answer_label,
                    index=None,
                    horizontal=True,
                    key=f"item_{item.id}",
                )
                st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)

    st.divider()
    st.subheader("Anything else")
    st.caption(
        "Optional - your answers won't affect your score. Use this space to share anything the questions above may not have covered. Your comments will be considered alongside your results and may be included in your recommendations if they highlight an important concern."
    )
    st.text_area(
        "What is the single biggest thing holding your company back from AI?",
        key="open_biggest_barrier", height=80,
    )
    st.text_area(
        "What would help your company move forward most?",
        key="open_what_would_help", height=80,
    )
    st.text_area(
        "Any other concerns or comments about AI adoption",
        key="open_additional_comments", height=80,
    )

    st.divider()

    if st.button("See my results", type="primary", use_container_width=True):
        submit()


def submit() -> None:
    """Collect the answers, validate them, and score if they're complete."""
    payload: Dict[str, object] = {}

    for field in cfg.CATEGORICAL_FIELDS:
        value = context_value(field)
        if value is not None:
            payload[field] = value

    for item in cfg.ALL_ITEMS:
        value = st.session_state.get(f"item_{item.id}")
        if value is not None:
            payload[item.id] = value

    for written in ("open_biggest_barrier", "open_what_would_help",
                    "open_additional_comments"):
        payload[written] = st.session_state.get(written, "") or ""

    profile = CompanyProfile.from_dict(payload)
    errors = profile.validate()

    if errors:
        unanswered = [
            item for item in cfg.ALL_ITEMS
            if st.session_state.get(f"item_{item.id}") is None
        ]
        missing_context = [
            CONTEXT_QUESTIONS[field] for field in cfg.CATEGORICAL_FIELDS
            if context_value(field) is None
        ]

        # An answer can be present but not usable -- a sector that doesn't
        # read as one, say. Counting blanks alone reported "0 questions and 0
        # company details still to go" while refusing to continue, which told
        # the person nothing about what was actually wrong. Anything that
        # isn't a plain blank is shown in full, in its own words.
        blanks = len(unanswered) + len(missing_context)
        rejected = [
            message for message in errors
            if "is required" not in message and "not answered" not in message
        ]

        if rejected:
            st.error("**Something needs changing before this can be scored.**")
            for message in rejected:
                st.write(f"• {message}")
            if blanks:
                st.write(f"There {'is' if blanks == 1 else 'are'} also "
                         f"{blanks} unanswered item{'' if blanks == 1 else 's'}.")
        else:
            st.error(
                f"**Not quite finished** — {len(unanswered)} question"
                f"{'s' if len(unanswered) != 1 else ''} and "
                f"{len(missing_context)} company detail"
                f"{'s' if len(missing_context) != 1 else ''} still to go."
            )

        if missing_context:
            st.write("**About your company** — " + "; ".join(missing_context))

        by_factor: Dict[str, int] = Counter(
            cfg.FACTORS_BY_ID[cfg.ITEM_TO_FACTOR[item.id]].name for item in unanswered
        )
        for name, count in by_factor.items():
            st.write(f"**{name}** — {count} unanswered")
        return

    results = SCORING.score(profile)
    ADVICE.recommend(results)
    st.session_state["results"] = results
    st.rerun()


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

def render_results(results) -> None:
    colour = band_colour(results.readiness_tier)

    st.markdown(
        f"""
        <div style="border-left:5px solid {colour};background:#F7F7F7;
                    padding:16px 18px;border-radius:4px">
          <div style="font-size:2.6rem;font-weight:700;line-height:1">
            {results.overall_score:.1f}<span style="font-size:1rem;opacity:.5">/100</span>
          </div>
          <div style="color:{colour};font-size:1.15rem;font-weight:600;margin-top:4px">
            {esc(results.readiness_tier)}
          </div>
          <div style="font-size:0.9rem;margin-top:6px">{esc(results.tier_description)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    bars_tab, shape_tab, detail_tab = st.tabs(
        ["Factor scores", "Profile shape", "Question detail"]
    )
    with bars_tab:
        for factor in results.ordered_factors():
            score_bar(factor.name, factor.score, factor.band_label)
    with shape_tab:
        radar([(SHORT_FACTOR_NAMES[f.factor_id], f.score)
               for f in results.ordered_factors()], colour)
        st.caption(
            "A balanced shape means readiness is even across the board. A spiky "
            "one means some areas are far ahead of others."
        )
    with detail_tab:
        item_strip(results)

    left, right = st.columns(2)
    with left:
        st.subheader("Strengths")
        if results.strengths:
            for factor in results.strengths:
                st.markdown(f"**{factor.name}** — {factor.score:.0f}/100")
        else:
            st.caption("No factor reached the strength threshold of 70.")
    with right:
        st.subheader("Main barriers")
        if results.barriers:
            for factor in results.barriers:
                st.markdown(f"**{factor.name}** — {factor.score:.0f}/100")
        else:
            st.caption("No factor fell below the barrier threshold of 50.")

    if results.item_barriers:
        st.subheader("Specific gaps")
        for item in results.item_barriers:
            note = (
                " &nbsp;*(barrier statement — agreeing lowers readiness)*"
                if item.reverse else ""
            )
            st.markdown(
                f"`{item.item_id}` {item.text}{note} &nbsp;**{item.score:.0f}/100**"
            )

    st.subheader("Recommended actions")
    if not results.recommendations:
        st.success(
            "No actions flagged — every factor scored at or above the Advanced "
            "threshold."
        )
    else:
        st.caption(
            "In priority order. Priority reflects how much closing each gap "
            "would move the overall score."
        )
        for index, rec in enumerate(results.recommendations, start=1):
            rec_colour = "#" + SEVERITY_COLOURS.get(rec.severity, "555555")
            label = SEVERITY_LABELS.get(rec.severity, rec.severity.title())
            source = rec.factor_name
            if rec.triggered_by_item:
                source += f" · {rec.triggered_by_item}"
            st.markdown(
                f"""
                <div style="border-left:3px solid {rec_colour};background:#FAFAFA;
                            padding:10px 14px;margin-bottom:9px;border-radius:3px">
                  <span style="color:{rec_colour};font-weight:700;font-size:.85rem">
                    {index}. {esc(label)}</span>
                  <span style="opacity:.55;font-size:.78rem"> &nbsp;{esc(source)}</span>
                  <div style="font-weight:600;margin-top:3px">{esc(rec.title)}</div>
                  <div style="font-size:.88rem;margin-top:3px">{esc(rec.action)}</div>
                  {evidence_html(rec, single=True)}
                </div>
                """,
                unsafe_allow_html=True,
            )

    render_written_answers(results)

    st.divider()
    st.subheader("Download Your Results")

    pdf_column, excel_column = st.columns(2)
    with pdf_column:
        st.download_button(
            "Download PDF report",
            data=EXPORTS.to_pdf(results),
            file_name=EXPORTS.filename(results, "pdf"),
            mime="application/pdf",
            use_container_width=True,
        )
    with excel_column:
        st.download_button(
            "Download Excel workbook",
            data=EXPORTS.to_excel(results),
            file_name=EXPORTS.filename(results, "xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    st.caption("The workbook has the factor and question charts as well as the numbers.")

    st.divider()
    if st.button("Start a new assessment"):
        reset_assessment()
        st.rerun()


# ---------------------------------------------------------------------------
# Batch mode -- score a whole file at once
# ---------------------------------------------------------------------------

def render_import_report(report) -> None:
    """Show what the importer made of the file, before any results."""
    matched = len(set(report.matched_items))
    total = len(cfg.ALL_ITEMS)

    if matched == total and not report.missing_context:
        st.success(f"Matched all {total} questions and every company detail.")
    else:
        st.info(
            f"Matched {matched} of {total} questions"
            + (f", missing: {', '.join(report.missing_context)}"
               if report.missing_context else ".")
        )

    with st.expander("How each column was read"):
        fuzzy = [m for m in report.matches if m.kind == "item" and m.confidence < 0.999]
        st.write(f"**{len(report.matches)} columns matched.**")
        if fuzzy:
            st.caption(
                "Matched on wording rather than an exact string — the column "
                "text differs slightly from the question as configured:"
            )
            for match in sorted(fuzzy, key=lambda m: m.confidence)[:10]:
                st.write(f"`{match.target}` ← {match.header}  ({match.confidence:.0%})")
        if report.free_text_headers:
            st.caption(
                "Kept as open-ended answers — not scored, but read and "
                "matched to the factors they concern:"
            )
            for header in report.free_text_headers:
                st.write(f"• {header}")
        if report.ignored_headers:
            st.caption(f"Ignored: {', '.join(report.ignored_headers)}")
        if report.unmatched_headers:
            st.caption("Couldn't place these:")
            for header in report.unmatched_headers:
                st.write(f"• {header}")


def render_framework_comparison(report) -> None:
    """
    What to show when the file is a dataset, but not this one.

    Scoring it is refused, and the reason is worth being straight about: the
    seven factors are measured by 32 specific statements, and a dataset asking
    different questions measures different things. A number produced from it
    would look like a readiness score without being one.

    Refusing and stopping there would waste the file, though. The question
    that can be answered is how the two instruments relate — which factors
    that dataset covers, which it leaves out, and what it asks about that this
    framework doesn't reach. That is a comparison worth having.
    """
    analysis = report.compare_to_framework()

    st.warning(
        "This dataset is different from the questionnaire used in this assessment. The questions don't match closely enough for the tool to score directly. The assessment uses 32 specific statements to measure 7 readiness factors, so using different questions could produce results that aren't directly comparable."
    )
    st.markdown(
        "You can compare the 2. Below you can see how the questions in this dataset relate to the 7 readiness factors. The questions are matched based on their meaning rather than their exact wording."
    )

    covered = analysis["covered"]
    not_covered = analysis["not_covered"]

    st.subheader(f"Covers {len(covered)} of {len(cfg.FACTORS)} factors")

    for factor in cfg.FACTORS:
        hits = analysis["by_factor"][factor.id]
        if not hits:
            continue
        st.markdown(f"**{factor.name}**")
        for header, score in sorted(hits, key=lambda pair: -pair[1]):
            st.markdown(
                f"<div style='font-size:.84rem;margin:2px 0 6px 0'>"
                f"<span style='color:#888'>{score:.2f}</span> &nbsp;{esc(header)}</div>",
                unsafe_allow_html=True,
            )

    if not_covered:
        st.subheader("Not covered by this dataset")
        for factor_id in not_covered:
            st.markdown(f"• **{cfg.FACTORS_BY_ID[factor_id].name}**")
        st.caption(
            "The dataset doesn't include the questions that correspond to these factors, so the tool can't score those factors from this dataset."
        )

    if analysis["unrelated"]:
        st.subheader("Includes questions not covered by this assessment")
        for header, score in analysis["unrelated"]:
            st.markdown(
                f"<div style='font-size:.84rem;margin:2px 0 6px 0'>"
                f"<span style='color:#888'>{score:.2f}</span> &nbsp;{esc(header)}</div>",
                unsafe_allow_html=True,
            )
        st.caption(
            "These scores are low because the questions focus on the results of using AI, such as whether AI has already helped the company, rather than its readiness to adopt AI. They measure something different from the assessment, not something better or worse."
        )

    st.divider()
    st.caption(
        "The questions are matched by their meaning rather than their exact wording. This works best when looking at the 7 readiness factors as a whole, but individual question matches may be less precise. That's why the matching is used for comparison and not for scoring."
    )


def render_batch() -> None:
    st.markdown(
        "Upload your dataset and the assessment will score each response using the same scoring method. You don't need to rename your columns to match the tool. It can identify the relevant questions from their wording and understand answers such as 'Agree' as well as numerical responses."
    )

    upload = st.file_uploader("Datasets", type=["csv", "xlsx", "xlsm"])
    if upload is None:
        st.caption(
            "CSV or Excel"
        )
        return

    first_pass = import_survey(upload.getvalue(), upload.name)
    if first_pass.error:
        st.error(first_pass.error)
        return

    # A file that is a different instrument gets the comparison first, and
    # then the option to score whatever factors it does cover. Leaving those
    # factors unread wastes a real reading; applying them without asking would
    # be deciding on the researcher's behalf that two questions measure the
    # same thing.
    if first_pass.looks_like_a_different_survey:
        render_framework_comparison(first_pass)

        analysis = first_pass.compare_to_framework()
        if not analysis["covered"]:
            return

        st.divider()
        st.subheader("Score the factors it does cover")
        covered = ", ".join(
            cfg.FACTORS_BY_ID[f].name for f in analysis["covered"])
        st.markdown(
            f"This dataset has questions matching **{covered}**. Those can be scored on their own, and the overall score will be based only on the readiness factors covered by the dataset. Any factors that are not included will be left out rather than treated as zero."
        )
        st.caption(
            "Please treat the results as an indication rather than an exact measurement. The questions come from a different dataset and have been matched to this assessment based on their meaning. The matches are more reliable when looking at the readiness factors as a whole than when looking at individual questions."
        )
        if not st.checkbox("Score the covered factors", key="score_partial"):
            return

        report = import_survey(upload.getvalue(), upload.name,
                               use_meaning_matches=True)
        partial_mode = True
    else:
        render_import_report(first_pass)
        report = first_pass
        partial_mode = bool(report.missing_items)

    pairs = profiles_from_report(report)
    scored, rejected = [], []
    for identifier, profile in pairs:
        try:
            result = SCORING.score(profile, allow_partial=partial_mode)
        except Exception:  # noqa: BLE001 - reported to the user below
            rejected.append((identifier, profile))
            continue
        if not partial_mode and not profile.is_valid():
            rejected.append((identifier, profile))
            continue
        ADVICE.recommend(result)
        scored.append((identifier, result))

    st.write(f"**{len(pairs)} responses read** — {len(scored)} scored, "
             f"{len(rejected)} rejected.")

    if rejected:
        with st.expander(f"{len(rejected)} responses couldn't be scored"):
            for identifier, profile in rejected[:25]:
                problems = profile.validate()
                st.write(f"`{identifier}` — "
                         f"{problems[0] if problems else 'no usable answers'}")
            if len(rejected) > 25:
                st.caption(f"…and {len(rejected) - 25} more.")

    if not scored:
        return

    notes = [(row.get("company_id"), row["free_text"])
             for row in report.rows if row.get("free_text")]
    summary = summarise_dataset(scored, dict(pairs), notes, upload.name)
    render_dataset(summary)


def render_dataset(summary) -> None:
    """The dataset analysis: the same numbers the downloads are built from."""
    if summary.partial:
        absent = [cfg.FACTORS_BY_ID[f].name for f in summary.factors_absent]
        st.warning(
            "**Partial coverage.** Scores below are built only from the "
            "questions this dataset contains, re-weighted across the factors "
            "present."
            + (f" No reading was possible for: {', '.join(absent)}."
               if absent else "")
        )

    top, middle, bottom = st.columns(3)
    top.metric("Mean readiness", f"{summary.mean:.1f}")
    middle.metric("Lowest", f"{summary.lowest:.1f}")
    bottom.metric("Highest", f"{summary.highest:.1f}")

    st.subheader("How the scores are spread")
    histogram(summary.scores)

    st.subheader("Tier split")
    for band in cfg.READINESS_BANDS:
        count = summary.tier_counts.get(band.label, 0)
        score_bar(band.label, count / max(1, summary.count) * 100, band.label,
                  caption=f"% &middot; {count} of {summary.count}")

    st.subheader("Average by factor")
    for factor_id, mean in summary.factor_means:
        score_bar(cfg.FACTORS_BY_ID[factor_id].name, mean,
                  cfg.band_for_score(mean).label)

    # --- profile shapes ---------------------------------------------------
    # Split by country and sector when the data holds more than one of either.
    # A single averaged shape over several countries describes a company that
    # does not exist anywhere in the file.
    if summary.split_profiles:
        if len(summary.by_country) > 1:
            st.subheader("Profile shape by country")
            _radar_grid(summary.by_country)
        if len(summary.by_sector) > 1:
            st.subheader("Profile shape by sector")
            _radar_grid(summary.by_sector)
    else:
        st.subheader("Average profile shape")
        radar([(SHORT_FACTOR_NAMES[fid], value)
               for fid, value in summary.factor_means],
              band_colour(cfg.band_for_score(summary.mean).label))

    # --- recommendations --------------------------------------------------
    st.subheader("Recommended actions for this group")
    if not summary.recommendations:
        st.success("No actions flagged — every factor averages at or above "
                   "the Advanced threshold.")
    else:
        st.caption(
            "Built from the average profile across the dataset, using the "
            "same rules a single assessment uses."
        )
        for index, rec in enumerate(summary.recommendations, start=1):
            colour = "#" + SEVERITY_COLOURS.get(rec.severity, "555555")
            label = SEVERITY_LABELS.get(rec.severity, rec.severity.title())
            st.markdown(
                f"""
                <div style="border-left:3px solid {colour};background:#FAFAFA;
                            padding:10px 14px;margin-bottom:9px;border-radius:3px">
                  <span style="color:{colour};font-weight:700;font-size:.85rem">
                    {index}. {esc(label)}</span>
                  <span style="opacity:.55;font-size:.78rem">
                    &nbsp;{esc(rec.factor_name)}</span>
                  <div style="font-weight:600;margin-top:3px">{esc(rec.title)}</div>
                  <div style="font-size:.88rem;margin-top:3px">{esc(rec.action)}</div>
                  {evidence_html(rec)}
                </div>
                """,
                unsafe_allow_html=True,
            )

    if summary.recommendation_counts:
        with st.expander("Most common recommendations across individual companies"):
            for title, count in summary.recommendation_counts:
                st.write(f"**{count}×** {title}")

    # --- what people wrote ------------------------------------------------
    insights = summary.text_insights
    if insights is not None and insights.used:
        st.subheader("Which factors the written answers name")
        st.caption(
            f"{insights.answers_used} of {insights.answers_seen} written "
            f"answers said something specific. The other "
            f"{insights.answers_dropped} were blanks or non-answers (“N/A”, "
            f"“none”, “no”) and were set aside rather than counted. Each "
            f"remaining answer is placed against the factor it talks about, "
            f"so the comments can be read against the scores. Shares are of "
            f"all {insights.total_respondents} respondents, not only those "
            f"whose answers could be read. No score changes as a result."
        )

        means = dict(summary.factor_means)
        for signal in insights.by_factor:
            score = means.get(signal.factor_id)
            scored = f"score {score:.0f}/100" if score is not None else "not scored"
            flagged = any(rec.factor_id == signal.factor_id
                          and rec.severity != "raised"
                          for rec in summary.recommendations)
            mismatch = "" if flagged else " · not flagged by the scores"
            score_bar(
                signal.factor_name, signal.share,
                cfg.band_for_score(100 - signal.share).label,
                caption=f"% raised it · {scored}{mismatch}",
            )
            for example in signal.examples[:1]:
                st.markdown(
                    f"<div style='font-size:.8rem;color:#777;margin:-4px 0 10px 2px'>"
                    f"“{esc(example)}”</div>", unsafe_allow_html=True)

    if summary.themes:
        st.subheader("What respondents raised themselves")
        st.caption(
            f"Grouped by subject rather than by word, so “cost”, “budget” and "
            f"“can't afford it” count as one concern rather than three."
        )
        for name, count, examples in summary.themes:
            share = count / max(1, len(summary.notes)) * 100
            score_bar(name, share, cfg.band_for_score(100 - share).label,
                      caption=f"% &middot; raised by {count}")
            for example in examples[:1]:
                st.markdown(
                    f"<div style='font-size:.8rem;color:#777;margin:-4px 0 10px 2px'>"
                    f"“{esc(example)}”</div>", unsafe_allow_html=True)

    if summary.notes:
        with st.expander(f"All {len(summary.notes)} written responses"):
            for identifier, answers in summary.notes[:60]:
                st.markdown(f"**{esc(identifier)}**")
                for question, answer in answers.items():
                    st.markdown(f"*{esc(question)}* — {esc(answer)}")
                st.markdown("---")

    # --- downloads --------------------------------------------------------
    st.divider()
    st.subheader("Download Your Results")
    pdf_column, excel_column = st.columns(2)
    with pdf_column:
        st.download_button(
            "Download PDF analysis",
            data=dataset_pdf_bytes(summary),
            file_name="ai-readiness-dataset-analysis.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with excel_column:
        st.download_button(
            "Download Excel analysis",
            data=dataset_excel_bytes(summary),
            file_name="ai-readiness-dataset-analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    


def _radar_grid(groups) -> None:
    """Small multiples: one profile shape per country or sector."""
    for start in range(0, min(len(groups), 6), 3):
        columns = st.columns(3)
        for column, group in zip(columns, groups[start:start + 3]):
            with column:
                radar(
                    [(SHORT_FACTOR_NAMES[fid], value)
                     for fid, value in group.factor_means],
                    band_colour(cfg.band_for_score(group.overall).label),
                    size=210,
                )
                st.markdown(
                    f"<div style='text-align:center;font-size:.84rem;"
                    f"margin-top:-6px'><b>{esc(group.label)}</b><br/>"
                    f"<span style='color:#888'>{group.overall:.1f}/100 · "
                    f"n={group.count}</span></div>",
                    unsafe_allow_html=True,
                )
    if len(groups) > 6:
        st.caption(f"Showing the six largest of {len(groups)} groups.")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("AI Adoption Readiness Assessment")
st.caption(
    "This is a readiness check for companies considering AI, and it scores 7 areas of your company, points out where the gaps are, and suggests what to do next."
)

with st.sidebar:
    st.header("About")
    st.write(
        "This tool scores AI adoption readiness across seven factors using a questionnaire."
    )
    st.write(f"**{len(cfg.FACTORS)} factors · {len(cfg.ALL_ITEMS)} questions**")
    st.divider()
    st.subheader("Score bands")
    for band in cfg.READINESS_BANDS:
        st.markdown(
            f"<span style='color:{band_colour(band.label)}'>●</span> "
            f"**{band.label}** {band.lower:.0f}–{band.upper:.0f}",
            unsafe_allow_html=True,
        )
    st.divider()
    st.caption(
        "Nothing you entered is stored. Your answers stay in your browser session and are removed when you close the tab. If you download a report, that downloaded file is the only copy of your results."
    )

assessment_tab, batch_tab = st.tabs(["Assessment", "Dataset"])

with assessment_tab:
    results = st.session_state.get("results")
    if results is None:
        render_form()
    else:
        render_results(results)

with batch_tab:
    render_batch()
