"""
Tests for reading real survey exports.

These exist because of a specific failure: a Google Forms export of this
tool's own questionnaire was rejected in full, all 17 responses, purely
over formatting. Every test here is a version of something that actually
went wrong, so the same class of problem can't come back quietly.
"""

import io

import pytest

from src import score_configuration as cfg
from src.company_profile import CompanyProfile
from src.scoring_engine import ScoringEngine
from src.survey_import import (
    ImportReport,
    _question_text,
    import_survey,
    match_columns,
    profiles_from_report,
    read_table,
)


# ---------------------------------------------------------------------------
# Building a file shaped like the real thing
# ---------------------------------------------------------------------------

WORD_FOR = {1: "Strongly Disagree", 2: "Disagree", 3: "Neutral",
            4: "Agree", 5: "Strongly Agree"}

# Typos present in the live form but not in the configuration. Left in on
# purpose: exact matching threw these two questions away.
FORM_TYPOS = {
    "WRK_3": "We have idenitfied specific skill gaps that block AI adoption.",
    "DAT_2": "We trust the quality and accuracy of our exisitng data.",
    "CUL_4": "We regulary discuss innovation and new technology at a company level.",
}


def forms_headers() -> list:
    """Headers the way Google Forms writes them: section name, question in [ ]."""
    headers = [
        "Timestamp", "Industry Sector", "Number of Employees",
        "Years in operation", "Region/Country of operation",
        "Current stage of AI adoption",
    ]
    for factor in cfg.FACTORS:
        for item in factor.items:
            text = FORM_TYPOS.get(item.id, item.text)
            headers.append(f"{factor.name} [{text}]")
    headers += [
        "What is the single biggest barrier preventing your company from adopting AI?",
        "What would help your company move forward with AI adoption?",
        "Any additional comments?",
    ]
    return headers


def forms_csv(answer: int = 4, sector: str = "Real Estate",
              region: str = "Canada", rows: int = 3) -> bytes:
    """A Forms-style export: readable headers, word answers, extra columns."""
    headers = forms_headers()
    lines = [",".join(f'"{h}"' for h in headers)]
    for index in range(rows):
        values = [
            f"9/{index + 1}/2026 10:00:00", sector, "50-249", "10+ years",
            region, "Exploring",
        ]
        values += [WORD_FOR[answer]] * len(cfg.ALL_ITEMS)
        values += ["Cost", "Funding and training", ""]
        lines.append(",".join(f'"{v}"' for v in values))
    return "\n".join(lines).encode("utf-8")


# ---------------------------------------------------------------------------
# The failure that started this
# ---------------------------------------------------------------------------

def test_google_forms_export_imports_without_any_editing():
    report = import_survey(forms_csv(), "responses.csv")

    assert report.error is None
    assert len(set(report.matched_items)) == len(cfg.ALL_ITEMS), (
        f"missing {report.missing_items}"
    )
    assert report.missing_context == []
    assert report.unmatched_headers == []


def test_every_imported_response_is_valid_and_scores():
    report = import_survey(forms_csv(rows=5), "responses.csv")
    pairs = profiles_from_report(report)

    assert len(pairs) == 5
    for identifier, profile in pairs:
        assert profile.validate() == [], f"{identifier}: {profile.validate()}"
        assert 0 <= ScoringEngine().score(profile).overall_score <= 100


def test_questions_with_typos_still_match():
    """The live form misspells three questions. Losing them isn't acceptable."""
    report = import_survey(forms_csv(), "responses.csv")
    matched = set(report.matched_items)
    for item_id in FORM_TYPOS:
        assert item_id in matched, f"{item_id} was dropped over a typo"


def test_a_question_mentioning_employees_is_not_read_as_the_headcount_column():
    """
    The bug that cost two questions: the alias "employees" appears inside
    "We provide training opportunities to employees...", and a substring
    match claimed that column as the company-size field.
    """
    report = import_survey(forms_csv(), "responses.csv")
    matched = set(report.matched_items)
    assert "WRK_2" in matched
    assert "CUL_2" in matched

    by_target = {m.target: m.header for m in report.matches}
    assert by_target["employee_band"] == "Number of Employees"


# ---------------------------------------------------------------------------
# Answer formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "written, expected",
    [
        ("Agree", 4), ("agree", 4), ("STRONGLY AGREE", 5),
        ("Strongly Disagree", 1), ("Neutral", 3),
        ("4", 4), (4, 4), ("4 - Agree", 4), ("4 — Agree", 4),
        ("Neither agree nor disagree", 3), (3.0, 3),
        ("", None), (None, None), ("banana", None), (9, None), (True, None),
    ],
)
def test_answers_read_the_same_whether_written_as_words_or_numbers(written, expected):
    assert cfg.parse_rating(written) == expected


