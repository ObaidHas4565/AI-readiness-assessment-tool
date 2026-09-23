"""
Written-answer analysis
=======================

The questionnaire's three open questions, and the free-text columns found in
an imported survey, are the only part of the instrument a respondent can use
to say something the 32 fixed questions never asked. Collecting them and then
printing them untouched at the back of a report wastes them.

This module reads them. It does two jobs:

  1. Throws away the answers that are not answers. A large share of any real
     survey's free text is "N/A", "None", "no", "-" or a blank, and counting
     those as evidence of anything would be worse than ignoring the column.
  2. Places the remaining answers against the seven readiness factors, using
     the same concept lexicon that matches survey questions to items, so that
     "we cannot afford it", "no budget" and "too expensive" all land on Budget.

What this deliberately does NOT do
----------------------------------
It does not change any score. The readiness score is defined as a weighted
average of rating responses, and quietly moving it on the strength of a
keyword match would make the number impossible to defend and impossible to
reproduce. What the text does instead is affect the *interpretation*:

  * it attaches the respondent's own words to the recommendation for the
    factor they were talking about, as evidence;
  * it raises a factor that the comments name repeatedly but the scores did
    not flag, as a separate, clearly-labelled item.

A disagreement between the numbers and the comments is a finding in itself,
and the second of those is how it gets reported rather than hidden.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import score_configuration as cfg
from .survey_import import STOPWORDS, _WORD_TO_CONCEPTS, _normalise, _stem


# ---------------------------------------------------------------------------
# Which concept belongs to which factor
# ---------------------------------------------------------------------------
# Seven of the nine concepts in the lexicon correspond to a readiness factor.
# The remaining two -- "adopt" and "ai" -- say the answer is about AI adoption
# without saying which factor, so they keep an answer in the analysis without
# assigning it anywhere.

CONCEPT_TO_FACTOR: Dict[str, str] = {
    "money": "budget",
    "people": "workforce",
    "leader": "leadership",
    "data": "data",
    "infra": "technology",
    "culture": "culture",
    "govern": "governance",
}

GENERAL_CONCEPTS = frozenset({"adopt", "ai"})

# Everyday vocabulary that the question-matching lexicon does not need but
# written answers use constantly. A respondent writes "the internet here is
# slow", not "our IT infrastructure is inadequate".
#
# These live here rather than in CONCEPT_LEXICON on purpose: that lexicon
# feeds the IDF weighting used to match survey columns to questions, and
# adding words to it would shift matching results that are already tested.
# Extending only the reading of free text leaves that untouched.
EXTRA_TERMS: Dict[str, Tuple[str, ...]] = {
    "infra": (
        "internet", "wifi", "computer", "computers", "laptop", "laptops",
        "system", "systems", "software", "device", "devices", "equipment",
        "machine", "slow", "offline", "update", "updates", "upgrade",
        "subscription", "license", "licence",
    ),
    "money": (
        "expensive", "cheap", "price", "pricing", "pay", "paying", "sme",
        "small", "tight", "limited", "resource", "resources", "free",
    ),
    "people": (
        "course", "courses", "workshop", "mentor", "consultant", "expert",
        "experts", "team", "teams", "people", "person", "junior", "senior",
        "graduate", "intern", "understand", "understanding", "confused",
        "confidence", "confident", "experience", "experienced",
    ),
    "leader": (
        "manager", "managers", "boss", "owner", "owners", "board", "ceo",
        "decision", "decisions", "plan", "planning", "roadmap", "goal",
        "goals", "approval", "approve", "convince",
    ),
    "data": (
        "spreadsheet", "spreadsheets", "excel", "paper", "paperwork",
        "manual", "manually", "digitise", "digitize", "database", "file",
        "files", "messy", "scattered", "duplicate",
    ),
    "govern": (
        "confidential", "gdpr", "leak", "breach", "safe", "safety", "rule",
        "rules", "policy", "policies", "government", "liable", "liability",
        "wrong", "mistake", "mistakes", "hallucinate", "inaccurate",
    ),
    "culture": (
        "afraid", "fear", "scared", "worried", "worry", "job", "jobs",
        "replace", "replaced", "redundant", "reluctant", "sceptical",
        "skeptical", "trust", "habit", "old", "traditional", "slowly",
    ),
    "adopt": (
        "start", "started", "starting", "begin", "trial", "test", "testing",
        "chatgpt", "copilot", "gemini", "claude", "llm", "chatbot",
    ),
}

_EXTRA_WORD_TO_CONCEPTS: Dict[str, List[str]] = {}
for _concept, _words in EXTRA_TERMS.items():
    for _word in _words:
        _EXTRA_WORD_TO_CONCEPTS.setdefault(_word, []).append(_concept)


# ---------------------------------------------------------------------------
# Answers that are not answers
# ---------------------------------------------------------------------------
# Compared after stripping every non-alphanumeric character, so "N/A", "n.a.",
# "N / A" and "na" are one entry rather than four.

NON_ANSWERS: frozenset = frozenset("""
na n none no nope nothing nil null nan no0ne x xx xxx none1 non
yes y ok okay fine good great bad same idk dk dunno
dontknow donotknow notsure unsure noidea noclue
nocomment nocomments nothingtoadd nothingelse nothingmuch noneatall
notapplicable notapplicableatall notrelevant noanswer
tbd tba asdf test none2 zero -
""".split())

# Content words that carry no information on their own. These are not general
# stopwords -- "nothing" is meaningful in "nothing has been budgeted" -- but an
# answer consisting only of these says nothing at all.
EMPTY_CONTENT: frozenset = frozenset("""
nothing none nil nope yeah yep sure maybe perhaps
ok okay fine good great bad better worse alright
know sure think thing things stuff
""".split())

MIN_CHARACTERS: int = 3
# An answer with no domain vocabulary at all still has to be long enough to be
# saying something. Three content words is roughly "processes are unclear" --
# short, but a real statement -- while one or two is almost always a shrug.
MIN_CONTENT_WORDS_WITHOUT_CONCEPT: int = 3


def _squash(text: str) -> str:
    """Reduce an answer to its letters and digits, for non-answer matching."""
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _content_words(text: str) -> List[str]:
    """The words in an answer that carry meaning."""
    return [
        word for word in _normalise(text).split()
        if word not in STOPWORDS
        and word not in EMPTY_CONTENT
        and _stem(word) not in EMPTY_CONTENT
        and len(word) >= 3
    ]


def concepts_in(text: str) -> set:
    """The lexicon concepts an answer mentions."""
    found = set()
    for word in _normalise(text).split():
        for lookup in (_WORD_TO_CONCEPTS, _EXTRA_WORD_TO_CONCEPTS):
            for concept in lookup.get(word, ()):
                found.add(concept)
            stem = _stem(word)
            if stem != word:
                for concept in lookup.get(stem, ()):
                    found.add(concept)
    return found


def is_informative(text: Optional[str]) -> Tuple[bool, str]:
    """
    Decide whether a written answer is worth analysing.

    Returns (keep, reason). The reason is only meaningful when keep is False,
    and exists so the report can say how many answers were set aside and why,
    rather than silently reducing the denominator.
    """
    if text is None:
        return False, "blank"

    raw = str(text).strip()
    if not raw:
        return False, "blank"

    squashed = _squash(raw)
    if not squashed:
        return False, "blank"
    if squashed in NON_ANSWERS:
        return False, "no answer given"
    if len(squashed) < MIN_CHARACTERS:
        return False, "too short to read"

    words = _content_words(raw)
    if not words:
        return False, "no specific content"

    if concepts_in(raw):
        return True, ""

    if len(words) >= MIN_CONTENT_WORDS_WITHOUT_CONCEPT:
        return True, ""

    return False, "too short to place"


# ---------------------------------------------------------------------------
# The analysis
# ---------------------------------------------------------------------------

@dataclass
class FactorSignal:
    """What the written answers said about one readiness factor."""

    factor_id: str
    factor_name: str
    mentions: int                            # respondents, not occurrences
    examples: List[str] = field(default_factory=list)
    # % of everyone surveyed, not % of those whose answers could be read.
    share: float = 0.0


@dataclass
class TextInsights:
    """The outcome of reading a set of written answers."""

    # Everyone the written answers were collected from, whether or not what
    # they wrote could be used. This is the denominator every share is taken
    # over: "9 of 15" where 15 is the people who happened to be understood
    # would report one person in twenty as unanimous agreement.
    total_respondents: int = 0
    respondents: int = 0        # of those, the ones who wrote something usable
    answers_seen: int = 0       # individual answers looked at
    answers_used: int = 0       # answers that said something
    answers_dropped: int = 0    # answers set aside as non-answers
    drop_reasons: Dict[str, int] = field(default_factory=dict)
    by_factor: List[FactorSignal] = field(default_factory=list)
    general: List[str] = field(default_factory=list)

    @property
    def used(self) -> bool:
        return self.answers_used > 0

    def signal(self, factor_id: str) -> Optional[FactorSignal]:
        for signal in self.by_factor:
            if signal.factor_id == factor_id:
                return signal
        return None


def _snippet(text: str, limit: int = 170) -> str:
    cleaned = " ".join(str(text).split())
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def analyse_notes(
    notes: Sequence[Tuple[str, Mapping[str, str]]],
) -> TextInsights:
    """
    Read a set of written answers and report what they are about.

    `notes` is a sequence of (respondent id, {question: answer}) pairs, which
    is the shape both the dataset tab and a single assessment already use.

    A respondent is counted at most once per factor, so one person writing
    three long answers about cost does not become three votes for Budget.
    """
    insights = TextInsights()
    mentions: Dict[str, int] = {}
    examples: Dict[str, List[str]] = {}
    contributing = 0

    for _, answers in notes:
        answers = dict(answers or {})
        wrote_something = False
        factors_this_person: Dict[str, str] = {}
        general_this_person: Optional[str] = None

        for answer in answers.values():
            insights.answers_seen += 1
            keep, reason = is_informative(answer)
            if not keep:
                insights.answers_dropped += 1
                insights.drop_reasons[reason] = \
                    insights.drop_reasons.get(reason, 0) + 1
                continue

            insights.answers_used += 1
            wrote_something = True

            found = concepts_in(answer)
            placed = False
            for concept in found:
                factor_id = CONCEPT_TO_FACTOR.get(concept)
                if factor_id:
                    placed = True
                    # Keep the first answer this person gave on the factor as
                    # the quotable one.
                    factors_this_person.setdefault(factor_id, str(answer))

            if not placed and (found & GENERAL_CONCEPTS or not found):
                # About AI adoption, or a real sentence with no domain word in
                # it. Either way it is kept, just not attributed to a factor.
                if general_this_person is None:
                    general_this_person = str(answer)

        if wrote_something:
            contributing += 1
        for factor_id, quote in factors_this_person.items():
            mentions[factor_id] = mentions.get(factor_id, 0) + 1
            if len(examples.setdefault(factor_id, [])) < 3:
                examples[factor_id].append(_snippet(quote))
        if general_this_person and len(insights.general) < 12:
            insights.general.append(_snippet(general_this_person))

    insights.respondents = contributing
    insights.total_respondents = len(notes)
    denominator = insights.total_respondents or 1

    signals: List[FactorSignal] = []
    for factor in cfg.FACTORS:
        count = mentions.get(factor.id, 0)
        if not count:
            continue
        signals.append(FactorSignal(
            factor_id=factor.id,
            factor_name=factor.name,
            mentions=count,
            examples=examples.get(factor.id, []),
            share=count / denominator * 100,
        ))

    insights.by_factor = sorted(signals, key=lambda s: -s.mentions)
    return insights


def analyse_single(notes: Optional[Mapping[str, str]]) -> TextInsights:
    """The same analysis for one company's three written answers."""
    return analyse_notes([("this company", dict(notes or {}))])


