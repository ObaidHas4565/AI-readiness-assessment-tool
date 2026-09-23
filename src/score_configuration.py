"""
ScoreConfiguration
==================

Fixed constants for the AI Adoption Readiness Assessment Tool.

This module is deliberately isolated from all scoring logic and all UI code, in
line with the Maintainability non-functional requirement: the weights, the
thresholds and the item wording can be revised as the research develops without
touching the ScoringEngine, the RecommendationEngine or the Streamlit layer.

Everything here is derived directly from the AI Adoption Readiness Survey
instrument (7 readiness factors, 32 rating items, 5 categorical profile fields).

Reference: Requirements Specification (FR3, NFR-Maintainability) and the
Class Diagram in Chapter 4, where ScoreConfiguration is a separate component
supplying constants to the ScoringEngine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 1. Rating scale
# ---------------------------------------------------------------------------
# The survey uses a single uniform 5-point agreement scale for every readiness
# item. Strongly Agree is stored as 5 so that, for positively-worded items, a
# higher stored value always means higher readiness.

RATING_MIN: int = 1
RATING_MAX: int = 5

RATING_LABELS: Dict[int, str] = {
    5: "Strongly Agree",
    4: "Agree",
    3: "Neutral",
    2: "Disagree",
    1: "Strongly Disagree",
}

# Reverse-worded items are re-coded as (RATING_MIN + RATING_MAX) - raw = 6 - raw
# so that, after re-coding, 5 always means "more ready" for every item.
REVERSE_PIVOT: int = RATING_MIN + RATING_MAX  # 6


# ---------------------------------------------------------------------------
# 2. Item and Factor definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    """A single Rating statement (a 'subfactor' in the requirements)."""

    id: str
    text: str
    reverse: bool = False


@dataclass(frozen=True)
class Factor:
    """A readiness factor: a named group of Rating items carrying a weight."""

    id: str
    name: str
    weight: float
    items: Tuple[Item, ...]
    # Short note on where this factor is grounded in the literature review.
    # Used in Chapter 4 to justify the factor set, and surfaced in the tool.
    literature: str = ""

    @property
    def item_ids(self) -> List[str]:
        return [item.id for item in self.items]


# ---------------------------------------------------------------------------
# NOTE ON WEIGHTS
# ---------------------------------------------------------------------------
# The weights below are set to EQUAL weighting (1/7 each) as the honest default.
#
# This is a deliberate starting position, not a finding. Objective 4 of the
# thesis is "Determine which areas have the greatest influence on AI adoption
# readiness" -- that is an empirical result, so hard-coding uneven weights
# before the analysis would be assuming the answer.
#
# Once the survey n is large enough, the `current_ai_stage` field on
# CompanyProfile gives an ordinal outcome variable that these factor scores can
# be regressed or correlated against, which is what would justify replacing the
# equal weights with empirically-derived ones. Changing the numbers below is the
# only edit required -- nothing else in the codebase hard-codes a weight.
# ---------------------------------------------------------------------------

_EQUAL_WEIGHT = 1.0 / 7.0


FACTORS: Tuple[Factor, ...] = (
    Factor(
        id="budget",
        name="Budget & Financial Readiness",
        weight=_EQUAL_WEIGHT,
        literature=(
            "Financial and resource constraints are repeatedly identified as a "
            "primary SME adoption barrier; 'funding' is an explicit dimension of "
            "the AI-BPM Maturity Assessment Matrix."
        ),
        items=(
            Item("BUD_1", "We have a dedicated budget for AI adoption or experimentation."),
            Item("BUD_2", "Financial cost is the current barrier in AI adoption.", reverse=True),
            Item("BUD_3", "We can access external funding or grants for technology adoption if needed."),
            Item("BUD_4", "Leadership would approve for investment in AI adoption if return on investment is clearly shown."),
        ),
    ),
    Factor(
        id="workforce",
        name="Workforce & Skill Readiness",
        weight=_EQUAL_WEIGHT,
        literature=(
            "Human readiness -- staff skills, training provision, learning ability "
            "and openness to change -- is the dimension the TOEH framework adds to "
            "TOE, and is central to the human-readiness literature."
        ),
        items=(
            Item("WRK_1", "Staff having the required technical skills needed to use AI tools effectively."),
            Item("WRK_2", "We provide training opportunities to employees for AI-related skills."),
            # See W3_NOTE below -- this item's polarity is a judgement call.
            Item("WRK_3", "We have identified specific skill gaps that block AI adoption.", reverse=True),
            Item("WRK_4", "Staff are generally open to use AI tools in their work."),
        ),
    ),
    Factor(
        id="leadership",
        name="Leadership & Strategic Readiness",
        weight=_EQUAL_WEIGHT,
        literature=(
            "Leadership commitment, strategic vision and change management recur "
            "across TOE, AIMAA and the AI-BPM matrix as determinants of successful "
            "adoption."
        ),
        items=(
            Item("LDR_1", "Leadership views AI adoption as low priority right now.", reverse=True),
            Item("LDR_2", "Leadership actively supports AI adoption initiatives."),
            Item("LDR_3", "We have clear strategic vision for how AI fits into our business goals."),
            Item("LDR_4", "Leadership regularly communicates the reasons and benefits of AI adoption to staff."),
            Item("LDR_5", "Decision-makers understand the basic capabilities and limitations of AI tools."),
        ),
    ),
    Factor(
        id="data",
        name="Data Readiness",
        weight=_EQUAL_WEIGHT,
        literature=(
            "Data quality, accessibility and governance are the focus of the IBM "
            "Ladder and a named dimension in most maturity models reviewed."
        ),
        items=(
            Item("DAT_1", "Our company data is well-organized and easily accessible."),
            Item("DAT_2", "We trust the quality and accuracy of our existing data."),
            Item("DAT_3", "We have processes in place for managing and governing data."),
            Item("DAT_4", "We could provide the data an AI tool would need if we adopted one."),
            Item("DAT_5", "Poor data quality is the current barrier to using AI tools in our company.", reverse=True),
        ),
    ),
    Factor(
        id="technology",
        name="Technology & IT Infrastructure Readiness",
        weight=_EQUAL_WEIGHT,
        literature=(
            "IT infrastructure, systems integration and prior digital adoption "
            "experience form the 'technology' pillar of TOE and the IT-readiness "
            "literature."
        ),
        items=(
            Item("TEC_1", "Current IT infrastructure could support new AI tools."),
            Item("TEC_2", "Integrated systems that could connect with AI systems."),
            Item("TEC_3", "We have IT support capable for maintaining AI tools."),
            Item("TEC_4", "We have previously adopted new digital tools or systems successfully."),
            Item("TEC_5", "Outdated or incompatible technology is the current barrier to AI adoption.", reverse=True),
        ),
    ),
    Factor(
        id="culture",
        name="Organizational Cultural Readiness",
        weight=_EQUAL_WEIGHT,
        literature=(
            "'Culture' is an explicit factor in the AI-BPM matrix; resistance to "
            "change and tolerance of failed pilots are recurring adoption barriers "
            "in the SME literature."
        ),
        items=(
            Item("CUL_1", "Our organization is generally open to new technologies."),
            # Already phrased positively for readiness ("are NOT overly resistant"),
            # so agreement indicates higher readiness -- this is NOT a reverse item.
            Item("CUL_2", "Employees are not overly resistant to changes in how they work."),
            Item("CUL_3", "Failed pilot projects are treated as learning opportunities rather than failures."),
            Item("CUL_4", "We regularly discuss innovation and new technology at a company level."),
        ),
    ),
    Factor(
        id="governance",
        name="Governance, Ethics & Trust",
        weight=_EQUAL_WEIGHT,
        literature=(
            "Responsible AI, privacy compliance, accountability structures and "
            "trustworthiness were identified in the review as a gap in models such "
            "as Gartner and McKinsey, and are addressed by AIMAA and AI-BPM."
        ),
        items=(
            Item("GOV_1", "We are confident in our ability to manage data privacy and security if we adopted AI."),
            Item("GOV_2", "We are aware of ethical issues (e.g. bias, transparency) associated with AI tools."),
            Item("GOV_3", "We already have clear accountability and oversight structures in technology-related decisions."),
            Item("GOV_4", "We generally trust AI tools to produce accurate and fair results."),
            Item("GOV_5", "We would struggle to comply with data privacy or security regulations if we adopt AI tools.", reverse=True),
        ),
    ),
)


# ---------------------------------------------------------------------------
# W3_NOTE -- open decision, flagged deliberately
# ---------------------------------------------------------------------------
# WRK_3 "We have identified specific skill gaps that block AI adoption" is
# genuinely ambiguous and materially affects the Workforce score:
#
#   Reading A (currently applied, reverse=True):
#       The statement asserts that gaps EXIST and BLOCK adoption. Agreeing is
#       therefore a report of a barrier -> lower readiness.
#
#   Reading B (reverse=False):
#       The statement is about diagnostic self-awareness -- a company that has
#       identified its gaps is better prepared than one that has not.
#
# Reading A is applied because the clause "that block AI adoption" makes the
# item a barrier statement, consistent with the other reverse items in the
# instrument (BUD_2, LDR_1, DAT_5, TEC_5, GOV_5). Flip `reverse` on WRK_3 above
# to switch readings; nothing else needs to change.
# ---------------------------------------------------------------------------


# Convenience lookups, built once at import.
FACTORS_BY_ID: Dict[str, Factor] = {f.id: f for f in FACTORS}
ALL_ITEMS: Tuple[Item, ...] = tuple(item for f in FACTORS for item in f.items)
ITEMS_BY_ID: Dict[str, Item] = {i.id: i for i in ALL_ITEMS}
ITEM_TO_FACTOR: Dict[str, str] = {i.id: f.id for f in FACTORS for i in f.items}


# ---------------------------------------------------------------------------
# 3. Categorical company profile fields
# ---------------------------------------------------------------------------
# These are contextual metadata, NOT scored. They exist to segment and benchmark
# responses and to support later empirical weighting. None of them identifies a
# company, in line with the Privacy non-functional requirement.

INDUSTRY_SECTORS: Tuple[str, ...] = (
    "Retail",
    "Technology",
    "Manufacturing",
    "Marketing",
    "Healthcare",
    "Other",
)

EMPLOYEE_BANDS: Tuple[str, ...] = ("1-9", "10-49", "50-249", "250+")

YEARS_IN_OPERATION: Tuple[str, ...] = ("Under 2 years", "2-5 years", "6-10 years", "10+ years")

REGIONS: Tuple[str, ...] = ("UAE", "UK", "India", "USA", "Other")

# Ordinal: this is the natural outcome variable for deriving empirical weights.
AI_ADOPTION_STAGES: Tuple[str, ...] = (
    "Not considering",
    "Exploring",
    "Piloting",
    "Actively Using",
    "Fully Integrated",
)

CATEGORICAL_FIELDS: Dict[str, Tuple[str, ...]] = {
    "industry_sector": INDUSTRY_SECTORS,
    "employee_band": EMPLOYEE_BANDS,
    "years_in_operation": YEARS_IN_OPERATION,
    "region": REGIONS,
    "current_ai_stage": AI_ADOPTION_STAGES,
}

# Sector and country are open fields: the lists above are suggestions for the
# dropdowns, not a closed set. A fixed list of five sectors and five countries
# can't describe companies globally -- the first real survey run returned Real
# Estate, Asset Management, Events, Transportation and Canada, none of which
# were on the list. Anything non-empty is accepted for these two.
#
# The other three stay closed on purpose. They aren't descriptive labels, they
# are ordered scales the tool reasons about: current_ai_stage is the outcome
# variable that empirical weighting would be derived against, and size and age
# are bands rather than free text. Variants of those get normalised by the
# aliases below rather than accepted as-is.
OPEN_FIELDS: frozenset = frozenset({"industry_sector", "region"})

# A bare "Other" carries no information, so it is rejected and the respondent
# is asked to say what the other is. Their answer becomes the stored value.
NEEDS_SPECIFIC_VALUE: Tuple[str, ...] = ("other", "others", "n/a", "na", "none")

# Common ways the closed fields get written in a real export, mapped back to
# the canonical value. Matching is done on a lowercased, stripped copy.
CATEGORY_ALIASES: Dict[str, Dict[str, str]] = {
    "employee_band": {
        # The spelled-out forms are what the readable CSV writes, to stop
        # Excel turning "10-49" into a date. They have to read back in.
        "1-9": "1-9", "1 to 9": "1-9", "1-9 employees": "1-9",
        "1 to 9 employees": "1-9", "under 10": "1-9",
        "less than 10": "1-9", "micro": "1-9",
        "10-49": "10-49", "10 to 49": "10-49", "10-49 employees": "10-49",
        "10 to 49 employees": "10-49", "small": "10-49",
        "50-249": "50-249", "50 to 249": "50-249",
        "50-249 employees": "50-249", "50 to 249 employees": "50-249",
        "medium": "50-249",
        "250+": "250+", "250 or more": "250+", "250+ employees": "250+",
        "more than 250": "250+", "large": "250+",
    },
    "years_in_operation": {
        "under 2 years": "Under 2 years", "under 2": "Under 2 years",
        "less than 2 years": "Under 2 years", "<2 years": "Under 2 years",
        "2-5 years": "2-5 years", "2 to 5 years": "2-5 years",
        "6-10 years": "6-10 years", "6 to 10 years": "6-10 years",
        "5-10 years": "6-10 years",
        "10+ years": "10+ years", "over 10 years": "10+ years",
        "more than 10 years": "10+ years", "10 or more years": "10+ years",
    },
    "current_ai_stage": {
        "not considering": "Not considering", "none": "Not considering",
        "no plans": "Not considering", "not started": "Not considering",
        "exploring": "Exploring", "researching": "Exploring",
        "considering": "Exploring", "planning": "Exploring",
        "piloting": "Piloting", "pilot": "Piloting", "testing": "Piloting",
        "trialling": "Piloting", "trialing": "Piloting",
        "actively using": "Actively Using", "using": "Actively Using",
        "in production": "Actively Using", "deployed": "Actively Using",
        "fully integrated": "Fully Integrated", "integrated": "Fully Integrated",
        "embedded": "Fully Integrated",
    },
}


def normalise_category(field_name: str, value: object) -> Optional[str]:
    """
    Tidy a categorical value into the form the tool stores.

    Open fields are returned trimmed, exactly as the respondent wrote them.
    Closed fields are matched against their aliases so that "250+ employees"
    or "Using" from someone else's export lands on the right band. A value
    that matches nothing comes back unchanged, so validation can report it
    rather than this function quietly inventing a category.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if field_name in OPEN_FIELDS:
        # Open fields are tidied by the plausibility checks, which also settle
        # casing and resolve "UAE"/"Dubai"/"United Arab Emirates" onto one
        # country so the breakdowns don't split a single place into three.
        from .open_value_checks import check_open_value

        cleaned, _ = check_open_value(field_name, text)
        return cleaned if cleaned is not None else text

    allowed = CATEGORICAL_FIELDS.get(field_name, ())
    for option in allowed:
        if text.lower() == option.lower():
            return option
    return CATEGORY_ALIASES.get(field_name, {}).get(text.lower(), text)


