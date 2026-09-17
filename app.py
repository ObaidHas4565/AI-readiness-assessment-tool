"""
AI Adoption Readiness Assessment -- dashboard

Run it with:

    streamlit run app.py

This is the front end for everything in src/. It collects the answers, hands
them to the scoring engine, shows the result, and offers the PDF and Excel
downloads. Nothing is written to a database or to disk -- the answers live in
Streamlit's session state and disappear when the browser tab closes, which is
what the assessment was designed around.

A note on the questions: the barrier-worded ones are shown exactly as written,
with nothing to mark them out. That's deliberate. Telling a respondent which
questions are scored backwards would change how they answer them, and the
scoring engine flips them afterwards anyway.
"""

from __future__ import annotations

import io
from typing import Dict, List, Optional

import streamlit as st

from src import score_configuration as cfg
from src.company_profile import CompanyProfile
from src.export_service import BAND_COLOURS, SEVERITY_COLOURS, SEVERITY_LABELS, ExportService
from src.recommendation_engine import RecommendationEngine
from src.scoring_engine import ScoringEngine
from src.synthetic_data import load_profiles_from_lines


st.set_page_config(
    page_title="AI Adoption Readiness Assessment",
    page_icon="📊",
    layout="centered",
)

SCORING = ScoringEngine()
ADVICE = RecommendationEngine()
EXPORTS = ExportService()

# Friendlier wording than the raw field names for the context questions.
CONTEXT_QUESTIONS: Dict[str, str] = {
    "industry_sector": "Which sector does your company operate in?",
    "employee_band": "How many people does your company employ?",
    "years_in_operation": "How long has the company been operating?",
    "region": "Where does the company mainly operate?",
    "current_ai_stage": "Where is the company with AI at the moment?",
}


# ---------------------------------------------------------------------------
# Small display helpers
# ---------------------------------------------------------------------------

def band_colour(label: str) -> str:
    return "#" + BAND_COLOURS.get(label, "555555")