def test_word_answers_score_identically_to_numbers():
    """
    The same responses written as words and as digits must land on the same
    score. Note this is not 75: "Agree" on a barrier-worded question means
    less readiness, so the six reverse items pull it down. That's the scoring
    engine working, and it has to work the same from either input format.
    """
    words = import_survey(forms_csv(answer=4), "words.csv")

    # The identical file with 4 in place of "Agree".
    numbers_csv = forms_csv(answer=4).replace(b"Agree", b"4")
    numbers = import_survey(numbers_csv, "numbers.csv")

    from_words = ScoringEngine().score(
        CompanyProfile.from_dict(words.rows[0])
    ).overall_score
    from_numbers = ScoringEngine().score(
        CompanyProfile.from_dict(numbers.rows[0])
    ).overall_score

    assert from_words == pytest.approx(from_numbers)
    assert 0 < from_words < 100


# ---------------------------------------------------------------------------
# Open sector and country
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sector",
    ["Real Estate", "Asset Management", "Events", "Transportation",
     "Financial Services", "Sales", "Education"],
)
def test_sectors_from_the_real_survey_are_accepted(sector):
    """Every one of these came back in the first live run and was rejected."""
    report = import_survey(forms_csv(sector=sector), "a.csv")
    _, profile = profiles_from_report(report)[0]
    assert profile.validate() == []
    assert profile.industry_sector == sector


@pytest.mark.parametrize("country", ["Canada", "Saudi Arabia", "Kenya", "Japan"])
def test_countries_outside_the_shortlist_are_accepted(country):
    report = import_survey(forms_csv(region=country), "a.csv")
    _, profile = profiles_from_report(report)[0]
    assert profile.validate() == []
    assert profile.region == country


def test_shouty_and_lowercase_sectors_group_together():
    """"EDUCATION" and "education" shouldn't come out as two sectors."""
    assert cfg.normalise_category("industry_sector", "EDUCATION") == "Education"
    assert cfg.normalise_category("industry_sector", "education") == "Education"


def test_the_same_country_written_different_ways_becomes_one_country():
    """
    Otherwise a single country splits across several bars in the results.
    "UAE", "Dubai" and "United Arab Emirates" are one place, and the
    breakdowns are only meaningful if they're counted as one.
    """
    for written in ("UAE", "uae", "U.A.E.", "Dubai", "United Arab Emirates"):
        assert cfg.normalise_category("region", written) == "United Arab Emirates"
    for written in ("UK", "England", "Great Britain", "United Kingdom"):
        assert cfg.normalise_category("region", written) == "United Kingdom"


# ---------------------------------------------------------------------------
# Rejecting answers that aren't real
# ---------------------------------------------------------------------------
# No permitted list, but not "anything goes" either. A nonsense value would
# quietly ruin every breakdown that groups by it.

@pytest.mark.parametrize("junk", ["bahab", "asdkjh", "qwerty", "xyz", "Narnia", "123"])
def test_a_country_that_does_not_exist_is_rejected(junk):
    from src.open_value_checks import check_open_value

    cleaned, problem = check_open_value("region", junk)
    assert cleaned is None
    assert problem and "country" in problem.lower()


@pytest.mark.parametrize(
    "country",
    ["Kenya", "Japan", "Saudi Arabia", "Canada", "Nigeria", "Brazil",
     "Singapore", "Phillipines"],
)
def test_any_real_country_is_accepted(country):
    from src.open_value_checks import check_open_value

    cleaned, problem = check_open_value("region", country)
    assert problem is None and cleaned


@pytest.mark.parametrize("junk", ["bahab", "asdkjh", "qwerty", "...", "company"])
def test_a_sector_that_is_not_an_industry_is_rejected(junk):
    from src.open_value_checks import check_open_value

    cleaned, problem = check_open_value("industry_sector", junk)
    assert cleaned is None
    assert problem and "industry" in problem.lower()


@pytest.mark.parametrize(
    "sector",
    ["Real Estate", "Asset Management", "Events", "Transportation",
     "Financial Services", "Sales", "Education",
     "marine engineering consultancy", "halal food logistics",
     "dental clinic", "solar panel installation"],
)
def test_any_genuine_industry_is_accepted_however_it_is_phrased(sector):
    """No list could contain these. The check is that it reads as an industry."""
    from src.open_value_checks import check_open_value

    cleaned, problem = check_open_value("industry_sector", sector)
    assert problem is None and cleaned