# Word answers, so an export that never converted the scale to numbers still
# loads. The wording identifies the value on its own -- "Agree" is a 4 whether
# or not a 4 was ever written next to it.
RATING_FROM_TEXT: Dict[str, int] = {
    "strongly disagree": 1, "strongly  disagree": 1, "str disagree": 1,
    "strongly disagre": 1, "very dissatisfied": 1,
    "disagree": 2, "somewhat disagree": 2, "slightly disagree": 2,
    "neutral": 3, "neither": 3, "neither agree nor disagree": 3,
    "no opinion": 3, "undecided": 3,
    "agree": 4, "somewhat agree": 4, "slightly agree": 4,
    "strongly agree": 5, "strongly  agree": 5, "str agree": 5,
    "very satisfied": 5,
}


def parse_rating(value: object) -> Optional[int]:
    """
    Turn whatever is in a response cell into a 1-5 value, or None.

    Handles the number itself, the number as text, and the wording on its own.
    Returns None when the cell is blank or can't be read, so the caller decides
    whether that's a skipped question or a broken file.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if RATING_MIN <= value <= RATING_MAX else None
    if isinstance(value, float):
        rounded = int(round(value))
        return rounded if RATING_MIN <= rounded <= RATING_MAX else None

    text = str(value).strip()
    if not text:
        return None

    # "4" or "4 - Agree" or "4 — Agree"
    head = text.replace("—", "-").split("-")[0].strip()
    if head.isdigit():
        number = int(head)
        if RATING_MIN <= number <= RATING_MAX:
            return number

    cleaned = " ".join(text.lower().replace("_", " ").split())
    if cleaned in RATING_FROM_TEXT:
        return RATING_FROM_TEXT[cleaned]

    # Last resort: a cell like "Agree (4)" or "Response: strongly agree"
    for phrase, number in sorted(
        RATING_FROM_TEXT.items(), key=lambda kv: -len(kv[0])
    ):
        if phrase in cleaned:
            return number
    return None


# ---------------------------------------------------------------------------
# 4. Score bands and selection thresholds
# ---------------------------------------------------------------------------
# All factor and overall scores are normalised to 0-100 so that they are
# directly comparable and easy to present. On the 1-5 rating scale:
#
#       all "Strongly Disagree" (1) ->   0
#       all "Disagree"          (2) ->  25
#       all "Neutral"           (3) ->  50
#       all "Agree"             (4) ->  75
#       all "Strongly Agree"    (5) -> 100
#
# The band boundaries below are chosen against those anchor points: "Advanced"
# begins at 70, just below a uniform "Agree" response, and "Emerging" ends at 40,
# between a uniform "Disagree" and a uniform "Neutral".

@dataclass(frozen=True)
class ReadinessBand:
    label: str
    lower: float          # inclusive
    upper: float          # exclusive (except for the top band)
    description: str


READINESS_BANDS: Tuple[ReadinessBand, ...] = (
    ReadinessBand(
        label="Emerging",
        lower=0.0,
        upper=40.0,
        description=(
            "Foundational gaps across several areas. AI adoption is likely to "
            "stall unless the underlying capabilities are addressed first."
        ),
    ),
    ReadinessBand(
        label="Developing",
        lower=40.0,
        upper=70.0,
        description=(
            "Some enabling conditions are in place but there are clear gaps. "
            "Targeted improvement in the weakest factors is needed before or "
            "alongside adoption."
        ),
    ),
    ReadinessBand(
        label="Advanced",
        lower=70.0,
        upper=100.0,
        description=(
            "Most enabling conditions are in place. The organisation is well "
            "positioned to adopt AI, with remaining effort focused on refinement."
        ),
    ),
)

# A factor at or above this score is reported as a strength.
STRENGTH_THRESHOLD: float = 70.0

# A factor below this score is reported as a barrier.
BARRIER_THRESHOLD: float = 50.0

# An individual item below this score is reported as a subfactor-level gap.
ITEM_BARRIER_THRESHOLD: float = 50.0

# Caps on how many strengths / barriers / recommendations are surfaced, so the
# generated profile stays readable rather than listing everything.
MAX_STRENGTHS: int = 3
MAX_BARRIERS: int = 3
MAX_ITEM_BARRIERS: int = 5
MAX_RECOMMENDATIONS: int = 8

# Without this cap, a single very weak factor fills the entire subfactor list
# (all five Data items, for instance) and crowds every other area out of the
# recommendations. Limiting how many items one factor may contribute keeps the
# reported gaps spread across the profile, which is what makes the output
# actionable rather than repetitive.
MAX_ITEM_BARRIERS_PER_FACTOR: int = 2


# ---------------------------------------------------------------------------
# 5. Helper functions
# ---------------------------------------------------------------------------

def normalise_rating(mean_value: float) -> float:
    """Convert a mean rating value (1-5) to a 0-100 score."""
    return (mean_value - RATING_MIN) / (RATING_MAX - RATING_MIN) * 100.0


def apply_reverse(raw_value: int, reverse: bool) -> int:
    """Re-code a reverse-worded item so that higher always means more ready."""
    return (REVERSE_PIVOT - raw_value) if reverse else raw_value


def band_for_score(score: float) -> ReadinessBand:
    """Return the ReadinessBand a 0-100 score falls into."""
    for band in READINESS_BANDS:
        if band.lower <= score < band.upper:
            return band
    # Top of the range is inclusive.
    return READINESS_BANDS[-1]


def validate_configuration() -> List[str]:
    """
    Self-check on the configuration itself.

    Called by the test suite so that a mistake in this file (a duplicated item
    id, weights that no longer sum to 1.0) fails loudly rather than silently
    distorting every score.
    """
    errors: List[str] = []

    total_weight = sum(f.weight for f in FACTORS)
    if abs(total_weight - 1.0) > 1e-9:
        errors.append(f"Factor weights must sum to 1.0, got {total_weight!r}.")

    seen: set = set()
    for item in ALL_ITEMS:
        if item.id in seen:
            errors.append(f"Duplicate item id: {item.id}")
        seen.add(item.id)

    for factor in FACTORS:
        if not factor.items:
            errors.append(f"Factor {factor.id} has no items.")
        if factor.weight < 0:
            errors.append(f"Factor {factor.id} has a negative weight.")

    covered = 0.0
    for band in READINESS_BANDS:
        if band.lower != covered:
            errors.append(f"Band {band.label} does not start where the previous band ended.")
        covered = band.upper
    if covered != 100.0:
        errors.append("Readiness bands do not cover the full 0-100 range.")

    return errors
