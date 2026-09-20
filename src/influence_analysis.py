"""
InfluenceAnalysis
=================

Which readiness factors carry the most influence, according to the data
actually collected -- Objective 1.5.

This module is deliberately kept apart from the scoring pipeline. It reads
results that the ScoringEngine has already produced and reports on them. It
does not modify the configuration, it does not change any score, and nothing
in the assessment tool imports it. If the analysis turns out to be
unconvincing on this sample, deleting this file and its test leaves the tool
exactly as it was.

What it can and cannot claim
----------------------------
There is no experiment here and no intervention, so nothing in this module
demonstrates that one factor *causes* readiness. What it does is report four
different kinds of evidence about which factors matter, on the sample given:

  1. Association with reported adoption stage.
     `current_ai_stage` is already collected on every profile and is ordinal
     ("Not considering" through "Fully Integrated"). Correlating each factor
     score against it asks: do companies further along with AI actually score
     higher on this factor? This is the closest thing to the objective's
     wording, and it is still only correlational.

  2. Association with the rest of the profile.
     Each factor is correlated against the mean of the *other six* factors.
     The factor is excluded from the total it is compared to, so this is not
     circular. It asks: does this factor move with overall readiness, or does
     it sit apart from it?

  3. How often the factor is the binding constraint.
     How often it falls below the barrier threshold, and how often it is the
     single weakest factor in a company's profile. A factor that is almost
     always the one holding companies back is practically influential whatever
     the correlations say.

  4. How much the overall result depends on it.
     Re-scoring the same companies under different weightings and measuring
     how far the overall scores, the rankings and the tiers move. A factor the
     result is insensitive to cannot be driving it.

These are reported side by side rather than merged into one number, because
they can disagree, and the disagreement is itself a finding worth writing up.

A note on sample size
---------------------
Correlations on a small sample are unstable. Every correlation here is
accompanied by a permutation test rather than a textbook p-value: the outcome
is shuffled many times and the observed correlation is compared against the
distribution of correlations produced by chance alone. That makes no
distributional assumptions, which matters at n = 17. The report states the
sample size at the top and warns when it is too small for the numbers to be
treated as stable.

Correlation choice: adoption stage is ordinal, so Spearman (rank) correlation
is used against it. Factor-to-factor comparisons are between two continuous
0-100 scores, so Pearson is used there.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from . import score_configuration as cfg
from .assessment_results import AssessmentResults

# Below this, correlations are reported but flagged as unstable.
STABLE_N: int = 30

# Below this, the report says plainly that the correlations should be read as
# exploratory only.
EXPLORATORY_N: int = 20

# Permutation trials. 2000 is enough to place a p-value to ~0.01 and runs in
# well under a second on a sample this size.
PERMUTATION_TRIALS: int = 2000

# Fixed so that two runs on the same data give the same p-values. Reliability
# NFR: identical input, identical output.
PERMUTATION_SEED: int = 20260201

# A corrected item-total correlation at or below this suggests the item is not
# measuring what the rest of its factor measures -- often a polarity mistake.
SUSPECT_ITEM_CORRELATION: float = 0.0


# ---------------------------------------------------------------------------
# 1. Statistics, on the standard library
# ---------------------------------------------------------------------------

def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def variance(values: Sequence[float]) -> float:
    """Sample variance (n-1). Zero for fewer than two values."""
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return sum((v - mu) ** 2 for v in values) / (len(values) - 1)


def stdev(values: Sequence[float]) -> float:
    return variance(values) ** 0.5


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """
    Pearson correlation, or None when it is undefined.

    Undefined means either fewer than three pairs or one of the two series
    being constant -- a factor everyone scored identically has no correlation
    with anything, and returning 0.0 there would be a made-up number.
    """
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = mean(xs), mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return numerator / (dx * dy)


def ranks(values: Sequence[float]) -> List[float]:
    """Ranks with ties averaged, which is what Spearman requires."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        shared = (position + end) / 2.0 + 1.0
        for index in range(position, end + 1):
            result[order[index]] = shared
        position = end + 1
    return result


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Spearman rank correlation -- Pearson applied to the ranks."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    return pearson(ranks(xs), ranks(ys))


