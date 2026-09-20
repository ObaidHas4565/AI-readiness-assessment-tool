"""
Tests for the factor influence analysis.

Two things are being checked here, and they are different in kind.

The statistics helpers are checked against values worked out by hand, because
a correlation function that is quietly wrong would produce a plausible-looking
table and there would be nothing to notice.

The analysis itself is checked against data built to contain a known answer:
a factor deliberately made to track the outcome should come out on top, an
item deliberately flipped should be flagged, and a sample with no variation
should refuse to report a correlation rather than invent one.
"""

from __future__ import annotations

import math

import pytest

from src import score_configuration as cfg
from src.company_profile import CompanyProfile
from src.influence_analysis import (
    EQUAL_WEIGHTS,
    analyse,
    compare_weighting,
    corrected_item_total,
    cronbach_alpha,
    emphasise,
    format_report,
    mean,
    overall_under,
    pearson,
    permutation_p,
    ranks,
    spearman,
    stdev,
)
from src.scoring_engine import ScoringEngine

ENGINE = ScoringEngine()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def build(answers, stage="Exploring", **overrides):
    """
    A complete, valid profile.

    `answers` maps a factor id to the value every item in that factor gets.
    Anything not named is answered 3, so a test only has to state the part it
    cares about. Values are raw -- reverse-coded items are flipped by the
    engine, exactly as with a real response.
    """
    responses = {}
    for factor in cfg.FACTORS:
        value = answers.get(factor.id, 3)
        for item in factor.items:
            responses[item.id] = value
    responses.update(overrides.pop("responses", {}))
    return CompanyProfile.from_dict({
        "industry_sector": "Technology",
        "employee_band": "10-49",
        "years_in_operation": "2-5 years",
        "region": "UAE",
        "current_ai_stage": stage,
        **responses,
        **overrides,
    })


def coherent(factor_id, value):
    """
    Raw answers for one factor from a respondent answering consistently.

    A company that is genuinely ready agrees with the positively-worded items
    and *disagrees* with the barrier-worded ones, so the raw answer to a
    reverse item is the mirror of the rest. After the engine re-codes them,
    every item in the factor lands on the same adjusted value.

    This matters: handing every item the same raw number instead would make
    the reverse items point the opposite way once re-coded, and the analysis
    would correctly flag them -- see the straight-lining test below.
    """
    return {
        item.id: (cfg.REVERSE_PIVOT - value) if item.reverse else value
        for item in cfg.FACTORS_BY_ID[factor_id].items
    }


def score_all(profiles):
    return [ENGINE.score(p, validate=False, allow_partial=True) for p in profiles]


# ---------------------------------------------------------------------------
# the statistics, against values worked out by hand
# ---------------------------------------------------------------------------

def test_a_perfect_straight_line_correlates_at_one():
    assert pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) == pytest.approx(1.0)
    assert pearson([1, 2, 3, 4, 5], [10, 8, 6, 4, 2]) == pytest.approx(-1.0)


def test_pearson_matches_a_hand_worked_example():
    # x = 1,2,3,4,5  y = 2,4,5,4,5 -> r = 0.8 / sqrt(1 * ...) worked out below.
    # deviations: x -2,-1,0,1,2   y -2,0,1,0,1
    # sum xy = 4 + 0 + 0 + 0 + 2 = 6 ; sum x^2 = 10 ; sum y^2 = 6
    expected = 6 / math.sqrt(10 * 6)
    assert pearson([1, 2, 3, 4, 5], [2, 4, 5, 4, 5]) == pytest.approx(expected)


def test_a_flat_series_has_no_correlation_rather_than_zero():
    # Everyone answering the same thing gives a correlation that is undefined,
    # not a correlation of nothing. Returning 0.0 here would read as "measured
    # and found unrelated", which is a different claim.
    assert pearson([5, 5, 5, 5], [1, 2, 3, 4]) is None
    assert spearman([5, 5, 5, 5], [1, 2, 3, 4]) is None


def test_too_few_points_is_refused():
    assert pearson([1, 2], [3, 4]) is None


