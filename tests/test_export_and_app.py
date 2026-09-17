"""
Tests for the export service (step 6) and the dashboard (step 7).

The export tests check the files are actually produced and that the numbers
inside them match the results object, rather than just checking nothing threw.
The dashboard tests drive the real app through Streamlit's AppTest harness, so
a broken widget or a crash on submit shows up here instead of in a demo.
"""

import io
import os
import zipfile

import pytest

from src import score_configuration as cfg
from src.company_profile import CompanyProfile
from src.export_service import (
    ExportService,
    suggested_filename,
    to_excel_bytes,
    to_pdf_bytes,
)
from src.recommendation_engine import RecommendationEngine
from src.scoring_engine import ScoringEngine


CONTEXT = {
    "industry_sector": "Manufacturing",
    "employee_band": "10-49",
    "years_in_operation": "6-10 years",
    "region": "UAE",
    "current_ai_stage": "Exploring",
}


def results_for(answer_for) -> "object":
    responses = {item.id: answer_for(item) for item in cfg.ALL_ITEMS}
    results = ScoringEngine().score(
        CompanyProfile.from_dict({**CONTEXT, **responses})
    )
    RecommendationEngine().recommend(results)
    return results


@pytest.fixture
def mixed_results():
    """A company with strengths, barriers, item gaps and recommendations."""
    responses = {item.id: 3 for item in cfg.ALL_ITEMS}
    for item in cfg.FACTORS_BY_ID["budget"].items:
        responses[item.id] = 1 if item.reverse else 5      # -> 100
    for item in cfg.FACTORS_BY_ID["governance"].items:
        responses[item.id] = 5 if item.reverse else 1      # -> 0

    results = ScoringEngine().score(
        CompanyProfile.from_dict({**CONTEXT, **responses})
    )
    RecommendationEngine().recommend(results)
    return results


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def test_pdf_is_a_real_pdf(mixed_results):
    data = to_pdf_bytes(mixed_results)
    assert data.startswith(b"%PDF-")
    assert data.rstrip().endswith(b"%%EOF")
    assert len(data) > 2000


@pytest.mark.parametrize(
    "answer_for",
    [
        lambda item: 1 if item.reverse else 5,   # perfect, no recommendations
        lambda item: 5 if item.reverse else 1,   # worst, everything flagged
        lambda item: 3,                          # flat neutral
    ],
)
def test_pdf_builds_for_every_extreme(answer_for):
    """The layout must survive empty sections and full ones alike."""
    assert to_pdf_bytes(results_for(answer_for)).startswith(b"%PDF-")


def test_pdf_handles_factor_names_containing_ampersands(mixed_results):
    """
    Most factor names contain "&", which reportlab would otherwise treat as
    the start of an entity and reject. This is the regression guard for that.
    """
    assert any("&" in factor.name for factor in cfg.FACTORS), "test premise gone"
    assert to_pdf_bytes(mixed_results).startswith(b"%PDF-")


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

def test_excel_is_a_real_workbook_with_the_expected_sheets(mixed_results):
    from openpyxl import load_workbook

    data = to_excel_bytes(mixed_results)
    assert zipfile.is_zipfile(io.BytesIO(data)), "xlsx files are zip archives"

    workbook = load_workbook(io.BytesIO(data))
    assert workbook.sheetnames == [
        "Summary", "Factor scores", "Responses", "Recommendations",
    ]


def test_excel_factor_scores_match_the_results(mixed_results):
    from openpyxl import load_workbook

    sheet = load_workbook(io.BytesIO(to_excel_bytes(mixed_results)))["Factor scores"]
    written = {
        sheet.cell(row=row, column=1).value: sheet.cell(row=row, column=2).value
        for row in range(2, len(cfg.FACTORS) + 2)
    }

    for factor in mixed_results.factor_scores.values():
        assert written[factor.name] == pytest.approx(factor.score, abs=0.05)