def permutation_p(xs: Sequence[float], ys: Sequence[float],
                  observed: Optional[float], *, use_ranks: bool,
                  trials: int = PERMUTATION_TRIALS,
                  seed: int = PERMUTATION_SEED) -> Optional[float]:
    """
    Two-sided p-value by shuffling.

    The second series is shuffled `trials` times and the correlation
    recomputed. The p-value is the share of shuffles that produced a
    correlation at least as strong as the observed one, in either direction.
    No normality assumption, which is the point at this sample size.
    """
    if observed is None or len(xs) < 3:
        return None
    rng = random.Random(seed)
    shuffled = list(ys)
    correlate = spearman if use_ranks else pearson
    hits = 0
    for _ in range(trials):
        rng.shuffle(shuffled)
        value = correlate(xs, shuffled)
        if value is not None and abs(value) >= abs(observed) - 1e-12:
            hits += 1
    # Add-one correction: a p-value of exactly zero overstates what a finite
    # number of shuffles can show.
    return (hits + 1) / (trials + 1)


def cronbach_alpha(item_columns: Sequence[Sequence[float]]) -> Optional[float]:
    """
    Cronbach's alpha over a factor's items.

    `item_columns` is one list of per-company values per item, already
    reverse-coded. Returns None when there are fewer than two items or fewer
    than two companies, or when total variance is zero.

    Alpha is reported here as a description of whether a factor's items hang
    together on this sample, not as a quality gate. At n = 17 it is itself
    imprecise, and a four-item factor is penalised by the formula relative to
    a longer one.
    """
    item_count = len(item_columns)
    if item_count < 2:
        return None
    rows = len(item_columns[0])
    if rows < 2:
        return None

    totals = [sum(column[r] for column in item_columns) for r in range(rows)]
    total_variance = variance(totals)
    if total_variance == 0:
        return None
    item_variance = sum(variance(column) for column in item_columns)
    return (item_count / (item_count - 1)) * (1 - item_variance / total_variance)


def corrected_item_total(item_columns: Sequence[Sequence[float]],
                         index: int) -> Optional[float]:
    """
    Correlate one item against the sum of the *other* items in its factor.

    Excluding the item from its own total is what makes this diagnostic. A
    negative value means the item moves opposite to everything else in its
    factor, which on a Likert instrument usually means the item's polarity is
    wrong -- it is being reverse-coded when it should not be, or vice versa.
    """
    if len(item_columns) < 2:
        return None
    rows = len(item_columns[0])
    rest = [
        sum(column[r] for j, column in enumerate(item_columns) if j != index)
        for r in range(rows)
    ]
    return pearson(item_columns[index], rest)


# ---------------------------------------------------------------------------
# 2. Pulling the numbers out of scored results
# ---------------------------------------------------------------------------

# Ordinal position of each adoption stage, 1 through 5.
STAGE_VALUES: Dict[str, int] = {
    stage: position + 1 for position, stage in enumerate(cfg.AI_ADOPTION_STAGES)
}


def outcome_values(results: Sequence[AssessmentResults]) -> List[Optional[float]]:
    """
    The reported adoption stage for each company, as 1-5, or None.

    This is the outcome variable the configuration file already identifies as
    the one empirical weighting would be derived against. It is collected on
    every profile as a required field, so on a complete survey export it is
    present without anything new being asked.
    """
    out: List[Optional[float]] = []
    for result in results:
        stage = (result.context or {}).get("current_ai_stage")
        out.append(float(STAGE_VALUES[stage]) if stage in STAGE_VALUES else None)
    return out


def factor_columns(results: Sequence[AssessmentResults]) -> Dict[str, List[Optional[float]]]:
    """Per-factor score for each company, None where the factor was not scored."""
    columns: Dict[str, List[Optional[float]]] = {f.id: [] for f in cfg.FACTORS}
    for result in results:
        for factor in cfg.FACTORS:
            scored = result.factor_scores.get(factor.id)
            columns[factor.id].append(scored.score if scored else None)
    return columns


def item_columns(results: Sequence[AssessmentResults],
                 factor_id: str) -> Tuple[List[str], List[List[float]]]:
    """
    Reverse-coded item values for one factor, over the companies that answered
    every item in it.

    Alpha and item-total correlations need a complete rectangle, so companies
    missing any item in this factor are dropped for this factor only. The
    number kept is reported alongside the result rather than hidden.
    """
    factor = cfg.FACTORS_BY_ID[factor_id]
    ids = [item.id for item in factor.items]

    rows: List[List[float]] = []
    for result in results:
        scored = result.factor_scores.get(factor_id)
        if not scored:
            continue
        values = {i.item_id: float(i.adjusted_value) for i in scored.item_scores}
        if any(item_id not in values for item_id in ids):
            continue
        rows.append([values[item_id] for item_id in ids])

    if not rows:
        return ids, []
    columns = [[row[position] for row in rows] for position in range(len(ids))]
    return ids, columns