def test_ties_share_the_average_rank():
    assert ranks([10, 20, 20, 40]) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_ignores_the_shape_of_the_curve():
    # Monotonic but strongly curved: Spearman sees 1.0, Pearson does not.
    xs = [1, 2, 3, 4, 5]
    ys = [1, 4, 9, 16, 25]
    assert spearman(xs, ys) == pytest.approx(1.0)
    assert pearson(xs, ys) < 1.0


def test_mean_and_stdev_agree_with_the_arithmetic():
    assert mean([2, 4, 6]) == pytest.approx(4.0)
    # sample sd of 2,4,6: deviations -2,0,2 -> var = 8/2 = 4 -> sd = 2
    assert stdev([2, 4, 6]) == pytest.approx(2.0)


def test_the_permutation_test_gives_the_same_answer_twice():
    xs = [1, 2, 3, 4, 5, 6, 7, 8]
    ys = [2, 1, 4, 3, 6, 5, 8, 7]
    observed = pearson(xs, ys)
    first = permutation_p(xs, ys, observed, use_ranks=False, trials=200)
    second = permutation_p(xs, ys, observed, use_ranks=False, trials=200)
    assert first == second


def test_a_strong_relationship_gets_a_small_p_and_a_weak_one_does_not():
    strong_x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    strong_y = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    noisy_y = [5, 3, 8, 1, 9, 2, 7, 4, 6, 5]

    strong_p = permutation_p(
        strong_x, strong_y, pearson(strong_x, strong_y),
        use_ranks=False, trials=500,
    )
    noisy_p = permutation_p(
        strong_x, noisy_y, pearson(strong_x, noisy_y),
        use_ranks=False, trials=500,
    )
    assert strong_p < 0.01
    assert noisy_p > strong_p


# ---------------------------------------------------------------------------
# reliability, and the polarity check it exists for
# ---------------------------------------------------------------------------

def test_items_that_move_together_give_a_high_alpha():
    columns = [
        [1, 2, 3, 4, 5],
        [1, 2, 3, 4, 5],
        [2, 2, 3, 4, 5],
    ]
    assert cronbach_alpha(columns) > 0.9


def test_unrelated_items_give_a_low_alpha():
    columns = [
        [1, 5, 2, 4, 3],
        [4, 2, 5, 1, 3],
        [3, 3, 1, 5, 2],
    ]
    assert cronbach_alpha(columns) < 0.5


def test_alpha_needs_at_least_two_items():
    assert cronbach_alpha([[1, 2, 3]]) is None


def test_an_item_pointing_the_wrong_way_correlates_negatively():
    # Three items agree; the fourth is their mirror image, which is what a
    # mis-polarised Likert item looks like once everything is reverse-coded.
    columns = [
        [1, 2, 3, 4, 5],
        [1, 2, 3, 4, 5],
        [1, 2, 3, 4, 5],
        [5, 4, 3, 2, 1],
    ]
    assert corrected_item_total(columns, 0) > 0.9
    assert corrected_item_total(columns, 3) < 0


def test_a_rest_that_never_moves_gives_no_correlation():
    # Two items that are exact mirrors sum to a constant, so there is nothing
    # for the third to correlate against. That has to come back undefined
    # rather than as a number.
    columns = [
        [1, 2, 3, 4, 5],
        [1, 2, 3, 4, 5],
        [5, 4, 3, 2, 1],
    ]
    assert corrected_item_total(columns, 0) is None


def test_an_item_is_never_correlated_against_itself():
    # If the item were included in its own total the third column here would
    # come back positive, because it dominates the sum.
    columns = [
        [1, 1, 1, 1, 2],
        [1, 1, 1, 1, 2],
        [50, 40, 30, 20, 10],
    ]
    assert corrected_item_total(columns, 2) < 0


# ---------------------------------------------------------------------------
# re-weighting
# ---------------------------------------------------------------------------

def test_equal_weights_reproduce_the_engines_own_overall_score():
    # The whole sensitivity analysis rests on this. If recomputing the overall
    # score from factor scores did not match the ScoringEngine, every shift
    # reported would be measured against the wrong baseline.
    for answers in ({}, {"data": 1}, {"budget": 5, "governance": 2},
                    {"culture": 4, "workforce": 1, "leadership": 5}):
        result = ENGINE.score(build(answers), validate=False)
        assert overall_under(result, EQUAL_WEIGHTS) == pytest.approx(
            result.overall_score
        )


