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
from src.export_service import BAND_COLOURS, SEVERITY_COLOURS, SEVERITY_LABELS, ExportService
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
    radius = size * 0.34
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
    st.caption("One block per question. Green(Strong), Yellow (Neutral), Red(Weak). Hover to read it.")


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
        if key.startswith(("item_", "ctx_", "specify_")) or key == "results":
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
        "Answer every question about your company as it is today, not as you "
        "would like it to be. It takes about five minutes. Nothing you enter "
        "is saved anywhere."
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
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()
    st.subheader("Take it with you")

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
            st.caption("Kept as open-ended answers (never scored):")
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
    What to show when the file is a survey, but not this one.

    Scoring it is refused, and the reason is worth being straight about: the
    seven factors are measured by 32 specific statements, and a survey asking
    different questions measures different things. A number produced from it
    would look like a readiness score without being one.

    Refusing and stopping there would waste the file, though. The question
    that can be answered is how the two instruments relate — which factors
    that survey covers, which it leaves out, and what it asks about that this
    framework doesn't reach. That is a comparison worth having.
    """
    analysis = report.compare_to_framework()

    st.warning(
        f"**This is a different questionnaire.** None of its questions match "
        f"this instrument's wording, so it can't be scored here — the seven "
        f"factors are defined by 32 specific statements, and a score built "
        f"from other questions would not be measuring the same thing."
    )
    st.markdown(
        "What can be done is compare the two. Below is where that survey's "
        "questions fall against the seven factors, matched on meaning rather "
        "than wording."
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
        st.subheader("Not covered at all")
        for factor_id in not_covered:
            st.markdown(f"• **{cfg.FACTORS_BY_ID[factor_id].name}**")
        st.caption(
            "That survey asks nothing that corresponds to these factors, so it "
            "could not produce a reading on them even in principle."
        )

    if analysis["unrelated"]:
        st.subheader("Asks about things this framework doesn't measure")
        for header, score in analysis["unrelated"]:
            st.markdown(
                f"<div style='font-size:.84rem;margin:2px 0 6px 0'>"
                f"<span style='color:#888'>{score:.2f}</span> &nbsp;{esc(header)}</div>",
                unsafe_allow_html=True,
            )
        st.caption(
            "These score near zero because they measure outcomes — whether AI "
            "has already helped — rather than readiness to adopt it. Different "
            "question, not a worse one."
        )

    st.divider()
    st.caption(
        "Matching here uses stemming, a domain concept lexicon and "
        "IDF-weighted cosine similarity over the question text. It is reliable "
        "at factor level and much less so at the level of individual "
        "questions, which is why it is used for comparison and not for scoring."
    )


def render_batch() -> None:
    st.markdown(
        "Upload a survey export and every response is scored with the same "
        "engine. The column names don't have to match the tool's — it works "
        "out which column is which from the question wording, and reads word "
        "answers like \"Agree\" as well as numbers."
    )

    upload = st.file_uploader("Survey file", type=["csv", "xlsx", "xlsm"])
    if upload is None:
        st.caption(
            "CSV or Excel. A Google Forms export of this questionnaire works "
            "as downloaded — no renaming or reformatting needed."
        )
        return

    report = import_survey(upload.getvalue(), upload.name)
    if report.error:
        st.error(report.error)
        return

    if report.looks_like_a_different_survey:
        render_framework_comparison(report)
        return

    render_import_report(report)

    pairs = profiles_from_report(report)
    valid = [(identifier, profile) for identifier, profile in pairs if profile.is_valid()]
    invalid = [(identifier, profile) for identifier, profile in pairs
               if not profile.is_valid()]

    st.write(f"**{len(pairs)} responses read** — {len(valid)} scored, "
             f"{len(invalid)} rejected.")

    if invalid:
        with st.expander(f"{len(invalid)} responses couldn't be scored"):
            for identifier, profile in invalid[:25]:
                st.write(f"`{identifier}` — {profile.validate()[0]}")
            if len(invalid) > 25:
                st.caption(f"…and {len(invalid) - 25} more.")

    if not valid:
        return

    scored = []
    for identifier, profile in valid:
        result = SCORING.score(profile)
        ADVICE.recommend(result)
        scored.append((identifier, result))

    render_batch_analytics(report, scored, dict(pairs))


def render_batch_analytics(report, scored, profiles_by_id) -> None:
    """
    The charts worth drawing for this particular file.

    Which ones appear depends on what the data contains: a single-country
    file gets no country chart, and a file with no open-ended questions gets
    no comments section. Drawing a comparison with one bar in it is worse
    than leaving it out.
    """
    results = [result for _, result in scored]
    overall = [result.overall_score for result in results]
    mean = sum(overall) / len(overall)

    top, middle, bottom = st.columns(3)
    top.metric("Mean readiness", f"{mean:.1f}")
    middle.metric("Lowest", f"{min(overall):.1f}")
    bottom.metric("Highest", f"{max(overall):.1f}")

    st.subheader("How the scores are spread")
    histogram(overall)

    st.subheader("Tier split")
    for band in cfg.READINESS_BANDS:
        count = sum(1 for r in results if r.readiness_tier == band.label)
        score_bar(
            band.label, count / len(results) * 100, band.label,
            caption=f"% &middot; {count} of {len(results)}",
        )

    st.subheader("Average by factor")
    factor_means = []
    for factor in cfg.FACTORS:
        scores = [r.factor(factor.id).score for r in results]
        factor_means.append((factor.name, sum(scores) / len(scores)))
    for name, value in sorted(factor_means, key=lambda kv: -kv[1]):
        score_bar(name, value, cfg.band_for_score(value).label)

    st.subheader("Average profile shape")
    radar(
        [(SHORT_FACTOR_NAMES[f.id],
          sum(r.factor(f.id).score for r in results) / len(results))
         for f in cfg.FACTORS],
        band_colour(cfg.band_for_score(mean).label),
    )

    # --- comparisons that only make sense if the data supports them --------
    drawn = []
    st.subheader("Breakdowns")

    for field, title in (
        ("current_ai_stage", "Readiness by current AI adoption stage"),
        ("industry_sector", "Readiness by sector"),
        ("region", "Readiness by country"),
        ("employee_band", "Readiness by company size"),
        ("years_in_operation", "Readiness by company age"),
    ):
        groups: Dict[str, List[float]] = defaultdict(list)
        for identifier, result in scored:
            value = getattr(profiles_by_id[identifier], field, None)
            if value:
                groups[str(value)].append(result.overall_score)
        if grouped_bars(title, groups):
            drawn.append(title)
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if not drawn:
        st.caption(
            "Every response in this file shares the same sector, size, country "
            "and adoption stage, so there's nothing to compare across."
        )
    elif "Readiness by current AI adoption stage" in drawn:
        st.caption(
            "The adoption-stage breakdown is the one that matters for the "
            "research question: it is the outcome variable that empirical "
            "factor weights would be derived against."
        )

    # --- what people actually wrote ---------------------------------------
    notes = [(row.get("company_id"), row["free_text"])
             for row in report.rows if row.get("free_text")]
    if notes:
        st.subheader("In their own words")
        st.caption(
            f"{len(notes)} of {len(report.rows)} responses included written "
            f"answers. These are never scored, but they are where the numbers "
            f"get explained."
        )
        for identifier, answers in notes[:40]:
            with st.expander(f"{identifier}"):
                for question, answer in answers.items():
                    st.markdown(f"**{question}**")
                    st.write(answer)

    # --- download ---------------------------------------------------------
    header = ["company_id", "overall_score", "readiness_tier"]
    header += [f.id for f in cfg.FACTORS]
    header += ["industry_sector", "region", "employee_band",
               "years_in_operation", "current_ai_stage", "recommendation_count"]

    lines = [",".join(header)]
    for identifier, result in scored:
        profile = profiles_by_id[identifier]
        row = [identifier, f"{result.overall_score:.2f}", result.readiness_tier]
        row += [f"{result.factor(f.id).score:.2f}" for f in cfg.FACTORS]
        row += [
            f'"{getattr(profile, name, "") or ""}"'
            for name in ("industry_sector", "region", "employee_band",
                         "years_in_operation", "current_ai_stage")
        ]
        row.append(str(len(result.recommendations)))
        lines.append(",".join(row))

    st.download_button(
        "Download scored results (CSV)",
        data="\n".join(lines).encode("utf-8"),
        file_name="scored_results.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("AI Adoption Readiness Assessment")
st.caption(
    "A readiness check for small and medium businesses considering AI. "
    "Scores seven areas, shows where the gaps are, and suggests what to do next."
)

with st.sidebar:
    st.header("About")
    st.write(
        "This tool scores AI adoption readiness across seven factors using a "
        "questionnaire developed for an MSc dissertation project."
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
        "Nothing you enter is stored. Answers stay in your browser session and "
        "are gone when you close the tab. Downloaded files are the only copy."
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