# ---------------------------------------------------------------------------
# Letting the text reach the recommendations
# ---------------------------------------------------------------------------

SEVERITY_RAISED = "raised"

# How many respondents, as a share, have to name a factor before it is raised
# against a score that did not flag it. One person out of two hundred is an
# anecdote; a fifth of them is a pattern. For a single company the threshold
# is meaningless -- there is only one respondent -- so any mention counts.
RAISE_SHARE: float = 20.0


def apply_to_recommendations(results, insights: TextInsights) -> None:
    """
    Let the written answers influence the advice, without touching the score.

    Two effects:

      * every recommendation for a factor people wrote about gains their own
        words as evidence, so the reader can see the action is not only a
        threshold being crossed;
      * a factor that people raise but the scores did not flag is added as a
        separate item, labelled as coming from the comments.

    `results` is mutated in place, which matches how RecommendationEngine
    already works on the same object.
    """
    from .assessment_results import Recommendation

    results.text_insights = insights
    if not insights.used:
        return

    # 1. Evidence on the recommendations that already exist.
    # Recommendation is frozen, so each one is rebuilt with its evidence
    # rather than edited in place. That keeps a recommendation an immutable
    # record of what the rules produced, which is what makes it safe to pass
    # the same object to the dashboard and to both exports.
    from dataclasses import replace

    rebuilt: List = []
    for rec in results.recommendations:
        signal = insights.signal(rec.factor_id)
        if signal:
            rec = replace(rec,
                          evidence=list(signal.examples[:2]),
                          evidence_count=signal.mentions)
        rebuilt.append(rec)
    results.recommendations = rebuilt

    already = {rec.factor_id for rec in rebuilt}

    # 2. Factors the comments raise that the scores did not.
    single = insights.total_respondents <= 1
    for signal in insights.by_factor:
        if signal.factor_id in already:
            continue
        if not single and signal.share < RAISE_SHARE:
            continue

        factor = results.factor_scores.get(signal.factor_id)
        if factor is None:
            # The factor was never scored -- no reading at all, so the comment
            # is the only evidence there is, and worth more here than usual.
            score_line = (
                "This factor was not covered by the data at all, so the "
                "written answers are the only evidence available for it."
            )
        else:
            score_line = (
                f"The scored questions put this factor at {factor.score:.0f}/100, "
                f"which is not low enough to flag as a barrier."
            )

        if single:
            who = "Your own written answer raises it directly."
        else:
            who = (
                f"{signal.mentions} of {insights.total_respondents} "
                f"respondents ({signal.share:.0f}%) raise it directly in "
                f"their own words."
            )

        results.recommendations.append(Recommendation(
            factor_id=signal.factor_id,
            factor_name=signal.factor_name,
            severity=SEVERITY_RAISED,
            title=f"Check {signal.factor_name} against what people actually wrote",
            action=(
                f"{score_line} {who} Where the comments and the scores "
                f"disagree, the comments are usually naming something the "
                f"fixed questions do not ask about, so this is worth looking "
                f"at before the questionnaire result is taken at face value."
            ),
            priority=-1.0,   # below every scored recommendation
            evidence=list(signal.examples[:2]),
            evidence_count=signal.mentions,
        ))