def test_emphasising_a_factor_still_leaves_the_weights_summing_to_one():
    weights = emphasise("data", 2.0)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["data"] > weights["budget"]


def test_re_weighting_moves_the_score_towards_the_emphasised_factor():
    # One weak factor against six average ones: leaning on the weak factor has
    # to pull the overall score down.
    result = ENGINE.score(build({"data": 1}), validate=False)
    baseline = overall_under(result, EQUAL_WEIGHTS)
    leaning = overall_under(result, emphasise("data", 3.0))
    assert leaning < baseline


def test_re_weighting_changes_nothing_when_every_factor_scores_the_same():
    # A company answering identically everywhere is the one case where the
    # weighting genuinely cannot matter, whatever weights are used.
    result = ENGINE.score(build({}), validate=False)
    for factor in cfg.FACTORS:
        assert overall_under(result, emphasise(factor.id, 5.0)) == pytest.approx(
            result.overall_score
        )


def test_a_scenario_reports_how_far_the_answer_moved():
    scored = score_all([
        build({"data": 1}), build({"data": 5}), build({"budget": 1}),
    ])
    scenario = compare_weighting(scored, emphasise("data", 3.0), "lean on data")
    assert scenario.mean_absolute_shift > 0
    assert scenario.largest_shift >= scenario.mean_absolute_shift
    assert "lean on data" == scenario.label
    assert "points" in scenario.summary


# ---------------------------------------------------------------------------
# the analysis end to end
# ---------------------------------------------------------------------------

def test_the_factor_built_to_track_the_outcome_comes_out_on_top():
    # Data readiness is made to rise in step with reported adoption stage.
    # Every other factor is held flat, so there is a right answer here.
    stages = list(cfg.AI_ADOPTION_STAGES)
    profiles = []
    for round_number in range(3):
        for position, stage in enumerate(stages):
            profiles.append(build({"data": min(5, position + 1)}, stage=stage))

    report = analyse(score_all(profiles), trials=300)

    assert report.outcome_available
    leader = report.by_outcome()[0]
    assert leader.factor_id == "data"
    assert leader.outcome_r > 0.8
    assert leader.outcome_p < 0.01


def test_a_factor_nobody_varies_on_gets_no_correlation():
    stages = list(cfg.AI_ADOPTION_STAGES)
    profiles = [
        build({"data": min(5, position + 1)}, stage=stage)
        for position, stage in enumerate(stages) for _ in range(3)
    ]
    report = analyse(score_all(profiles), trials=200)

    budget = next(f for f in report.factors if f.factor_id == "budget")
    assert budget.sd_score == pytest.approx(0.0)
    assert budget.outcome_r is None


def test_all_one_stage_means_no_outcome_analysis_and_a_warning_saying_so():
    profiles = [
        build({"data": value}, stage="Piloting") for value in (1, 2, 3, 4, 5)
    ]
    report = analyse(score_all(profiles), trials=100)

    assert not report.outcome_available
    assert any("same adoption stage" in w for w in report.warnings)
    assert report.by_outcome() == []


def test_a_small_sample_says_so_before_anything_else():
    profiles = [build({"data": value}) for value in (1, 2, 3, 4, 5)]
    report = analyse(score_all(profiles), trials=100)
    assert any("exploratory" in w for w in report.warnings)


def test_the_weakest_factor_is_counted_as_the_weakest():
    profiles = [build({"budget": 1}) for _ in range(4)]
    report = analyse(score_all(profiles), scenarios=False, trials=50)

    budget = next(f for f in report.factors if f.factor_id == "budget")
    assert budget.weakest_rate == pytest.approx(100.0)
    assert budget.barrier_rate == pytest.approx(100.0)


def test_a_factor_nobody_answered_is_left_out_not_scored_as_zero():
    profile = build({})
    for item in cfg.FACTORS_BY_ID["governance"].items:
        profile.responses.pop(item.id)

    report = analyse(score_all([profile, build({})]), scenarios=False, trials=50)
    governance = next(f for f in report.factors if f.factor_id == "governance")
    assert governance.scored_companies == 1


