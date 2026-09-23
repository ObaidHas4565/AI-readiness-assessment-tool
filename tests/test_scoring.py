"""
Test suite for steps 1-3.

These tests are the cheap safety net referred to in the build plan: they let
the scoring logic be verified against known inputs without needing synthetic
data, a dashboard, or any manual checking.

Run from the project root with:   pytest -v
"""

import pytest

from src import score_configuration as cfg
from src.company_profile import CompanyProfile, ValidationError
from src.recommendation_engine import RecommendationEngine, severity_for
from src.scoring_engine import ScoringEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONTEXT = {
    "industry_sector": "Technology",
    "employee_band": "10-49",
    "years_in_operation": "2-5 years",
    "region": "UAE",
    "current_ai_stage": "Exploring",
}


def profile_with(value: int = 3, overrides: dict | None = None) -> CompanyProfile:
    """A complete profile where every item is answered with `value`."""
    responses = {item.id: value for item in cfg.ALL_ITEMS}
    if overrides:
        responses.update(overrides)
    return CompanyProfile.from_dict({**BASE_CONTEXT, **responses})


# ---------------------------------------------------------------------------
# Configuration integrity
# ---------------------------------------------------------------------------

def test_configuration_is_internally_consistent():
    assert cfg.validate_configuration() == []


def test_survey_shape_matches_instrument():
    """7 factors and 32 rating items, as per the survey document."""
    assert len(cfg.FACTORS) == 7
    assert len(cfg.ALL_ITEMS) == 32


def test_expected_reverse_items():
    """The reverse-worded items must be exactly these, or every score shifts."""
    reverse_ids = {i.id for i in cfg.ALL_ITEMS if i.reverse}
    assert reverse_ids == {"BUD_2", "WRK_3", "LDR_1", "DAT_5", "TEC_5", "GOV_5"}


# ---------------------------------------------------------------------------
# Anchor points: the scale behaves as documented
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "answer, expected_overall",
    [
        (1, 0.0),    # all "Strongly Disagree" on positive items
        (3, 50.0),   # all "Neutral"
        (5, 100.0),  # all "Strongly Agree" on positive items
    ],
)
def test_uniform_answers_hit_scale_anchors(answer, expected_overall):
    """
    A uniform answer of 3 must give exactly 50, because Neutral is the midpoint
    for reverse and non-reverse items alike. Uniform 1 and 5 only reach the
    extremes once reverse items are re-coded -- which is the point of the test:
    it fails loudly if reverse coding is dropped.
    """
    responses = {}
    for item in cfg.ALL_ITEMS:
        # Answer each item in the direction that means "most ready".
        responses[item.id] = (cfg.REVERSE_PIVOT - answer) if item.reverse else answer

    results = ScoringEngine().score(CompanyProfile.from_dict({**BASE_CONTEXT, **responses}))
    assert results.overall_score == pytest.approx(expected_overall)


def test_reverse_coding_inverts_that_item_only():
    """Agreeing that 'cost is the barrier' must lower, not raise, the score."""
    neutral = ScoringEngine().score(profile_with(3))
    agrees_cost_is_barrier = ScoringEngine().score(profile_with(3, {"BUD_2": 5}))

    assert agrees_cost_is_barrier.factor("budget").score < neutral.factor("budget").score
    # No other factor should move.
    assert agrees_cost_is_barrier.factor("data").score == neutral.factor("data").score


# ---------------------------------------------------------------------------
# Scoring behaviour
# ---------------------------------------------------------------------------

def test_weighted_overall_equals_sum_of_contributions():
    results = ScoringEngine().score(profile_with(4))
    expected = sum(f.weighted_contribution for f in results.factor_scores.values())
    assert results.overall_score == pytest.approx(expected)


def test_tier_assignment_matches_bands():
    engine = ScoringEngine()
    assert engine.score(profile_with(1)).readiness_tier == "Emerging"
    assert engine.score(profile_with(3)).readiness_tier == "Developing"
    assert engine.score(profile_with(5)).readiness_tier == "Advanced"


def test_identical_input_gives_identical_output():
    """Reliability requirement: scoring is deterministic."""
    engine = ScoringEngine()
    a = engine.score(profile_with(4, {"DAT_1": 2, "GOV_3": 1}))
    b = engine.score(profile_with(4, {"DAT_1": 2, "GOV_3": 1}))
    assert a.to_dict() == b.to_dict()


def test_strengths_and_barriers_are_selected_correctly():
    """A company strong on budget and weak on data should report exactly that."""
    responses = {item.id: 3 for item in cfg.ALL_ITEMS}
    for item in cfg.FACTORS_BY_ID["budget"].items:
        responses[item.id] = 1 if item.reverse else 5   # -> 100
    for item in cfg.FACTORS_BY_ID["data"].items:
        responses[item.id] = 5 if item.reverse else 1   # -> 0

    results = ScoringEngine().score(CompanyProfile.from_dict({**BASE_CONTEXT, **responses}))

    assert results.factor("budget").score == pytest.approx(100.0)
    assert results.factor("data").score == pytest.approx(0.0)
    assert "Budget & Financial Readiness" in [f.name for f in results.strengths]
    assert "Data Readiness" in [f.name for f in results.barriers]


def test_item_barriers_report_lowest_scoring_subfactors():
    results = ScoringEngine().score(profile_with(4, {"LDR_3": 1, "TEC_3": 1}))
    flagged = {i.item_id for i in results.item_barriers}
    assert {"LDR_3", "TEC_3"} <= flagged