def test_nonsense_reaches_the_person_as_a_readable_message():
    profile = CompanyProfile.from_dict({
        "industry_sector": "bahab", "employee_band": "10-49",
        "years_in_operation": "2-5 years", "region": "bahab",
        "current_ai_stage": "Exploring",
        **{item.id: 3 for item in cfg.ALL_ITEMS},
    })
    errors = profile.validate()
    assert len(errors) == 2
    assert any("country" in e.lower() for e in errors)
    assert any("industry" in e.lower() for e in errors)


def test_bare_other_is_sent_back_for_a_specific_answer():
    report = import_survey(forms_csv(sector="Other"), "a.csv")
    _, profile = profiles_from_report(report)[0]
    errors = profile.validate()
    assert any("specific answer" in e for e in errors)


def test_closed_fields_still_reject_nonsense():
    """Size, age and adoption stage are scales, not labels -- they stay closed."""
    profile = CompanyProfile.from_dict({
        "industry_sector": "Robotics", "employee_band": "a few",
        "years_in_operation": "10+ years", "region": "Peru",
        "current_ai_stage": "Exploring",
        **{item.id: 3 for item in cfg.ALL_ITEMS},
    })
    assert any("Employee Band" in e for e in profile.validate())


@pytest.mark.parametrize(
    "written, expected",
    [("250+ employees", "250+"), ("10 to 49", "10-49"), ("Using", "Actively Using"),
     ("over 10 years", "10+ years"), ("pilot", "Piloting")],
)
def test_common_variants_of_the_closed_fields_are_understood(written, expected):
    field = {
        "250+": "employee_band", "10-49": "employee_band",
        "Actively Using": "current_ai_stage", "10+ years": "years_in_operation",
        "Piloting": "current_ai_stage",
    }[expected]
    assert cfg.normalise_category(field, written) == expected


# ---------------------------------------------------------------------------
# File formats
# ---------------------------------------------------------------------------

def test_excel_files_are_accepted():
    """Asking someone to convert to CSV first is a step that exists only for us."""
    from openpyxl import Workbook

    headers = forms_headers()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    row = ["9/1/2026", "Technology", "10-49", "2-5 years", "UAE", "Piloting"]
    row += ["Agree"] * len(cfg.ALL_ITEMS) + ["Cost", "Funding", ""]
    sheet.append(row)

    buffer = io.BytesIO()
    workbook.save(buffer)

    report = import_survey(buffer.getvalue(), "responses.xlsx")
    assert report.error is None
    assert len(set(report.matched_items)) == len(cfg.ALL_ITEMS)
    _, profile = profiles_from_report(report)[0]
    assert profile.validate() == []


def test_a_file_using_the_tools_own_column_codes_still_works():
    """The synthetic generator's format must keep importing."""
    headers = (["company_id"] + list(cfg.CATEGORICAL_FIELDS)
               + [item.id for item in cfg.ALL_ITEMS])
    values = ["SYN0001", "Retail", "10-49", "2-5 years", "UAE", "Exploring"]
    values += ["3"] * len(cfg.ALL_ITEMS)
    data = (",".join(headers) + "\n" + ",".join(values)).encode("utf-8")

    report = import_survey(data, "synthetic.csv")
    assert len(set(report.matched_items)) == len(cfg.ALL_ITEMS)
    _, profile = profiles_from_report(report)[0]
    assert profile.validate() == []


# ---------------------------------------------------------------------------
# Keeping what isn't scored
# ---------------------------------------------------------------------------

def test_open_ended_answers_are_kept_not_discarded():
    report = import_survey(forms_csv(), "a.csv")
    assert len(report.free_text_headers) == 3

    notes = report.rows[0].get("free_text")
    assert notes, "the written answers were thrown away"
    assert any("barrier" in question.lower() for question in notes)


def test_admin_columns_are_ignored_quietly():
    report = import_survey(forms_csv(), "a.csv")
    assert "Timestamp" in report.ignored_headers
    assert "Timestamp" not in report.unmatched_headers


# ---------------------------------------------------------------------------
# Knowing when it's a different survey altogether
# ---------------------------------------------------------------------------

def test_a_different_questionnaire_is_recognised_rather_than_force_fitted():
    """
    A public-sector AI survey was tried against this tool. It measures
    something else, so the honest answer is to say so -- not to squeeze a
    score out of whatever columns happen to line up.
    """
    headers = ["Timestamp", "Q1. Country Selection"] + [
        f"Q{n}. Our agency has a policy covering area {n}." for n in range(2, 13)
    ]
    values = ["2024-09-01", "Saudi Arabia"] + ["5"] * 11
    data = (",".join(f'"{h}"' for h in headers) + "\n"
            + ",".join(f'"{v}"' for v in values)).encode("utf-8")

    report = import_survey(data, "other_survey.xlsx".replace("xlsx", "csv"))
    assert report.looks_like_a_different_survey
    assert report.item_coverage < 0.25