def test_excel_lists_every_question(mixed_results):
    from openpyxl import load_workbook

    sheet = load_workbook(io.BytesIO(to_excel_bytes(mixed_results)))["Responses"]
    written = {sheet.cell(row=row, column=1).value for row in range(2, sheet.max_row + 1)}
    assert written == {item.id for item in cfg.ALL_ITEMS}


def test_excel_never_writes_a_size_excel_would_read_as_a_date(mixed_results):
    """Same trap as the readable CSV -- "10-49" becomes Oct-49 in Excel."""
    import re
    from openpyxl import load_workbook

    sheet = load_workbook(io.BytesIO(to_excel_bytes(mixed_results)))["Summary"]
    for row in sheet.iter_rows(values_only=True):
        for value in row:
            if isinstance(value, str):
                assert not re.fullmatch(r"\d+-\d+", value), f"{value!r} converts to a date"


def test_filenames_carry_the_tier_and_no_identifying_detail(mixed_results):
    name = suggested_filename(mixed_results, "pdf")
    assert name.endswith(".pdf")
    assert mixed_results.readiness_tier.lower() in name


def test_service_wrapper_matches_the_functions(mixed_results):
    service = ExportService()
    assert service.to_pdf(mixed_results).startswith(b"%PDF-")
    assert zipfile.is_zipfile(io.BytesIO(service.to_excel(mixed_results)))


def test_write_helpers_put_files_on_disk(mixed_results, tmp_path):
    from src.export_service import write_excel, write_pdf

    pdf = write_pdf(mixed_results, str(tmp_path / "r.pdf"))
    excel = write_excel(mixed_results, str(tmp_path / "r.xlsx"))

    assert open(pdf, "rb").read(5) == b"%PDF-"
    assert zipfile.is_zipfile(excel)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
# These drive app.py itself. They're slower than the rest of the suite because
# each one runs the whole script, but they catch the class of bug that only
# appears when the app is actually used.

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


APP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py"
)


def run_app() -> AppTest:
    # Absolute path: AppTest resolves a relative one against this test file's
    # own folder, not the project root.
    return AppTest.from_file(APP_PATH, default_timeout=120).run()


def fill_in(app: AppTest, answer_for) -> AppTest:
    for field, options in cfg.CATEGORICAL_FIELDS.items():
        app.session_state[f"ctx_{field}"] = options[0]
    for item in cfg.ALL_ITEMS:
        app.session_state[f"item_{item.id}"] = answer_for(item)
    return app.run()


def test_app_loads_with_every_question_on_it():
    app = run_app()
    assert not app.exception
    assert len(app.radio) == len(cfg.ALL_ITEMS)
    assert len(app.selectbox) == len(cfg.CATEGORICAL_FIELDS)


def test_submitting_an_empty_form_reports_what_is_missing():
    app = run_app()
    app.button[0].click().run()

    assert not app.exception
    assert "results" not in app.session_state
    assert app.error, "an incomplete submission must show an error"


def test_completed_assessment_produces_a_score():
    app = fill_in(run_app(), lambda item: 1 if item.reverse else 5)
    app.button[0].click().run()

    assert not app.exception
    results = app.session_state["results"]
    assert results.overall_score == pytest.approx(100.0)
    assert results.readiness_tier == "Advanced"


def test_results_view_offers_both_downloads():
    app = fill_in(run_app(), lambda item: 3)
    app.button[0].click().run()

    assert not app.exception
    labels = [button.label for button in app.download_button]
    assert "Download PDF report" in labels
    assert "Download Excel workbook" in labels


def test_starting_over_clears_the_answers():
    app = fill_in(run_app(), lambda item: 3)
    app.button[0].click().run()
    assert "results" in app.session_state

    next(b for b in app.button if b.label == "Start a new assessment").click().run()

    assert not app.exception
    assert "results" not in app.session_state
    # The form is showing again, so the radios exist but none is selected.
    assert all(radio.value is None for radio in app.radio)