def test_barriers_are_ranked_by_weighted_impact():
    """The worst-scoring barrier should be listed first under equal weights."""
    responses = {item.id: 3 for item in cfg.ALL_ITEMS}
    for item in cfg.FACTORS_BY_ID["data"].items:
        responses[item.id] = 5 if item.reverse else 1        # -> 0
    for item in cfg.FACTORS_BY_ID["culture"].items:
        responses[item.id] = 4 if item.reverse else 2        # -> 25

    results = ScoringEngine().score(CompanyProfile.from_dict({**BASE_CONTEXT, **responses}))
    assert results.barriers[0].factor_id == "data"


# ---------------------------------------------------------------------------
# Validation (FR2)
# ---------------------------------------------------------------------------

def test_complete_profile_is_valid():
    assert profile_with(3).validate() == []


def test_missing_answers_are_rejected():
    profile = profile_with(3)
    del profile.responses["GOV_1"]
    errors = profile.validate()
    assert any("GOV_1" in e for e in errors)


def test_out_of_range_answers_are_rejected():
    profile = profile_with(3, {"DAT_2": 9})
    assert any("out of range" in e for e in profile.validate())


def test_non_integer_answer_is_rejected():
    profile = profile_with(3)
    profile.responses["DAT_2"] = "high"
    assert any("DAT_2" in e for e in profile.validate())


def test_missing_categorical_field_is_rejected():
    profile = profile_with(3)
    profile.region = None
    assert any("Region" in e for e in profile.validate())


def test_invalid_categorical_value_is_rejected():
    profile = profile_with(3)
    profile.employee_band = "500-1000"
    assert any("Employee Band" in e for e in profile.validate())


def test_scoring_an_invalid_profile_raises():
    profile = profile_with(3)
    del profile.responses["BUD_1"]
    with pytest.raises(ValidationError):
        ScoringEngine().score(profile)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def test_weak_factor_produces_recommendations():
    responses = {item.id: 3 for item in cfg.ALL_ITEMS}
    for item in cfg.FACTORS_BY_ID["governance"].items:
        responses[item.id] = 5 if item.reverse else 1

    results = ScoringEngine().score(CompanyProfile.from_dict({**BASE_CONTEXT, **responses}))
    recs = RecommendationEngine().recommend(results)

    assert recs, "A company scoring 0 on governance must receive recommendations."
    assert any(r.factor_id == "governance" for r in recs)
    assert any(r.severity == "critical" for r in recs)


def test_strong_company_receives_no_recommendations():
    responses = {
        item.id: (cfg.REVERSE_PIVOT - 5) if item.reverse else 5
        for item in cfg.ALL_ITEMS
    }
    results = ScoringEngine().score(CompanyProfile.from_dict({**BASE_CONTEXT, **responses}))
    assert RecommendationEngine().recommend(results) == []


def test_recommendations_are_priority_ordered_and_capped():
    results = ScoringEngine().score(profile_with(1))
    recs = RecommendationEngine().recommend(results)

    assert len(recs) <= cfg.MAX_RECOMMENDATIONS
    priorities = [r.priority for r in recs]
    assert priorities == sorted(priorities, reverse=True)


def test_recommendations_are_attached_to_results():
    results = ScoringEngine().score(profile_with(2))
    returned = RecommendationEngine().recommend(results)
    assert results.recommendations == returned


def test_item_level_recommendation_is_triggered_by_its_item():
    results = ScoringEngine().score(profile_with(4, {"DAT_3": 1}))
    recs = RecommendationEngine().recommend(results)
    assert any(r.triggered_by_item == "DAT_3" for r in recs)


def test_every_item_has_an_action_defined():
    """Guards against adding a survey item and forgetting its recommendation."""
    from src.recommendation_engine import ITEM_ACTIONS

    missing = [i.id for i in cfg.ALL_ITEMS if i.id not in ITEM_ACTIONS]
    assert missing == []


def test_every_factor_has_rules_for_all_severities():
    from src.recommendation_engine import FACTOR_RULES

    for factor in cfg.FACTORS:
        assert factor.id in FACTOR_RULES, f"No rules for factor {factor.id}"
        for severity in ("critical", "moderate", "refine"):
            assert severity in FACTOR_RULES[factor.id]


@pytest.mark.parametrize(
    "score, expected",
    [(0, "critical"), (34.9, "critical"), (35, "moderate"),
     (49.9, "moderate"), (50, "refine"), (69.9, "refine"), (70, None), (100, None)],
)
def test_severity_boundaries(score, expected):
    assert severity_for(score) == expected


# ---------------------------------------------------------------------------
# Export-facing serialisation
# ---------------------------------------------------------------------------

def test_to_dict_contains_everything_the_export_needs():
    results = ScoringEngine().score(profile_with(2))
    RecommendationEngine().recommend(results)
    payload = results.to_dict()

    assert set(payload) >= {
        "overall_score", "readiness_tier", "tier_description", "context",
        "factors", "items", "strengths", "barriers", "item_barriers",
        "recommendations",
    }
    assert len(payload["factors"]) == 7
    assert len(payload["items"]) == 32


def test_item_barriers_are_spread_across_factors():
    """
    A single very weak factor must not fill the entire subfactor list, or the
    profile reports the same problem repeatedly and hides other gaps.
    """
    responses = {item.id: 3 for item in cfg.ALL_ITEMS}
    for factor_id in ("data", "governance"):
        for item in cfg.FACTORS_BY_ID[factor_id].items:
            responses[item.id] = 5 if item.reverse else 1

    results = ScoringEngine().score(CompanyProfile.from_dict({**BASE_CONTEXT, **responses}))

    counts = {}
    for item in results.item_barriers:
        counts[item.factor_id] = counts.get(item.factor_id, 0) + 1

    assert max(counts.values()) <= cfg.MAX_ITEM_BARRIERS_PER_FACTOR
    assert len(counts) > 1, "Gaps should span more than one factor."