def test_an_empty_file_reports_a_problem_instead_of_crashing():
    assert import_survey(b"", "a.csv").error
    assert import_survey(b"just,headers,here", "a.csv").error


# ---------------------------------------------------------------------------
# Header parsing details
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "header, expected",
    [
        ("Data Readiness [Our data is tidy.]", "Our data is tidy."),
        ("Budget - We have a budget.", "We have a budget."),
        ("We have a budget.", "We have a budget."),
    ],
)
def test_question_text_is_pulled_out_of_the_header(header, expected):
    assert _question_text(header) == expected


def test_two_columns_cannot_claim_the_same_question():
    headers = ["BUD_1", "Budget & Financial Readiness [We have a dedicated "
               "budget for AI adoption or experimentation.]"]
    matches, leftover, _, _ = match_columns(headers)
    targets = [m.target for m in matches]
    assert targets.count("BUD_1") == 1
    assert len(leftover) == 1


# ---------------------------------------------------------------------------
# Matching by meaning
# ---------------------------------------------------------------------------
# String similarity handles this questionnaire retyped. It cannot handle the
# same question asked in someone else's words, which is what these cover.

def test_differently_worded_questions_match_on_meaning():
    from src.survey_import import meaning_similarity

    pairs = [
        ("Our agency has sufficient and reliable IT infrastructure "
         "(broadband, servers, cloud services).", "technology"),
        ("Adequate budget and funding are allocated for AI projects.", "budget"),
        ("Senior management actively champions AI adoption.", "leadership"),
        ("Employees can acquire the skills required through training.", "workforce"),
        ("We adhere to legal and ethical standards and monitor for bias.",
         "governance"),
    ]
    for text, expected_factor in pairs:
        best_factor, best = "", 0.0
        for factor in cfg.FACTORS:
            score = max(meaning_similarity(text, item.text) for item in factor.items)
            if score > best:
                best_factor, best = factor.id, score
        assert best_factor == expected_factor, (
            f"{text!r} landed on {best_factor}, expected {expected_factor}"
        )


def test_meaning_matching_ignores_shared_filler_words():
    """
    Every question says "AI" and "our company". Without IDF weighting those
    shared words make everything look similar to everything else.
    """
    from src.survey_import import meaning_similarity

    budget = cfg.ITEMS_BY_ID["BUD_1"].text
    culture = cfg.ITEMS_BY_ID["CUL_1"].text
    assert meaning_similarity(budget, budget) > 0.99
    assert meaning_similarity(budget, culture) < 0.4


def test_a_foreign_survey_is_compared_not_scored():
    """
    A different instrument gets an analysis of how it relates to the seven
    factors. It does not get a readiness score, because its questions measure
    different things and a number built from them would not be this measure.
    """
    headers = ["Timestamp", "Q1. Country Selection",
               "Q2. Our agency has reliable IT infrastructure and cloud servers.",
               "Q3. Adequate budget and funding are allocated for AI projects.",
               "Q4. Senior management champions AI adoption across the agency.",
               "Q5. Implementing AI has improved citizen satisfaction greatly."]
    values = ["2024-09-01", "Saudi Arabia", "5", "4", "4", "3"]
    data = (",".join(f'"{h}"' for h in headers) + "\n"
            + ",".join(f'"{v}"' for v in values)).encode("utf-8")

    report = import_survey(data, "other.csv")
    assert report.looks_like_a_different_survey
    assert report.direct_coverage == 0.0

    analysis = report.compare_to_framework()
    assert "technology" in analysis["covered"]
    assert "budget" in analysis["covered"]
    assert "leadership" in analysis["covered"]
    # Nothing in that file asks about data quality or company culture.
    assert "data" in analysis["not_covered"]
    assert "culture" in analysis["not_covered"]


def test_meaning_matches_never_silently_fill_a_foreign_file():
    """
    A suggestion is not data. On a file that is a different instrument the
    proposed pairings are kept for analysis but no answer is imported from
    them, or the tool would be inventing responses.
    """
    headers = ["Q1. Our agency has reliable IT infrastructure and cloud servers.",
               "Q2. Adequate budget and funding are allocated for AI projects."]
    data = (",".join(f'"{h}"' for h in headers) + "\n" + '"5","4"').encode("utf-8")

    report = import_survey(data, "other.csv")
    assert report.looks_like_a_different_survey
    answered = [key for key in report.rows[0] if key in cfg.ITEMS_BY_ID]
    assert answered == [], f"values were imported from guesses: {answered}"


