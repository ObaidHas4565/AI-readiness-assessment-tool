"""
Tests for the synthetic data generator.

These guard the property that actually matters: generated rows must be
indistinguishable in FORM from real survey responses, so that anything which
would break on real data breaks here first.
"""

import csv
import os
import tempfile

import pytest

from src import score_configuration as cfg
from src.recommendation_engine import RecommendationEngine
from src.scoring_engine import ScoringEngine
from src.synthetic_data import (
    READINESS_PROFILES,
    CSV_FIELDNAMES,
    generate_company,
    generate_dataset,
    load_profiles_from_csv,
    write_csv,
)


def test_RP_weights_sum_to_one():
    total = sum(a.weight for a in READINESS_PROFILES)
    assert total == pytest.approx(1.0, abs=1e-9)


def test_every_RP_covers_every_factor():
    for profile in READINESS_PROFILES:
        for factor in cfg.FACTORS:
            assert factor.id in profile.factor_levels, (
                f"{profile.name} is missing a level for {factor.id}"
            )


def test_generated_rows_are_valid_profiles():
    """Every generated company must pass the same validation as real input."""
    from src.company_profile import CompanyProfile

    for row in generate_dataset(n=50, seed=1):
        profile = CompanyProfile.from_dict(row)
        assert profile.validate() == [], profile.validate()


def test_all_answers_are_in_range():
    for row in generate_dataset(n=50, seed=2):
        for item in cfg.ALL_ITEMS:
            assert cfg.LIKERT_MIN <= row[item.id] <= cfg.LIKERT_MAX


def test_generation_is_reproducible():
    assert generate_dataset(n=20, seed=99) == generate_dataset(n=20, seed=99)


def test_different_seeds_give_different_data():
    assert generate_dataset(n=20, seed=1) != generate_dataset(n=20, seed=2)


def test_reverse_items_are_inverted_in_raw_output():
    """
    A strong readiness profile must ANSWER LOW on barrier-worded items.

    This is the property most likely to be got wrong silently: if reverse
    items were written un-inverted, every score would still look plausible
    but would be wrong.
    """
    import random

    advanced = next(p for p in READINESS_PROFILES if p.name == "Advanced_Adopter")
    rng = random.Random(5)
    rows = [generate_company(rng, read_profile=advanced) for _ in range(40)]

    for item in cfg.ALL_ITEMS:
        values = [row[item.id] for row in rows]
        average = sum(values) / len(values)
        if item.reverse:
            assert average < 2.5, f"{item.id} should be answered LOW by a ready firm"
        else:
            assert average > 3.5, f"{item.id} should be answered HIGH by a ready firm"


def test_RP_land_in_expected_score_regions():
    """Weak readiness profiles must score low and strong ones high, or the generator
    and the scoring engine disagree about what readiness means."""
    import random

    engine = ScoringEngine()
    from src.company_profile import CompanyProfile

    expectations = {"Early_Stage_Adopter": (0, 40), "Advanced_Adopter": (70, 100)}

    for name, (low, high) in expectations.items():
        profile = next(p for p in READINESS_PROFILES if p.name == name)
        rng = random.Random(11)
        scores = [
            engine.score(CompanyProfile.from_dict(generate_company(rng, profile))).overall_score
            for _ in range(30)
        ]
        average = sum(scores) / len(scores)
        assert low <= average <= high, f"{name} averaged {average:.1f}, expected {low}-{high}"


def test_dataset_spans_all_three_tiers():
    """A test dataset that never produces an Advanced company cannot exercise
    the tier logic, so this is a requirement of the generator, not a nicety."""
    engine = ScoringEngine()
    from src.company_profile import CompanyProfile

    tiers = {
        engine.score(CompanyProfile.from_dict(row)).readiness_tier
        for row in generate_dataset(n=200, seed=42)
    }
    assert tiers == {"Emerging", "Developing", "Advanced"}


def test_csv_round_trip_preserves_answers():
    rows = generate_dataset(n=25, seed=7)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "synthetic.csv")
        assert write_csv(rows, path) == 25

        with open(path, newline="", encoding="utf-8") as handle:
            assert csv.DictReader(handle).fieldnames == CSV_FIELDNAMES

        loaded = load_profiles_from_csv(path)

    assert len(loaded) == 25
    for row, (identifier, profile) in zip(rows, loaded):
        assert identifier == row["company_id"]
        assert profile.validate() == []
        for item in cfg.ALL_ITEMS:
            assert profile.responses[item.id] == row[item.id]


def test_whole_dataset_scores_without_error():
    """End-to-end: generate, score, recommend, for every row."""
    from src.company_profile import CompanyProfile

    scoring_engine = ScoringEngine()
    recommendation_engine = RecommendationEngine()

    for row in generate_dataset(n=100, seed=3):
        results = scoring_engine.score(CompanyProfile.from_dict(row))
        recommendation_engine.recommend(results)
        assert 0.0 <= results.overall_score <= 100.0
        assert len(results.recommendations) <= cfg.MAX_RECOMMENDATIONS