def _paired(xs: Sequence[Optional[float]],
            ys: Sequence[Optional[float]]) -> Tuple[List[float], List[float]]:
    """Drop any pair where either side is missing."""
    left: List[float] = []
    right: List[float] = []
    for x, y in zip(xs, ys):
        if x is not None and y is not None:
            left.append(float(x))
            right.append(float(y))
    return left, right


# ---------------------------------------------------------------------------
# 3. Weighting, and how much the answer depends on it
# ---------------------------------------------------------------------------

def overall_under(result: AssessmentResults,
                  weights: Mapping[str, float]) -> Optional[float]:
    """
    Recompute one company's overall score under a different weighting.

    Mirrors the ScoringEngine exactly: weight the factor scores that are
    present and divide by the weight actually used, so a factor nobody
    answered is left out rather than counted as zero. Under equal weights this
    reproduces the engine's own number, which the test suite checks.
    """
    total_weight = 0.0
    total = 0.0
    for factor_id, scored in result.factor_scores.items():
        weight = weights.get(factor_id, 0.0)
        total += scored.score * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return total / total_weight


EQUAL_WEIGHTS: Dict[str, float] = {f.id: f.weight for f in cfg.FACTORS}


def emphasise(factor_id: str, multiplier: float = 2.0) -> Dict[str, float]:
    """Equal weights with one factor's weight multiplied, then renormalised."""
    weights = dict(EQUAL_WEIGHTS)
    weights[factor_id] = weights[factor_id] * multiplier
    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


@dataclass(frozen=True)
class WeightScenario:
    """What happens to the results when the weighting changes."""

    label: str
    weights: Dict[str, float]
    mean_absolute_shift: float      # average change in overall score, points
    largest_shift: float            # worst single company, points
    tier_changes: int               # companies that moved band
    rank_agreement: Optional[float] # Spearman against the baseline ranking

    @property
    def summary(self) -> str:
        parts = [
            f"average {self.mean_absolute_shift:.1f} points",
            f"largest {self.largest_shift:.1f}",
            f"{self.tier_changes} tier change(s)",
        ]
        if self.rank_agreement is not None:
            parts.append(f"rank agreement {self.rank_agreement:.2f}")
        return ", ".join(parts)


def compare_weighting(results: Sequence[AssessmentResults],
                      weights: Mapping[str, float],
                      label: str) -> WeightScenario:
    """Score every company both ways and measure how far the answer moved."""
    baseline: List[float] = []
    alternative: List[float] = []
    tier_changes = 0

    for result in results:
        before = overall_under(result, EQUAL_WEIGHTS)
        after = overall_under(result, weights)
        if before is None or after is None:
            continue
        baseline.append(before)
        alternative.append(after)
        if cfg.band_for_score(before).label != cfg.band_for_score(after).label:
            tier_changes += 1

    shifts = [abs(a - b) for a, b in zip(alternative, baseline)]
    return WeightScenario(
        label=label,
        weights=dict(weights),
        mean_absolute_shift=mean(shifts),
        largest_shift=max(shifts) if shifts else 0.0,
        tier_changes=tier_changes,
        rank_agreement=spearman(baseline, alternative),
    )


# ---------------------------------------------------------------------------
# 4. The per-factor picture
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FactorInfluence:
    """Everything this analysis can say about one readiness factor."""

    factor_id: str
    name: str
    scored_companies: int

    # How the factor behaves across the sample.
    mean_score: float
    sd_score: float
    lowest: float
    highest: float

    # How often it is the thing holding a company back.
    barrier_rate: float       # share scoring below the barrier threshold
    weakest_rate: float       # share where it is the company's lowest factor

    # Association with reported adoption stage (Spearman, ordinal outcome).
    outcome_r: Optional[float] = None
    outcome_p: Optional[float] = None
    outcome_n: int = 0

    # Association with the mean of the other factors (Pearson, itself excluded).
    rest_r: Optional[float] = None
    rest_p: Optional[float] = None

    # Internal coherence of the factor's own items.
    alpha: Optional[float] = None
    alpha_n: int = 0
    item_totals: Dict[str, Optional[float]] = field(default_factory=dict)

    @property
    def suspect_items(self) -> List[str]:
        """
        Items that move against the rest of their own factor.

        On a Likert instrument this is the signature of a polarity mistake, so
        these are worth checking against the original question wording before
        anything else in the analysis is trusted.
        """
        return sorted(
            item_id for item_id, value in self.item_totals.items()
            if value is not None and value <= SUSPECT_ITEM_CORRELATION
        )