# ---------------------------------------------------------------------------
# Reading the tool's own output back in
# ---------------------------------------------------------------------------

def test_the_readable_csv_this_tool_writes_can_be_read_back():
    """
    The readable export failed to import: its headers carry the factor name,
    the item code and a [REVERSE-WORDED] tag, and the six barrier questions
    were dropped over that tag alone. A tool that can't read its own output
    is not much of a tool.
    """
    import tempfile, os
    from src.synthetic_data import generate_dataset, write_readable_csv

    rows = generate_dataset(n=12, seed=3)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "readable.csv")
        write_readable_csv(rows, path)
        data = open(path, "rb").read()

    report = import_survey(data, "readable.csv")
    assert len(set(report.matched_items)) == len(cfg.ALL_ITEMS), (
        f"dropped {report.missing_items}"
    )
    pairs = profiles_from_report(report)
    for identifier, profile in pairs:
        assert profile.validate() == [], f"{identifier}: {profile.validate()}"


def test_spelled_out_employee_bands_read_back():
    """The readable CSV writes "10 to 49 employees" to dodge Excel's date guess."""
    for written, expected in (
        ("1 to 9 employees", "1-9"), ("10 to 49 employees", "10-49"),
        ("50 to 249 employees", "50-249"), ("250+ employees", "250+"),
    ):
        assert cfg.normalise_category("employee_band", written) == expected


def test_an_item_code_anywhere_in_the_header_is_found():
    from src.survey_import import find_item_code

    assert find_item_code("Budget & Financial Readiness | BUD_1 | We have…") == "BUD_1"
    assert find_item_code("GOV_5") == "GOV_5"
    assert find_item_code("Number of Employees") is None


# ---------------------------------------------------------------------------
# Partial coverage
# ---------------------------------------------------------------------------

def test_a_dataset_covering_some_factors_is_scored_on_those():
    """
    Refusing a dataset outright because it misses two factors throws away a
    real reading on the five it covers.
    """
    from src.scoring_engine import ScoringEngine

    answers = {}
    for factor_id in ("budget", "technology", "leadership"):
        for item in cfg.FACTORS_BY_ID[factor_id].items:
            answers[item.id] = 4

    profile = CompanyProfile.from_dict({
        "industry_sector": "Retail", "employee_band": "10-49",
        "years_in_operation": "2-5 years", "region": "UAE",
        "current_ai_stage": "Exploring", **answers,
    })
    results = ScoringEngine().score(profile, allow_partial=True)

    assert results.partial
    assert set(results.factor_scores) == {"budget", "technology", "leadership"}
    assert "data" not in results.factor_scores, "absent factor scored as zero"


def test_absent_factors_do_not_drag_the_overall_score_down():
    """
    The trap this avoids: treating "not asked" as "answered badly". The
    overall is re-weighted across the factors present, so a partial read of
    three strong factors reports strong, not weak.
    """
    from src.scoring_engine import ScoringEngine

    engine = ScoringEngine()
    base = {"industry_sector": "Retail", "employee_band": "10-49",
            "years_in_operation": "2-5 years", "region": "UAE",
            "current_ai_stage": "Exploring"}

    full = engine.score(CompanyProfile.from_dict(
        {**base, **{i.id: 4 for i in cfg.ALL_ITEMS}}))

    subset = ("budget", "technology", "leadership")
    partial_answers = {}
    for factor_id in subset:
        for item in cfg.FACTORS_BY_ID[factor_id].items:
            partial_answers[item.id] = 4
    partial = engine.score(
        CompanyProfile.from_dict({**base, **partial_answers}), allow_partial=True)

    expected = sum(full.factor(f).score for f in subset) / len(subset)
    assert partial.overall_score == pytest.approx(expected)
    assert partial.overall_score > 50, "a partial read of decent answers read as weak"


def test_a_completed_assessment_is_unaffected_by_partial_support():
    from src.scoring_engine import ScoringEngine

    profile = CompanyProfile.from_dict({
        "industry_sector": "Retail", "employee_band": "10-49",
        "years_in_operation": "2-5 years", "region": "UAE",
        "current_ai_stage": "Exploring",
        **{i.id: 4 for i in cfg.ALL_ITEMS},
    })
    results = ScoringEngine().score(profile)
    assert results.partial is False
    assert len(results.factor_scores) == len(cfg.FACTORS)