# ---------------------------------------------------------------------------
# Validation against realistically messy data
# ---------------------------------------------------------------------------
# The clean dataset alone gives false confidence: the tool looks robust simply
# because nothing malformed was ever sent to it. These tests send it the
# defects a real Google Forms export actually produces.

def test_every_invalid_row_is_rejected():
    from src.company_profile import CompanyProfile
    from src.synthetic_data import generate_invalid_rows

    for description, row in generate_invalid_rows():
        profile = CompanyProfile.from_dict(row)
        errors = profile.validate()
        assert errors, f"validation accepted a bad row: {description}"


def test_invalid_rows_cannot_be_scored():
    """A malformed row must raise, never silently produce a score."""
    from src.company_profile import CompanyProfile, ValidationError
    from src.synthetic_data import generate_invalid_rows

    engine = ScoringEngine()
    for description, row in generate_invalid_rows():
        with pytest.raises(ValidationError):
            engine.score(CompanyProfile.from_dict(row))


def test_invalid_row_errors_name_the_offending_field():
    """Error messages must be specific enough to act on, not just 'invalid'."""
    from src.company_profile import CompanyProfile
    from src.synthetic_data import generate_invalid_rows

    cases = dict(generate_invalid_rows())

    out_of_range = CompanyProfile.from_dict(cases["out-of-range answer (scale mis-mapped on import)"])
    assert any("out of range" in e for e in out_of_range.validate())

    blank_sector = CompanyProfile.from_dict(cases["sector left blank"])
    assert any("Industry Sector" in e for e in blank_sector.validate())

    vague = CompanyProfile.from_dict(cases["bare 'Other' with nothing specified"])
    assert any("specific answer" in e for e in vague.validate())

    missing_region = CompanyProfile.from_dict(cases["missing required context field"])
    assert any("Region" in e for e in missing_region.validate())


# ---------------------------------------------------------------------------
# Companion artefacts
# ---------------------------------------------------------------------------

def test_data_dictionary_documents_every_column():
    from src.synthetic_data import write_data_dictionary

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "DATA_DICTIONARY.md")
        write_data_dictionary(path)
        text = open(path, encoding="utf-8").read()

    for item in cfg.ALL_ITEMS:
        assert f"`{item.id}`" in text, f"{item.id} missing from the data dictionary"
        assert item.text in text, f"question text for {item.id} missing"
    for field in cfg.CATEGORICAL_FIELDS:
        assert f"`{field}`" in text
    for factor in cfg.FACTORS:
        assert factor.name in text


def test_data_dictionary_marks_reverse_items():
    from src.synthetic_data import write_data_dictionary

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "d.md")
        write_data_dictionary(path)
        lines = open(path, encoding="utf-8").read().splitlines()

    for item in cfg.ALL_ITEMS:
        row = next(l for l in lines if l.startswith(f"| `{item.id}`"))
        assert ("**Yes**" in row) == item.reverse, f"{item.id} reverse flag wrong"


def test_readable_csv_has_question_text_headers_and_labels():
    from src.synthetic_data import write_readable_csv

    rows = generate_dataset(n=5, seed=4)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "readable.csv")
        write_readable_csv(rows, path)
        with open(path, newline="", encoding="utf-8") as handle:
            table = list(csv.reader(handle))

    header, first = table[0], table[1]
    assert any("We have a dedicated budget" in h for h in header)
    assert any("[REVERSE-WORDED]" in h for h in header)
    # Values carry their word label, e.g. "4 - Agree"
    assert any(" - " in cell and cell.split(" - ")[0].isdigit() for cell in first)
    assert len(table) == 6  # header + 5 rows


def test_readable_csv_is_safe_from_excel_date_conversion():
    """
    Excel silently turns "1-9" into 01-Sep and "10-49" into Oct-49 when a CSV
    is opened directly. The readable CSV exists to be opened in Excel, so no
    value in it may look like a date to Excel's type guesser.
    """
    from src.synthetic_data import write_readable_csv

    rows = generate_dataset(n=60, seed=8)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "readable.csv")
        write_readable_csv(rows, path)
        with open(path, newline="", encoding="utf-8") as handle:
            table = list(csv.reader(handle))

    header, data = table[0], table[1:]
    band_index = header.index("Employee Band")
    values = {row[band_index] for row in data}

    # Nothing of the form <digits>-<digits>, which is what Excel date-parses.
    import re
    for value in values:
        assert not re.fullmatch(r"\d+-\d+", value), (
            f"{value!r} will be converted to a date by Excel"
        )
    assert values == {
        "1 to 9 employees", "10 to 49 employees",
        "50 to 249 employees", "250+ employees",
    }


def test_coded_csv_keeps_the_original_survey_values():
    """
    The Excel-safety rewrite must apply ONLY to the readable copy. The coded
    CSV is the tool's input and must carry the survey's exact category values,
    or validation would reject it.
    """
    rows = generate_dataset(n=40, seed=9)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "coded.csv")
        write_csv(rows, path)
        with open(path, newline="", encoding="utf-8") as handle:
            values = {row["employee_band"] for row in csv.DictReader(handle)}

        assert values <= set(cfg.EMPLOYEE_BANDS)
        for _, profile in load_profiles_from_csv(path):
            assert profile.validate() == []
