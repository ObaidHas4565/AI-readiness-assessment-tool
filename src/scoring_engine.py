"""
ScoringEngine
=============

Turns a validated CompanyProfile into an AssessmentResults object.

Method (Chapter 4, scoring methodology):

  1. Re-code reverse-worded items so that 5 always means "more ready".
  2. Average the re-coded items within each factor -> a 1-5 factor mean.
  3. Normalise each factor mean to 0-100.
  4. Combine factor scores using the weights in ScoreConfiguration to produce
     the overall readiness score.
  5. Assign a readiness tier from the score bands.
  6. Select strengths, factor-level barriers and item-level (subfactor) gaps.

The engine holds no state between assessments and performs no I/O, which is
what satisfies the Reliability requirement: identical input always produces
identical output.
"""

from __future__ import annotations

from typing import Dict, List

from .assessment_results import AssessmentResults, FactorScore, ItemScore
from .company_profile import CompanyProfile, ValidationError
from . import score_configuration as cfg


class ScoringEngine:
    """Applies ScoreConfiguration to a CompanyProfile."""

    def __init__(self, configuration=cfg) -> None:
        # Injecting the configuration module keeps the engine testable against
        # an alternative weighting without editing this class.
        self.cfg = configuration

    # ------------------------------------------------------------------

    def score(self, profile: CompanyProfile, validate: bool = True,
              allow_partial: bool = False) -> AssessmentResults:
        """
        Score a company profile.

        Parameters
        ----------
        validate:
            Left on by default as a safety net. The dashboard validates before
            calling, per the Session Diagram, so in the running application
            this check should never be the thing that catches a problem.
        allow_partial:
            Score from whatever answers are present rather than requiring all
            32. Off by default, because a person filling the questionnaire in
            should finish it. Turned on for datasets from elsewhere, which
            often cover some factors and not others -- refusing those outright
            throws away a real reading on the factors they do cover. A factor
            with no answers at all is left out entirely rather than scored as
            zero, and the overall score is re-weighted across the factors that
            remain, so absence never masquerades as weakness.
        """
        if validate and not allow_partial:
            profile.raise_if_invalid()

        factor_scores: Dict[str, FactorScore] = {}

        for factor in self.cfg.FACTORS:
            item_scores = self._score_items(factor, profile, allow_partial)
            if not item_scores:
                continue

            mean_rating = sum(i.adjusted_value for i in item_scores) / len(item_scores)
            score_0_100 = self.cfg.normalise_rating(mean_rating)
            band = self.cfg.band_for_score(score_0_100)

            factor_scores[factor.id] = FactorScore(
                factor_id=factor.id,
                name=factor.name,
                weight=factor.weight,
                mean_rating=mean_rating,
                score=score_0_100,
                band_label=band.label,
                weighted_contribution=score_0_100 * factor.weight,
                item_scores=item_scores,
                answered=len(item_scores),
                expected=len(factor.items),
            )

        if not factor_scores:
            raise ValidationError("No answers could be scored.")

        # Re-weight across the factors actually present. With every factor
        # answered this divides by 1.0 and changes nothing.
        total_weight = sum(f.weight for f in factor_scores.values())
        overall = sum(
            f.weighted_contribution for f in factor_scores.values()
        ) / total_weight if total_weight else 0.0
        overall_band = self.cfg.band_for_score(overall)

        return AssessmentResults(
            overall_score=overall,
            readiness_tier=overall_band.label,
            tier_description=overall_band.description,
            factor_scores=factor_scores,
            strengths=self._select_strengths(factor_scores),
            barriers=self._select_barriers(factor_scores),
            item_barriers=self._select_item_barriers(factor_scores),
            context=profile.context_summary(),
            notes=profile.notes(),
            partial=any(f.is_partial for f in factor_scores.values())
            or len(factor_scores) < len(self.cfg.FACTORS),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _score_items(self, factor, profile: CompanyProfile,
                     allow_partial: bool = False) -> List[ItemScore]:
        scores: List[ItemScore] = []
        for item in factor.items:
            value = profile.responses.get(item.id)
            if value is None:
                if allow_partial:
                    continue
                raise ValidationError(f"{item.id} was not answered.")
            try:
                raw = int(value)
            except (TypeError, ValueError):
                if allow_partial:
                    continue
                raise ValidationError(f"{item.id} is not a number: {value!r}")
            if not (self.cfg.RATING_MIN <= raw <= self.cfg.RATING_MAX):
                if allow_partial:
                    continue
                raise ValidationError(f"{item.id} is out of range: {raw}")
            adjusted = self.cfg.apply_reverse(raw, item.reverse)
            scores.append(
                ItemScore(
                    item_id=item.id,
                    text=item.text,
                    factor_id=factor.id,
                    factor_name=factor.name,
                    raw_value=raw,
                    adjusted_value=adjusted,
                    reverse=item.reverse,
                    score=self.cfg.normalise_rating(adjusted),
                )
            )
        return scores

    def _select_strengths(self, factor_scores: Dict[str, FactorScore]) -> List[FactorScore]:
        strong = [f for f in factor_scores.values() if f.score >= self.cfg.STRENGTH_THRESHOLD]
        strong.sort(key=lambda f: f.score, reverse=True)
        return strong[: self.cfg.MAX_STRENGTHS]

    def _select_barriers(self, factor_scores: Dict[str, FactorScore]) -> List[FactorScore]:
        weak = [f for f in factor_scores.values() if f.score < self.cfg.BARRIER_THRESHOLD]
        # Ranked by weight-adjusted gap, so the barriers listed first are the
        # ones whose improvement would move the overall score the most.
        weak.sort(key=lambda f: f.impact, reverse=True)
        return weak[: self.cfg.MAX_BARRIERS]

    def _select_item_barriers(self, factor_scores: Dict[str, FactorScore]) -> List[ItemScore]:
        """
        Select the weakest individual items, capped per factor.

        The per-factor cap matters: without it a single very weak factor fills
        the whole list with its own items and the profile reports the same
        problem five times instead of showing the spread of gaps.
        """
        candidates = [
            i
            for f in factor_scores.values()
            for i in f.item_scores
            if i.score < self.cfg.ITEM_BARRIER_THRESHOLD
        ]
        candidates.sort(key=lambda i: i.score)

        selected: List[ItemScore] = []
        per_factor: Dict[str, int] = {}
        for item in candidates:
            if per_factor.get(item.factor_id, 0) >= self.cfg.MAX_ITEM_BARRIERS_PER_FACTOR:
                continue
            selected.append(item)
            per_factor[item.factor_id] = per_factor.get(item.factor_id, 0) + 1
            if len(selected) >= self.cfg.MAX_ITEM_BARRIERS:
                break

        return selected
