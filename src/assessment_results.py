"""
AssessmentResults
=================

The output object produced by the ScoringEngine and consumed by the
RecommendationEngine, the dashboard and the export service.

Per the Class Diagram, this is the boundary between scoring and recommendation:
the RecommendationEngine reads the barriers recorded here and never touches the
raw CompanyProfile. Keeping that boundary explicit is what allows the scoring
logic and the recommendation logic to be revised independently.

Nothing here is persisted. Results exist in memory for the duration of the
session only, matching the Session Diagram's no-database design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ItemScore:
    """Score for a single Likert item (subfactor)."""

    item_id: str
    text: str
    factor_id: str
    factor_name: str
    raw_value: int          # exactly as the user answered (1-5)
    adjusted_value: int     # after reverse-coding, so 5 always == more ready
    reverse: bool
    score: float            # adjusted_value normalised to 0-100

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"{self.item_id} ({self.score:.0f}/100): {self.text}"


@dataclass(frozen=True)
class FactorScore:
    """Aggregated score for one readiness factor."""

    factor_id: str
    name: str
    weight: float
    mean_likert: float          # 1-5
    score: float                # 0-100
    band_label: str
    weighted_contribution: float  # score * weight, contribution to the overall
    item_scores: List[ItemScore] = field(default_factory=list)

    @property
    def gap(self) -> float:
        """Distance from a perfect score -- the headroom available."""
        return 100.0 - self.score

    @property
    def impact(self) -> float:
        """
        Weight-adjusted size of the gap.

        Used to prioritise recommendations: closing a large gap on a heavily
        weighted factor moves the overall score more than closing a small gap
        on a lightly weighted one.
        """
        return self.gap * self.weight

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"{self.name}: {self.score:.1f}/100 ({self.band_label})"


@dataclass(frozen=True)
class Recommendation:
    """A single suggested action, produced by the RecommendationEngine."""

    factor_id: str
    factor_name: str
    severity: str          # "critical" | "moderate" | "refine"
    title: str
    action: str
    # Populated when the recommendation was triggered by one specific item
    # rather than by the factor as a whole.
    triggered_by_item: Optional[str] = None
    priority: float = 0.0  # higher == address sooner

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"[{self.severity}] {self.factor_name} - {self.title}"


@dataclass
class AssessmentResults:
    """
    The complete AI readiness profile for one submitted company.

    `recommendations` is populated separately by the RecommendationEngine; the
    ScoringEngine leaves it empty. That ordering mirrors the Session Diagram,
    where the dashboard invokes the two engines in turn rather than one calling
    the other.
    """

    overall_score: float
    readiness_tier: str
    tier_description: str

    factor_scores: Dict[str, FactorScore] = field(default_factory=dict)
    strengths: List[FactorScore] = field(default_factory=list)
    barriers: List[FactorScore] = field(default_factory=list)
    item_barriers: List[ItemScore] = field(default_factory=list)
    recommendations: List[Recommendation] = field(default_factory=list)

    context: Dict[str, Optional[str]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience accessors used by the dashboard and export service
    # ------------------------------------------------------------------

    def ordered_factors(self, descending: bool = True) -> List[FactorScore]:
        """Factor scores sorted by score -- the order the bar chart should use."""
        return sorted(
            self.factor_scores.values(),
            key=lambda f: f.score,
            reverse=descending,
        )

    def factor(self, factor_id: str) -> FactorScore:
        return self.factor_scores[factor_id]

    def to_dict(self) -> Dict[str, Any]:
        """Flat, serialisable view -- the basis for the PDF/Excel export."""
        return {
            "overall_score": round(self.overall_score, 2),
            "readiness_tier": self.readiness_tier,
            "tier_description": self.tier_description,
            "context": dict(self.context),
            "factors": [
                {
                    "factor_id": f.factor_id,
                    "name": f.name,
                    "weight": round(f.weight, 4),
                    "mean_likert": round(f.mean_likert, 3),
                    "score": round(f.score, 2),
                    "band": f.band_label,
                    "weighted_contribution": round(f.weighted_contribution, 3),
                }
                for f in self.ordered_factors()
            ],
            "items": [
                {
                    "item_id": i.item_id,
                    "factor_id": i.factor_id,
                    "text": i.text,
                    "raw_value": i.raw_value,
                    "adjusted_value": i.adjusted_value,
                    "reverse": i.reverse,
                    "score": round(i.score, 2),
                }
                for f in self.ordered_factors()
                for i in f.item_scores
            ],
            "strengths": [f.name for f in self.strengths],
            "barriers": [f.name for f in self.barriers],
            "item_barriers": [
                {"item_id": i.item_id, "text": i.text, "score": round(i.score, 2)}
                for i in self.item_barriers
            ],
            "recommendations": [
                {
                    "factor": r.factor_name,
                    "severity": r.severity,
                    "title": r.title,
                    "action": r.action,
                    "triggered_by_item": r.triggered_by_item,
                }
                for r in self.recommendations
            ],
        }