def test_a_flipped_item_is_flagged_as_moving_against_its_factor():
    # DAT_1 is inverted relative to the rest of Data readiness, which is what a
    # reverse-coding mistake produces. The analysis should say so rather than
    # quietly reporting a low alpha.
    profiles = []
    for value in (1, 2, 4, 5, 1, 2, 4, 5):
        responses = coherent("data", value)
        responses["DAT_1"] = cfg.REVERSE_PIVOT - responses["DAT_1"]
        profiles.append(build({}, responses=responses))

    report = analyse(score_all(profiles), scenarios=False, trials=50)

    assert "data" in report.polarity_flags
    assert "DAT_1" in report.polarity_flags["data"]
    assert any("DAT_1" in w for w in report.warnings)


def test_a_coherent_factor_is_not_flagged():
    profiles = [
        build({}, responses=coherent("data", value))
        for value in (1, 2, 3, 4, 5, 1, 2, 3)
    ]
    report = analyse(score_all(profiles), scenarios=False, trials=50)
    assert "data" not in report.polarity_flags


def test_straight_lining_makes_every_reverse_item_look_mis_polarised():
    # Respondents who tick the same box all the way down are a known survey
    # problem, and this is what they do to the diagnostic: once re-coded, the
    # barrier-worded items point the opposite way to everything else and get
    # flagged even though the questionnaire is fine.
    #
    # The test is here so the limitation is recorded rather than discovered
    # later: a polarity flag is a prompt to check the wording and the response
    # pattern together, not proof on its own that an item is wrong.
    profiles = [
        build({}, responses={
            item.id: value for item in cfg.FACTORS_BY_ID["data"].items
        })
        for value in (1, 2, 3, 4, 5, 1, 2, 3)
    ]
    report = analyse(score_all(profiles), scenarios=False, trials=50)

    # DAT_5 is the only reverse item in Data readiness.
    assert report.polarity_flags.get("data") == ["DAT_5"]


def test_nothing_to_analyse_is_reported_rather_than_crashing():
    report = analyse([], trials=10)
    assert report.n == 0
    assert report.warnings


def test_agreement_across_measures_is_what_gets_reported_as_a_leader():
    stages = list(cfg.AI_ADOPTION_STAGES)
    profiles = [
        build({"data": min(5, position + 1)}, stage=stage)
        for position, stage in enumerate(stages) for _ in range(3)
    ]
    report = analyse(score_all(profiles), trials=200)
    # Data leads the outcome ordering and is the weakest factor most often,
    # so it should survive the agreement filter.
    assert "data" in report.agreed_leaders()


def test_the_report_prints_and_says_what_it_cannot_claim():
    stages = list(cfg.AI_ADOPTION_STAGES)
    profiles = [
        build({"data": min(5, position + 1)}, stage=stage)
        for position, stage in enumerate(stages) for _ in range(3)
    ]
    text = format_report(analyse(score_all(profiles), trials=100))

    assert "FACTOR INFLUENCE ANALYSIS" in text
    assert "Companies analysed: 15" in text
    assert "not a demonstrated cause" in text or "no evidence here" in text
    # The sample-size caveat has to survive into the printed output, not just
    # sit on the report object.
    assert "exploratory" in text


def test_the_analysis_never_touches_the_scores_it_was_given():
    profiles = [build({"data": value}) for value in (1, 3, 5)]
    scored = score_all(profiles)
    before = [r.overall_score for r in scored]
    factors_before = [dict((k, v.score) for k, v in r.factor_scores.items())
                      for r in scored]

    analyse(scored, trials=100)

    assert [r.overall_score for r in scored] == before
    assert [dict((k, v.score) for k, v in r.factor_scores.items())
            for r in scored] == factors_before


def test_the_configured_weights_are_still_equal():
    # The analysis reports on weighting; it does not change it. If this fails,
    # something has written weights back into the configuration.
    assert len(set(round(w, 12) for w in EQUAL_WEIGHTS.values())) == 1