def score_bar(label: str, score: float, band: str, caption: Optional[str] = None) -> None:
    """
    One labelled bar. Plain HTML so it matches the colours in the PDF.

    `caption` overrides the text on the right. The tier distribution needs it,
    because the number it shows is a percentage of companies rather than a
    score, and "/100 - Emerging" next to it would read as a score.
    """
    right = caption if caption is not None else f"/100 &middot; {band}"
    st.markdown(
        f"""
        <div style="margin-bottom:9px">
          <div style="display:flex;justify-content:space-between;font-size:0.86rem">
            <span>{label}</span>
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


def answer_label(value: int) -> str:
    return f"{value} — {cfg.LIKERT_LABELS[value]}"


def reset_assessment() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(("item_", "ctx_")) or key == "results":
            del st.session_state[key]


# ---------------------------------------------------------------------------
# The assessment form
# ---------------------------------------------------------------------------

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
        st.selectbox(
            CONTEXT_QUESTIONS[field],
            options=list(options),
            index=None,
            placeholder="Choose an option",
            key=f"ctx_{field}",
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
        with st.expander(f"{number}. {factor.name}  ·  {mark}", expanded=number == 1):
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
        value = st.session_state.get(f"ctx_{field}")
        if value is not None:
            payload[field] = value

    for item in cfg.ALL_ITEMS:
        value = st.session_state.get(f"item_{item.id}")
        if value is not None:
            payload[item.id] = value

    profile = CompanyProfile.from_dict(payload)
    errors = profile.validate()

    if errors:
        st.error(
            f"**{len(errors)} question"
            f"{'s' if len(errors) > 1 else ''} still needs an answer.**"
        )
        # Say which ones, rather than making them hunt through seven sections.
        missing_factors = sorted({
            cfg.FACTORS_BY_ID[cfg.ITEM_TO_FACTOR[item.id]].name
            for item in cfg.ALL_ITEMS
            if st.session_state.get(f"item_{item.id}") is None
        })
        missing_context = [
            CONTEXT_QUESTIONS[field]
            for field in cfg.CATEGORICAL_FIELDS
            if st.session_state.get(f"ctx_{field}") is None
        ]
        if missing_context:
            st.write("**About your company** — " + "; ".join(missing_context))
        for name in missing_factors:
            st.write(f"**{name}** — some statements are unanswered")
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
            {results.readiness_tier}
          </div>
          <div style="font-size:0.9rem;margin-top:6px">{results.tier_description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Readiness by factor")
    for factor in results.ordered_factors():
        score_bar(factor.name, factor.score, factor.band_label)

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
                    {index}. {label}</span>
                  <span style="opacity:.55;font-size:.78rem"> &nbsp;{source}</span>
                  <div style="font-weight:600;margin-top:3px">{rec.title}</div>
                  <div style="font-size:.88rem;margin-top:3px">{rec.action}</div>
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

    st.divider()
    if st.button("Start a new assessment"):
        reset_assessment()
        st.rerun()


# ---------------------------------------------------------------------------
# Batch mode -- score a whole CSV at once
# ---------------------------------------------------------------------------
# This isn't part of what an SME would use. It's here so a survey export or a
# generated dataset can be run through the same engine in one go, which is what
# the evaluation chapter needs.

def render_batch() -> None:
    st.markdown(
        "Upload a CSV of responses in the tool's column format — a survey "
        "export, or a file from `generate_synthetic_data.py` — and every row "
        "is scored with the same engine. Useful for checking how the tool "
        "behaves across many companies rather than one."
    )

    upload = st.file_uploader("CSV file", type=["csv"])
    if upload is None:
        st.caption(
            "Columns needed: the five context fields, plus one column per "
            "question code (BUD_1, WRK_1, …). See `data/DATA_DICTIONARY.md`."
        )
        return

    text = io.StringIO(upload.getvalue().decode("utf-8"))
    try:
        loaded = load_profiles_from_lines(text)
    except Exception as error:  # noqa: BLE001 - surfaced to the user as-is
        st.error(f"That file couldn't be read as a CSV: {error}")
        return

    if not loaded:
        st.warning("The file has no rows in it.")
        return

    valid, invalid = [], []
    for identifier, profile in loaded:
        (valid if profile.is_valid() else invalid).append((identifier, profile))

    st.write(f"**{len(loaded)} rows read** — {len(valid)} valid, {len(invalid)} rejected.")

    if invalid:
        with st.expander(f"{len(invalid)} rows failed validation"):
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

    overall = [r.overall_score for _, r in scored]
    st.metric("Mean overall readiness", f"{sum(overall) / len(overall):.1f}/100")

    st.subheader("Tier distribution")
    for band in cfg.READINESS_BANDS:
        count = sum(1 for _, r in scored if r.readiness_tier == band.label)
        share = count / len(scored) * 100
        score_bar(
            band.label, share, band.label,
            caption=f"% &middot; {count} of {len(scored)} companies",
        )

    st.subheader("Average score by factor")
    for factor in cfg.FACTORS:
        scores = [r.factor(factor.id).score for _, r in scored]
        mean = sum(scores) / len(scores)
        score_bar(factor.name, mean, cfg.band_for_score(mean).label)

    # Downloadable per-company results, so the numbers can go into a
    # spreadsheet or a stats package rather than being read off the screen.
    header = ["company_id", "overall_score", "readiness_tier"]
    header += [f.id for f in cfg.FACTORS] + ["recommendation_count"]
    lines = [",".join(header)]
    for identifier, result in scored:
        row = [identifier, f"{result.overall_score:.2f}", result.readiness_tier]
        row += [f"{result.factor(f.id).score:.2f}" for f in cfg.FACTORS]
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
    st.write(
        f"**{len(cfg.FACTORS)} factors · {len(cfg.ALL_ITEMS)} questions**"
    )
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

assessment_tab, batch_tab = st.tabs(["Assessment", "Score a dataset"])

with assessment_tab:
    results = st.session_state.get("results")
    if results is None:
        render_form()
    else:
        render_results(results)

with batch_tab:
    render_batch()
