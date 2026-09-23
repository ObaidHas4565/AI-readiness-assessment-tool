"""
Tests for reading the written answers.

Two things are being protected here. The first is that non-answers stay out:
a real survey is full of "N/A", "none" and blanks, and counting those as
evidence would be worse than ignoring the column entirely. The second is the
boundary the analysis must not cross -- the text may change the advice, but it
must never change a score.
"""

import pytest

from src import score_configuration as cfg
from src.company_profile import CompanyProfile
from src.recommendation_engine import RecommendationEngine
from src.scoring_engine import ScoringEngine
from src.text_analysis import (
    analyse_notes,
    analyse_single,
    apply_to_recommendations,
    concepts_in,
    is_informative,
)


CONTEXT = {
    "industry_sector": "Retail",
    "employee_band": "10-49",
    "years_in_operation": "6-10 years",
    "region": "UAE",
    "current_ai_stage": "Exploring",
}


# ---------------------------------------------------------------------------
# Throwing out the answers that are not answers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("answer", [
    "N/A", "n/a", "N.A.", "NA", "na",
    "None", "none", "NONE",
    "No", "no", "Nope",
    "Nothing", "nothing",
    "Yes", "yes",
    "", "   ", "-", ".", "x",
    "nil", "idk", "not sure", "good", "ok",
    "nothing much really",
])
def test_non_answers_are_not_counted(answer):
    keep, reason = is_informative(answer)
    assert not keep, f"{answer!r} should have been set aside"
    assert reason


@pytest.mark.parametrize("answer,concept", [
    ("Cost", "money"),
    ("we cannot afford the licences", "money"),
    ("Lack of skilled staff", "people"),
    ("management does not see the value", "leader"),
    ("our data is messy and spread across spreadsheets", "data"),
    ("the team is worried about privacy", "govern"),
    ("we need better internet in the office", "infra"),
    ("staff are afraid of losing their jobs", "culture"),
])
def test_real_answers_are_kept_and_placed(answer, concept):
    keep, _ = is_informative(answer)
    assert keep, f"{answer!r} should have been kept"
    assert concept in concepts_in(answer)


def test_blank_and_missing_are_handled_without_raising():
    assert is_informative(None)[0] is False
    assert is_informative("")[0] is False


def test_the_discard_count_is_reported_rather_than_hidden():
    """
    A tool that quietly drops half the answers and reports on the rest is
    reporting on a sample it has not described. The counts say what happened.
    """
    notes = [
        ("R1", {"barrier": "Cost is the main problem", "help": "N/A"}),
        ("R2", {"barrier": "none", "help": ""}),
    ]
    insights = analyse_notes(notes)

    assert insights.answers_seen == 4
    assert insights.answers_used == 1
    assert insights.answers_dropped == 3
    assert sum(insights.drop_reasons.values()) == 3
    assert insights.respondents == 1


def test_one_person_writing_three_times_is_one_voice():
    """A respondent counts once per factor, not once per answer."""
    notes = [("R1", {
        "a": "cost is the problem",
        "b": "we have no budget",
        "c": "everything is too expensive",
    })]
    insights = analyse_notes(notes)

    budget = insights.signal("budget")
    assert budget is not None
    assert budget.mentions == 1


# ---------------------------------------------------------------------------
# Reaching the recommendations without reaching the score
# ---------------------------------------------------------------------------

def _profile(**extra) -> CompanyProfile:
    answers = {item.id: 3 for item in cfg.ALL_ITEMS}
    return CompanyProfile.from_dict({**CONTEXT, **answers, **extra})


def test_written_answers_never_move_the_score():
    """
    The score is a weighted average of rating responses and nothing else.
    Moving it on a keyword match would make it impossible to reproduce.
    """
    plain = ScoringEngine().score(_profile())
    talkative = ScoringEngine().score(_profile(
        open_biggest_barrier="We have no budget at all and no skilled staff.",
        open_what_would_help="Funding and training.",
    ))

    assert plain.overall_score == talkative.overall_score
    for factor in cfg.FACTORS:
        assert (plain.factor(factor.id).score
                == talkative.factor(factor.id).score)


def test_the_words_attach_to_the_recommendation_they_support():
    profile = _profile(
        open_biggest_barrier="Cost is the single biggest barrier for us.")
    results = ScoringEngine().score(profile)
    RecommendationEngine().recommend(results)

    budget = [r for r in results.recommendations if r.factor_id == "budget"]
    assert budget, "a mid-scoring factor should still produce advice"
    assert any(r.evidence for r in budget)
    assert any("Cost is the single biggest barrier" in quote
               for r in budget for quote in r.evidence)


def test_a_factor_the_comments_raise_but_the_scores_did_not():
    """
    The case the free text exists for: the questionnaire is content with an
    area and the respondent is not. That disagreement is a finding, so it is
    reported rather than dropped.
    """
    answers = {item.id: 5 if not item.reverse else 1 for item in cfg.ALL_ITEMS}
    profile = CompanyProfile.from_dict({
        **CONTEXT, **answers,
        "open_biggest_barrier":
            "Honestly our data is a mess, scattered across old spreadsheets.",
    })
    results = ScoringEngine().score(profile)
    RecommendationEngine().recommend(results)

    # Nothing scored badly enough to be flagged the usual way.
    assert results.factor("data").score >= cfg.BARRIER_THRESHOLD

    raised = [r for r in results.recommendations if r.severity == "raised"]
    assert raised, "the comment should have raised the factor on its own"
    assert any(r.factor_id == "data" for r in raised)
    assert all(r.evidence for r in raised)


def test_a_lone_voice_in_a_large_dataset_does_not_become_a_finding():
    """
    One person out of many naming a factor is an anecdote. The threshold
    exists so a single comment cannot manufacture a cohort-level action.
    """
    from src.export_service import cohort_results

    scored = []
    for index in range(20):
        answers = {item.id: 5 if not item.reverse else 1
                   for item in cfg.ALL_ITEMS}
        result = ScoringEngine().score(
            CompanyProfile.from_dict({**CONTEXT, **answers}))
        scored.append((f"R{index}", result))

    notes = [("R0", {"barrier": "our data is messy and scattered"})]
    notes += [(f"R{i}", {"barrier": "nothing at all"}) for i in range(1, 20)]

    average = cohort_results(scored)
    RecommendationEngine().recommend(average)
    apply_to_recommendations(average, analyse_notes(notes))

    assert not [r for r in average.recommendations if r.severity == "raised"]


def test_a_single_assessment_needs_no_threshold():
    """With one respondent there is no share to reach -- they are the data."""
    insights = analyse_single({"barrier": "our data is messy and scattered"})
    assert insights.respondents == 1
    assert insights.signal("data") is not None