@dataclass
class InfluenceReport:
    """The assembled analysis for one dataset."""

    n: int
    factors: List[FactorInfluence]
    outcome_available: bool
    outcome_spread: Dict[str, int]
    scenarios: List[WeightScenario]
    warnings: List[str]

    def by_outcome(self) -> List[FactorInfluence]:
        """Factors ordered by association with reported adoption stage."""
        rated = [f for f in self.factors if f.outcome_r is not None]
        return sorted(rated, key=lambda f: f.outcome_r, reverse=True)

    def by_rest(self) -> List[FactorInfluence]:
        rated = [f for f in self.factors if f.rest_r is not None]
        return sorted(rated, key=lambda f: f.rest_r, reverse=True)

    def by_barrier_rate(self) -> List[FactorInfluence]:
        return sorted(self.factors, key=lambda f: f.barrier_rate, reverse=True)

    def agreed_leaders(self, top: int = 3) -> List[str]:
        """
        Factors that appear near the top of more than one ordering.

        Presented as the only honest basis for saying a factor looks
        influential: a factor that leads on one measure and not the others is
        an artefact of that measure, not a finding.
        """
        appearances: Dict[str, int] = {}
        for ordering in (self.by_outcome(), self.by_rest(), self.by_barrier_rate()):
            for influence in ordering[:top]:
                appearances[influence.factor_id] = appearances.get(influence.factor_id, 0) + 1
        return sorted(
            (key for key, count in appearances.items() if count >= 2),
            key=lambda key: -appearances[key],
        )

    @property
    def polarity_flags(self) -> Dict[str, List[str]]:
        """Items flagged as moving against their own factor, by factor id."""
        return {
            influence.factor_id: influence.suspect_items
            for influence in self.factors if influence.suspect_items
        }


