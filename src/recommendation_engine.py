"""
RecommendationEngine
====================

Maps identified gaps onto concrete suggested actions.

Per the Class Diagram, this engine depends on the barriers recorded in
AssessmentResults and NOT on the raw CompanyProfile: it is not involved in
validation or scoring, and it never re-reads the user's answers. Everything it
needs -- which factors are weak, how weak, and which individual items dragged
them down -- is already present on the results object.

Two levels of rule are applied:

  * Factor-level  -- triggered by a factor's score band, giving the broad
                     programme of work for that area.
  * Item-level    -- triggered by a specific low-scoring item (a subfactor),
                     giving a targeted action for that precise gap.

Recommendations are returned in priority order, where priority is the
weight-adjusted size of the gap. This directly serves FR6 and the objective of
suggesting actions for weaker areas.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .assessment_results import AssessmentResults, Recommendation
from . import score_configuration as cfg


# ---------------------------------------------------------------------------
# Severity bands
# ---------------------------------------------------------------------------
# "critical" and "moderate" together cover the barrier range (< 50). "refine"
# covers factors that are not barriers but still sit below the Advanced band,
# so the tool has something useful to say to a mid-scoring company rather than
# only to a weak one.

SEVERITY_CRITICAL = "critical"
SEVERITY_MODERATE = "moderate"
SEVERITY_REFINE = "refine"

CRITICAL_BELOW: float = 35.0
MODERATE_BELOW: float = 50.0
REFINE_BELOW: float = 70.0


def severity_for(score: float) -> str | None:
    if score < CRITICAL_BELOW:
        return SEVERITY_CRITICAL
    if score < MODERATE_BELOW:
        return SEVERITY_MODERATE
    if score < REFINE_BELOW:
        return SEVERITY_REFINE
    return None


# ---------------------------------------------------------------------------
# Factor-level rules: factor_id -> severity -> (title, action)
# ---------------------------------------------------------------------------

FACTOR_RULES: Dict[str, Dict[str, Tuple[str, str]]] = {
    "budget": {
        SEVERITY_CRITICAL: (
            "Establish any AI budget at all before committing to tools",
            "There is currently no financial basis for adoption. Rather than "
            "seeking a large budget, ring-fence a small fixed experimentation "
            "amount for one low-cost pilot, and frame the request around a "
            "single measurable process cost so the investment case is concrete.",
        ),
        SEVERITY_MODERATE: (
            "Convert ad-hoc spending into a defined AI budget line",
            "Funding appears to be available in principle but is not committed. "
            "Define a named budget line for the next 12 months, however small, "
            "and attach it to a specific use case with an expected return, since "
            "leadership approval is more likely where the return is shown.",
        ),
        SEVERITY_REFINE: (
            "Protect the AI budget against being reallocated",
            "Funding is broadly in place. Guard against it being absorbed by "
            "other priorities by separating run costs from experimentation "
            "costs, and review the split at each budget cycle.",
        ),
    },
    "workforce": {
        SEVERITY_CRITICAL: (
            "Address the skills base before tool selection",
            "Adopting tools ahead of the skills to run them is a leading cause "
            "of failed adoption. Start with baseline AI literacy for the whole "
            "team rather than deep technical training for a few, and identify "
            "one internal person to own the capability.",
        ),
        SEVERITY_MODERATE: (
            "Close the specific skill gaps blocking adoption",
            "Some capability exists but there are known gaps. Turn the gaps into "
            "a short written training plan with named owners and dates, and "
            "prioritise the skills needed by the first intended use case rather "
            "than general upskilling.",
        ),
        SEVERITY_REFINE: (
            "Broaden capability beyond the early adopters",
            "Skills are reasonable but likely concentrated. Spread capability "
            "through peer sessions or internal documentation so that adoption "
            "does not depend on a small number of individuals.",
        ),
    },
    "leadership": {
        SEVERITY_CRITICAL: (
            "Secure visible leadership sponsorship first",
            "Without leadership backing, other readiness work tends not to "
            "survive contact with competing priorities. Seek a named executive "
            "sponsor and a short written statement of why AI matters to the "
            "business before investing further effort elsewhere.",
        ),
        SEVERITY_MODERATE: (
            "Turn general support into a stated strategy",
            "Leadership is not opposed but direction is unclear. Document how AI "
            "is expected to support two or three specific business goals, and "
            "communicate it to staff, since stated vision is what converts "
            "support into decisions.",
        ),
        SEVERITY_REFINE: (
            "Improve how the AI direction is communicated",
            "Direction exists but may not be reaching staff consistently. Add AI "
            "progress as a standing item in existing all-hands or team meetings "
            "rather than creating a separate communication channel.",
        ),
    },
    "data": {
        SEVERITY_CRITICAL: (
            "Treat data preparation as the first project, not a prerequisite",
            "Data in its current state is unlikely to support a working AI tool. "
            "Scope a data clean-up on one dataset tied to one intended use case, "
            "rather than an organisation-wide data programme, which rarely "
            "completes at smaller scale.",
        ),
        SEVERITY_MODERATE: (
            "Improve organisation and governance of existing data",
            "Data exists but is not reliably usable. Document where key data "
            "lives, who owns it and how it is maintained, and fix accessibility "
            "for the one or two datasets an initial AI use case would need.",
        ),
        SEVERITY_REFINE: (
            "Formalise data quality checks",
            "Data is broadly usable. Add routine quality checks and a named data "
            "owner so quality does not drift once AI systems begin depending on "
            "it.",
        ),
    },
    "technology": {
        SEVERITY_CRITICAL: (
            "Resolve infrastructure constraints before adoption",
            "Current systems are unlikely to support AI tools. Favour hosted or "
            "cloud-based options that avoid the existing infrastructure "
            "entirely for a first pilot, while planning the necessary upgrades "
            "separately.",
        ),
        SEVERITY_MODERATE: (
            "Close the integration and support gaps",
            "Infrastructure is partially ready. Identify which systems an AI "
            "tool would need to connect to, confirm whether they expose an "
            "interface for that, and establish who maintains the tool once it "
            "is live.",
        ),
        SEVERITY_REFINE: (
            "Plan for maintenance, not just deployment",
            "Infrastructure is adequate. Confirm ongoing IT support capacity for "
            "AI tools specifically, as maintenance load is commonly "
            "underestimated relative to initial setup.",
        ),
    },
    "culture": {
        SEVERITY_CRITICAL: (
            "Address resistance before introducing tools",
            "Introducing AI into a resistant culture tends to entrench "
            "opposition. Involve staff in identifying which of their own tasks "
            "are worth automating, so that adoption is experienced as relief "
            "rather than as imposition.",
        ),
        SEVERITY_MODERATE: (
            "Build openness through a low-stakes pilot",
            "Openness is mixed. Run a small visible pilot in a team that is "
            "already willing, and publicise the result internally, including "
            "what did not work, to establish that experimentation is safe.",
        ),
        SEVERITY_REFINE: (
            "Make innovation discussion routine",
            "Culture is broadly supportive. Give innovation a regular forum so "
            "that it continues without depending on individual enthusiasm.",
        ),
    },
    "governance": {
        SEVERITY_CRITICAL: (
            "Establish basic AI governance before deployment",
            "Adopting AI without privacy, accountability or oversight structures "
            "creates regulatory and reputational exposure. Confirm which data "
            "protection obligations apply, and name a person accountable for "
            "AI-related decisions before any tool handles company or customer "
            "data.",
        ),
        SEVERITY_MODERATE: (
            "Formalise oversight and build ethical awareness",
            "Some awareness exists but structures are incomplete. Write a short "
            "acceptable-use position covering what AI tools may and may not be "
            "used for, and brief staff on bias and transparency risks.",
        ),
        SEVERITY_REFINE: (
            "Extend existing governance to cover AI specifically",
            "Governance is largely in place. Extend current technology oversight "
            "to name AI explicitly, including how outputs are reviewed before "
            "they inform decisions.",
        ),
    },
}


# ---------------------------------------------------------------------------
# Item-level rules: item_id -> (title, action)
# ---------------------------------------------------------------------------
# Triggered only when that specific item scores below the item barrier
# threshold. These are the subfactor-level recommendations required by FR6.

ITEM_ACTIONS: Dict[str, Tuple[str, str]] = {
    # --- Budget & Financial Readiness ---
    "BUD_1": (
        "No dedicated AI budget",
        "Ring-fence a defined amount for AI experimentation, separate from "
        "general IT spend, so pilots are not competing with routine costs.",
    ),
    "BUD_2": (
        "Cost is reported as the active barrier",
        "Focus on use cases with low entry cost and short payback, such as "
        "subscription tools applied to an existing manual task, rather than "
        "custom development.",
    ),
    "BUD_3": (
        "Limited access to external funding",
        "Check eligibility for regional SME digital adoption grants and "
        "technology partner credits, which are commonly available but "
        "under-claimed at smaller company sizes.",
    ),
    "BUD_4": (
        "Investment approval is uncertain even with a clear return",
        "Establish what evidence decision-makers would actually accept as proof "
        "of return, and design the first pilot to produce exactly that measure.",
    ),
    # --- Workforce & Skill Readiness ---
    "WRK_1": (
        "Staff lack the technical skills to use AI tools effectively",
        "Prioritise tools with minimal technical overhead for the first "
        "adoption, and provide short applied training on the specific tool "
        "rather than general AI theory.",
    ),
    "WRK_2": (
        "No training provision for AI-related skills",
        "Introduce a modest recurring training commitment, such as a monthly "
        "session, since sustained low-intensity training outperforms one-off "
        "workshops for capability building.",
    ),
    "WRK_3": (
        "Skill gaps are identified as blocking adoption",
        "Convert the known gaps into a written plan stating which roles need "
        "which skills by when, and decide for each whether it will be met by "
        "training, hiring or an external partner.",
    ),
    "WRK_4": (
        "Staff are not open to using AI tools",
        "Address the concern directly by clarifying how AI will affect roles, "
        "as unaddressed job-security concerns are a common driver of "
        "resistance.",
    ),
    # --- Leadership & Strategic Readiness ---
    "LDR_1": (
        "Leadership treats AI adoption as low priority",
        "Present a short business case tied to a current operational pain "
        "point, since competing priorities are usually displaced by relevance "
        "rather than by advocacy.",
    ),
    "LDR_2": (
        "Leadership does not actively support AI initiatives",
        "Identify a single senior sponsor willing to back one pilot, rather "
        "than seeking broad leadership consensus up front.",
    ),
    "LDR_3": (
        "No clear strategic vision for AI",
        "Write a brief statement linking AI to two or three existing business "
        "goals, so that tool choices can be assessed against stated intent.",
    ),
    "LDR_4": (
        "Reasons and benefits of AI are not communicated to staff",
        "Communicate the intent behind AI adoption before tools appear, as "
        "unexplained technology change reliably increases resistance.",
    ),
    "LDR_5": (
        "Decision-makers do not understand AI capabilities and limitations",
        "Provide a short briefing for decision-makers covering realistic "
        "capability and known limitations, to reduce both over-expectation and "
        "unnecessary caution.",
    ),
    # --- Data Readiness ---
    "DAT_1": (
        "Company data is not well-organised or accessible",
        "Map where key data currently sits and consolidate the datasets "
        "relevant to the intended use case into a single accessible location.",
    ),
    "DAT_2": (
        "Existing data is not trusted for quality or accuracy",
        "Profile one priority dataset for completeness, duplication and "
        "consistency, and fix that dataset before extending the exercise.",
    ),
    "DAT_3": (
        "No processes for managing and governing data",
        "Assign ownership for key datasets and document basic rules for how "
        "data is entered, updated and retained.",
    ),
    "DAT_4": (
        "Unable to supply the data an AI tool would require",
        "Determine what data the intended use case actually needs and whether "
        "it is currently captured at all, since unrecorded data is a different "
        "problem from disorganised data.",
    ),
    "DAT_5": (
        "Poor data quality is reported as the active barrier",
        "Scope a focused remediation on the single dataset blocking progress "
        "rather than an organisation-wide data programme.",
    ),
    # --- Technology & IT Infrastructure Readiness ---
    "TEC_1": (
        "Current IT infrastructure cannot support AI tools",
        "Consider cloud-hosted AI services for initial adoption, which shift "
        "infrastructure requirements to the provider and avoid upfront "
        "capital cost.",
    ),
    "TEC_2": (
        "Systems are not integrated and may not connect to AI tools",
        "Establish whether the core systems involved expose an API or export "
        "capability, as this determines whether integration or manual data "
        "transfer is required.",
    ),
    "TEC_3": (
        "No IT support capable of maintaining AI tools",
        "Confirm who will maintain the tool after deployment, and where no "
        "internal capacity exists, favour managed or vendor-supported options.",
    ),
    "TEC_4": (
        "No track record of successfully adopting new digital tools",
        "Build adoption experience with a smaller, lower-risk digital change "
        "first, as prior successful adoption is a strong predictor of "
        "subsequent success.",
    ),
    "TEC_5": (
        "Outdated or incompatible technology is the active barrier",
        "Identify which specific system is the constraint and whether it must "
        "be replaced or can be bypassed for an initial pilot.",
    ),
    # --- Organizational Cultural Readiness ---
    "CUL_1": (
        "The organisation is not generally open to new technology",
        "Introduce change through a team that is already receptive, and use its "
        "result as internal evidence rather than arguing the case abstractly.",
    ),
    "CUL_2": (
        "Employees are resistant to changes in how they work",
        "Involve affected staff in choosing which tasks to automate, since "
        "participation in the decision reduces resistance more effectively than "
        "communication after it.",
    ),
    "CUL_3": (
        "Failed pilots are treated as failures rather than learning",
        "State explicitly that pilots may be discontinued without blame, as "
        "fear of failure suppresses the experimentation that adoption depends "
        "on.",
    ),
    "CUL_4": (
        "Innovation and new technology are not discussed company-wide",
        "Create a regular low-effort forum for surfacing ideas, such as a "
        "standing agenda item in an existing meeting.",
    ),
    # --- Governance, Ethics & Trust ---
    "GOV_1": (
        "Low confidence in managing data privacy and security under AI",
        "Establish what data would be sent to any AI tool and where it would be "
        "processed, and confirm this against applicable data protection "
        "obligations before adoption.",
    ),
    "GOV_2": (
        "Limited awareness of AI ethical issues",
        "Brief relevant staff on bias, transparency and appropriate use, so "
        "that risks are recognised before outputs are relied upon.",
    ),
    "GOV_3": (
        "No clear accountability or oversight for technology decisions",
        "Name who is accountable for AI-related decisions and how those "
        "decisions are recorded, before tools are introduced.",
    ),
    "GOV_4": (
        "Low trust in AI outputs",
        "Begin with use cases where outputs are human-reviewed before action, "
        "allowing trust to be established against observed accuracy.",
    ),
    "GOV_5": (
        "Compliance with privacy or security regulation would be a struggle",
        "Obtain clarity on the applicable regulatory requirements before "
        "adoption, and select tools whose data handling and hosting can "
        "demonstrably meet them.",
    ),
}


# ---------------------------------------------------------------------------

class RecommendationEngine:
    """
    Generates prioritised recommendations from an AssessmentResults object.

    The engine is stateless and reads only from the results object, never from
    the submitted CompanyProfile.
    """

    def __init__(self, configuration=cfg) -> None:
        self.cfg = configuration

    def recommend(self, results: AssessmentResults) -> List[Recommendation]:
        """
        Build the recommendation list.

        Returns the list and also assigns it onto `results.recommendations`, so
        the dashboard can either use the return value or read it back off the
        results object.
        """
        recommendations: List[Recommendation] = []

        # --- factor-level ---
        for factor_score in results.factor_scores.values():
            severity = severity_for(factor_score.score)
            if severity is None:
                continue

            rules = FACTOR_RULES.get(factor_score.factor_id, {})
            if severity not in rules:
                continue

            title, action = rules[severity]
            recommendations.append(
                Recommendation(
                    factor_id=factor_score.factor_id,
                    factor_name=factor_score.name,
                    severity=severity,
                    title=title,
                    action=action,
                    priority=factor_score.impact,
                )
            )

        # --- item-level (subfactors) ---
        for item in results.item_barriers:
            if item.item_id not in ITEM_ACTIONS:
                continue

            title, action = ITEM_ACTIONS[item.item_id]
            parent = results.factor_scores[item.factor_id]
            recommendations.append(
                Recommendation(
                    factor_id=item.factor_id,
                    factor_name=item.factor_name,
                    severity=severity_for(item.score) or SEVERITY_REFINE,
                    title=title,
                    action=action,
                    triggered_by_item=item.item_id,
                    # Item-level actions are ranked slightly below the
                    # factor-level programme they sit inside, so the broad
                    # direction is read before the specific fix.
                    priority=(100.0 - item.score) * parent.weight * 0.9,
                )
            )

        recommendations.sort(key=lambda r: r.priority, reverse=True)
        recommendations = recommendations[: self.cfg.MAX_RECOMMENDATIONS]

        results.recommendations = recommendations
        return recommendations