def analyse(results: Sequence[AssessmentResults],
            *, scenarios: bool = True,
            extra_weightings: Optional[Mapping[str, Mapping[str, float]]] = None,
            trials: int = PERMUTATION_TRIALS) -> InfluenceReport:
    """
    Run the whole analysis over a set of already-scored companies.

    `extra_weightings` accepts named alternative weight sets -- for instance a
    weighting taken from the literature -- which are compared against the
    equal-weight baseline alongside the automatic single-factor scenarios.
    Nothing is invented here: an alternative weighting has to be supplied by
    the caller, because a weight that is not grounded in either this data or a
    cited source would be a number with no provenance.
    """
    results = list(results)
    n = len(results)
    warnings: List[str] = []

    if n == 0:
        return InfluenceReport(0, [], False, {}, [], ["No scored companies supplied."])

    columns = factor_columns(results)
    outcome = outcome_values(results)
    usable_outcome = [v for v in outcome if v is not None]
    outcome_available = len(usable_outcome) >= 3 and len(set(usable_outcome)) > 1

    spread: Dict[str, int] = {}
    for result in results:
        stage = (result.context or {}).get("current_ai_stage") or "(not given)"
        spread[stage] = spread.get(stage, 0) + 1

    # --- warnings, stated up front rather than buried ---
    if n < EXPLORATORY_N:
        warnings.append(
            f"Only {n} companies. Correlations on a sample this size are "
            f"exploratory: they indicate where to look, not what is true."
        )
    elif n < STABLE_N:
        warnings.append(
            f"{n} companies is below the {STABLE_N} at which these correlations "
            f"start to settle. Treat the ordering as provisional."
        )
    if not outcome_available:
        if not usable_outcome:
            warnings.append(
                "No adoption stage was recorded, so factors cannot be compared "
                "against an outcome."
            )
        elif len(set(usable_outcome)) <= 1:
            warnings.append(
                "Every company reported the same adoption stage, so there is no "
                "variation to correlate against."
            )
    elif len(usable_outcome) < n:
        warnings.append(
            f"Adoption stage is missing for {n - len(usable_outcome)} of {n} "
            f"companies; the outcome correlations use the rest."
        )

    # --- per-factor ---
    influences: List[FactorInfluence] = []
    for factor in cfg.FACTORS:
        mine = columns[factor.id]
        present = [v for v in mine if v is not None]
        if not present:
            continue

        # The mean of the other six factors, per company.
        others: List[Optional[float]] = []
        for row in range(n):
            rest = [
                columns[other.id][row] for other in cfg.FACTORS
                if other.id != factor.id and columns[other.id][row] is not None
            ]
            others.append(mean(rest) if rest else None)

        # How often this factor is the weakest one a company has.
        weakest_count = 0
        for row in range(n):
            scores = {
                other.id: columns[other.id][row] for other in cfg.FACTORS
                if columns[other.id][row] is not None
            }
            if len(scores) > 1 and min(scores, key=lambda k: scores[k]) == factor.id:
                weakest_count += 1

        xs_out, ys_out = _paired(mine, outcome)
        outcome_r = spearman(xs_out, ys_out) if outcome_available else None
        outcome_p = permutation_p(
            xs_out, ys_out, outcome_r, use_ranks=True, trials=trials
        ) if outcome_r is not None else None

        xs_rest, ys_rest = _paired(mine, others)
        rest_r = pearson(xs_rest, ys_rest)
        rest_p = permutation_p(
            xs_rest, ys_rest, rest_r, use_ranks=False, trials=trials
        ) if rest_r is not None else None

        ids, item_cols = item_columns(results, factor.id)
        alpha = cronbach_alpha(item_cols) if item_cols else None
        totals: Dict[str, Optional[float]] = {}
        if item_cols:
            for position, item_id in enumerate(ids):
                totals[item_id] = corrected_item_total(item_cols, position)

        influences.append(
            FactorInfluence(
                factor_id=factor.id,
                name=factor.name,
                scored_companies=len(present),
                mean_score=mean(present),
                sd_score=stdev(present),
                lowest=min(present),
                highest=max(present),
                barrier_rate=100.0 * sum(
                    1 for v in present if v < cfg.BARRIER_THRESHOLD
                ) / len(present),
                weakest_rate=100.0 * weakest_count / n,
                outcome_r=outcome_r,
                outcome_p=outcome_p,
                outcome_n=len(xs_out),
                rest_r=rest_r,
                rest_p=rest_p,
                alpha=alpha,
                alpha_n=len(item_cols[0]) if item_cols else 0,
                item_totals=totals,
            )
        )

    # --- how much the weighting matters ---
    built: List[WeightScenario] = []
    if scenarios and n >= 2:
        for factor in cfg.FACTORS:
            built.append(compare_weighting(
                results,
                emphasise(factor.id, 2.0),
                f"Double the weight on {factor.name}",
            ))
        for label, weights in (extra_weightings or {}).items():
            built.append(compare_weighting(results, weights, label))

    # A polarity flag makes everything downstream suspect, so it is raised as
    # a warning and not left sitting in a table.
    for influence in influences:
        for item_id in influence.suspect_items:
            item = cfg.ITEMS_BY_ID.get(item_id)
            direction = "reverse-scored" if item and item.reverse else "scored as written"
            warnings.append(
                f"{item_id} moves against the rest of {influence.name} "
                f"(r = {influence.item_totals[item_id]:.2f}). It is currently "
                f"{direction}. Check the wording before relying on this factor."
            )

    return InfluenceReport(
        n=n,
        factors=influences,
        outcome_available=outcome_available,
        outcome_spread=spread,
        scenarios=built,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 5. Readable output
# ---------------------------------------------------------------------------

def _show(value: Optional[float], places: int = 2, dash: str = "--") -> str:
    return dash if value is None else f"{value:.{places}f}"


def format_report(report: InfluenceReport) -> str:
    """Plain-text report, sized to paste into a chapter or read in a terminal."""
    out: List[str] = []
    add = out.append

    add("FACTOR INFLUENCE ANALYSIS")
    add("=" * 74)
    add(f"Companies analysed: {report.n}")
    if report.outcome_spread:
        spread = ", ".join(
            f"{stage}: {count}"
            for stage, count in sorted(report.outcome_spread.items(),
                                       key=lambda kv: -kv[1])
        )
        add(f"Reported adoption stage: {spread}")
    add("")

    if report.warnings:
        add("READ THIS FIRST")
        add("-" * 74)
        for warning in report.warnings:
            add(f"  * {warning}")
        add("")

    add("HOW EACH FACTOR BEHAVES")
    add("-" * 74)
    add(f"{'Factor':<38}{'mean':>7}{'sd':>7}{'barrier%':>10}{'weakest%':>10}")
    for influence in sorted(report.factors, key=lambda f: f.mean_score):
        add(
            f"{influence.name[:37]:<38}"
            f"{influence.mean_score:>7.1f}"
            f"{influence.sd_score:>7.1f}"
            f"{influence.barrier_rate:>10.0f}"
            f"{influence.weakest_rate:>10.0f}"
        )
    add("")
    add("  barrier%  = share of companies scoring below "
        f"{cfg.BARRIER_THRESHOLD:.0f} on this factor")
    add("  weakest%  = share of companies whose lowest factor this is")
    add("")

    add("ASSOCIATION WITH REPORTED ADOPTION STAGE")
    add("-" * 74)
    if not report.outcome_available:
        add("  Not available on this sample -- see the warnings above.")
    else:
        add("  Spearman rank correlation against current_ai_stage,")
        add("  p from a permutation test (shuffled outcome, "
            f"{PERMUTATION_TRIALS} trials).")
        add("")
        add(f"{'Factor':<38}{'r':>8}{'p':>8}{'n':>5}")
        for influence in report.by_outcome():
            add(
                f"{influence.name[:37]:<38}"
                f"{_show(influence.outcome_r):>8}"
                f"{_show(influence.outcome_p, 3):>8}"
                f"{influence.outcome_n:>5}"
            )
    add("")

    add("ASSOCIATION WITH THE REST OF THE PROFILE")
    add("-" * 74)
    add("  Pearson correlation between each factor and the mean of the other")
    add("  six. The factor is excluded from the total it is compared against,")
    add("  so this is not circular.")
    add("")
    add(f"{'Factor':<38}{'r':>8}{'p':>8}")
    for influence in report.by_rest():
        add(
            f"{influence.name[:37]:<38}"
            f"{_show(influence.rest_r):>8}"
            f"{_show(influence.rest_p, 3):>8}"
        )
    add("")

    add("INTERNAL COHERENCE OF EACH FACTOR")
    add("-" * 74)
    add("  Cronbach's alpha over the factor's own items, after reverse-coding.")
    add("  Descriptive only at this sample size, and shorter factors are")
    add("  penalised by the formula.")
    add("")
    add(f"{'Factor':<38}{'items':>7}{'alpha':>8}{'n':>5}")
    for influence in report.factors:
        add(
            f"{influence.name[:37]:<38}"
            f"{len(influence.item_totals):>7}"
            f"{_show(influence.alpha):>8}"
            f"{influence.alpha_n:>5}"
        )
    if report.polarity_flags:
        add("")
        add("  Items moving against their own factor:")
        for factor_id, items in report.polarity_flags.items():
            name = cfg.FACTORS_BY_ID[factor_id].name
            add(f"    {name}: {', '.join(items)}")
    add("")

    add("HOW MUCH THE WEIGHTING CHANGES THE ANSWER")
    add("-" * 74)
    if not report.scenarios:
        add("  Not run.")
    else:
        add("  Each row re-scores every company with one factor's weight")
        add("  doubled, against the equal-weight baseline.")
        add("")
        add(f"{'Scenario':<44}{'mean shift':>12}{'tiers':>8}{'rank r':>9}")
        for scenario in sorted(report.scenarios,
                               key=lambda s: s.mean_absolute_shift, reverse=True):
            add(
                f"{scenario.label[:43]:<44}"
                f"{scenario.mean_absolute_shift:>12.2f}"
                f"{scenario.tier_changes:>8}"
                f"{_show(scenario.rank_agreement):>9}"
            )
        add("")
        add("  mean shift = average change in overall score, in points")
        add("  tiers      = companies that moved readiness band")
        add("  rank r     = agreement with the baseline ranking (1.00 = unchanged)")
    add("")

    add("WHERE THE MEASURES AGREE")
    add("-" * 74)
    agreed = report.agreed_leaders()
    if agreed:
        add("  These factors appear in the top three of more than one measure:")
        for factor_id in agreed:
            add(f"    * {cfg.FACTORS_BY_ID[factor_id].name}")
        add("")
        add("  Agreement across measures is the only basis on which this")
        add("  analysis supports calling a factor influential. It remains an")
        add("  association on one small sample, not a demonstrated cause.")
    else:
        add("  No factor reaches the top three on more than one measure.")
        add("  On this sample the measures disagree, which is itself the")
        add("  finding: there is no evidence here for re-weighting.")
    add("")

    return "\n".join(out)
