"""
Generate a synthetic test dataset and run it through the assessment tool.

    python generate_synthetic_data.py                 # 300 rows, seed 42
    python generate_synthetic_data.py --n 500         # different size
    python generate_synthetic_data.py --seed 7        # different draw
    python generate_synthetic_data.py --out data/synthetic_companies.csv

Writes a CSV in the tool's schema, then scores every row and reports what the
engine produced. The report is the actual point of the exercise: it shows
whether the scoring logic behaves sensibly across many varied companies, not
just the handful of hand-written cases in the test suite.

"""

from __future__ import annotations

import argparse
import os
from typing import Dict, List, Sequence

from src import score_configuration as cfg
from src.recommendation_engine import RecommendationEngine
from src.scoring_engine import ScoringEngine
from src.synthetic_data import (
    READINESS_PROFILES,
    generate_dataset,
    load_profiles_from_csv,
    write_csv,
    write_data_dictionary,
    write_readable_csv,
)


# ---------------------------------------------------------------------------
# Small statistics helpers (kept dependency-free, consistent with the rest
# of the codebase -- swap for pandas/scipy if those are added later)
# ---------------------------------------------------------------------------

def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return (sum((v - mu) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def _ranks(values: Sequence[float]) -> List[float]:
    """Fractional ranks, with ties averaged (needed for Spearman)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        average_rank = (position + end) / 2 + 1
        for index in range(position, end + 1):
            ranks[order[index]] = average_rank
        position = end + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """
    Spearman rank correlation.

    Rank-based rather than Pearson because `current_ai_stage` is ordinal, not
    interval -- the gap between "Piloting" and "Actively Using" is not a
    measurable quantity, so ranks are the defensible choice.
    """
    if len(x) < 3:
        return 0.0
    rx, ry = _ranks(x), _ranks(y)
    mx, my = mean(rx), mean(ry)
    numerator = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denominator = (
        sum((a - mx) ** 2 for a in rx) ** 0.5 * sum((b - my) ** 2 for b in ry) ** 0.5
    )
    return numerator / denominator if denominator else 0.0


def bar(value: float, scale: float = 100.0, width: int = 24) -> str:
    filled = int(round((value / scale) * width)) if scale else 0
    return "#" * max(0, min(width, filled))


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=300, help="number of companies")
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    parser.add_argument(
        "--out",
        default=os.path.join("data", "synthetic_companies.csv"),
        help="output CSV path",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    # --- generate + write ---------------------------------------------------
    rows = generate_dataset(n=args.n, seed=args.seed)
    written = write_csv(rows, args.out)
    print(f"Wrote {written} synthetic companies to {args.out} (seed={args.seed})")

    # Companion artefacts. The coded CSV above is what the tool reads; these two
    # exist so a person can actually understand it. The column codes (BUD_1,
    # WRK_3, ...) are stable identifiers for the code and the write-up to refer
    # to, but they are meaningless on their own without the dictionary.
    stem = os.path.splitext(args.out)[0]
    readable_path = f"{stem}_readable.csv"
    dictionary_path = os.path.join(os.path.dirname(args.out) or ".", "DATA_DICTIONARY.md")

    write_readable_csv(rows, readable_path)
    write_data_dictionary(dictionary_path)
    print(f"Wrote readable copy (full question text)  -> {readable_path}")
    print(f"Wrote column reference                    -> {dictionary_path}\n")

    # --- reload from disk ---------------------------------------------------
    # Deliberately reloading rather than scoring the in-memory rows: this
    # exercises the same CSV -> validation -> scoring path that real survey
    # data will follow, so a schema mismatch surfaces here rather than later.
    profiles = load_profiles_from_csv(args.out)

    invalid = [(cid, p.validate()) for cid, p in profiles if not p.is_valid()]
    if invalid:
        print(f"VALIDATION FAILED for {len(invalid)} row(s):")
        for cid, errors in invalid[:5]:
            print(f"  {cid}: {errors[0]}")
        return
    print(f"All {len(profiles)} rows passed validation.\n")

    # --- score --------------------------------------------------------------
    scoring_engine = ScoringEngine()
    recommendation_engine = RecommendationEngine()

    results = []
    for _, profile in profiles:
        result = scoring_engine.score(profile)
        recommendation_engine.recommend(result)
        results.append(result)

    profile_by_id = {row["company_id"]: row["profile"] for row in rows}

    # --- overall ------------------------------------------------------------
    overall = [r.overall_score for r in results]
    print("=" * 74)
    print("OVERALL READINESS")
    print("=" * 74)
    print(f"  mean {mean(overall):5.1f}   sd {stdev(overall):5.1f}   "
          f"min {min(overall):5.1f}   max {max(overall):5.1f}\n")

    print("  Tier distribution")
    for band in cfg.READINESS_BANDS:
        count = sum(1 for r in results if r.readiness_tier == band.label)
        share = count / len(results) * 100
        print(f"    {band.label:<11} {count:4d}  ({share:4.1f}%)  {bar(share)}")
    print()

    # --- per factor ---------------------------------------------------------
    print("=" * 74)
    print("FACTOR SCORES")
    print("=" * 74)
    print(f"  {'factor':<42} {'mean':>6} {'sd':>6} {'min':>6} {'max':>6}")
    print("  " + "-" * 70)
    for factor in cfg.FACTORS:
        scores = [r.factor(factor.id).score for r in results]
        print(f"  {factor.name:<42} {mean(scores):6.1f} {stdev(scores):6.1f} "
              f"{min(scores):6.1f} {max(scores):6.1f}")
    print()

    # --- readiness profile recovery -------------------------------------------------
    # Checks that companies built to be weak actually score weak. If an
    # readiness profile's mean lands in the wrong region, either the generator or the
    # scoring logic is wrong -- this is the main sanity check of the run.
    print("=" * 74)
    print("READINESS PROFILE -> SCORE (does the engine recover the intended pattern?)")
    print("=" * 74)
    for profile in sorted(READINESS_PROFILES, key=lambda p: p.name):
        subset = [
            r for r, (cid, _) in zip(results, profiles)
            if profile_by_id.get(cid) == profile.name
        ]
        if not subset:
            continue
        scores = [r.overall_score for r in subset]
        tiers = [r.readiness_tier for r in subset]
        dominant = max(set(tiers), key=tiers.count)
        print(f"  {profile.name:<38} n={len(subset):3d}  "
              f"mean {mean(scores):5.1f}  mostly {dominant}")
    print()

    # --- strengths / barriers -----------------------------------------------
    print("=" * 74)
    print("MOST FREQUENTLY IDENTIFIED BARRIERS AND STRENGTHS")
    print("=" * 74)
    barrier_counts: Dict[str, int] = {}
    strength_counts: Dict[str, int] = {}
    for result in results:
        for factor_score in result.barriers:
            barrier_counts[factor_score.name] = barrier_counts.get(factor_score.name, 0) + 1
        for factor_score in result.strengths:
            strength_counts[factor_score.name] = strength_counts.get(factor_score.name, 0) + 1

    print("  Barriers")
    for name, count in sorted(barrier_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {name:<42} {count:4d}  {bar(count / len(results) * 100)}")
    print("\n  Strengths")
    for name, count in sorted(strength_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {name:<42} {count:4d}  {bar(count / len(results) * 100)}")
    print()

    # --- recommendation coverage --------------------------------------------
    rec_counts = [len(r.recommendations) for r in results]
    no_recs = sum(1 for c in rec_counts if c == 0)
    print("=" * 74)
    print("RECOMMENDATION COVERAGE")
    print("=" * 74)
    print(f"  mean recommendations per company : {mean(rec_counts):.1f}")
    print(f"  companies receiving none         : {no_recs} "
          f"({no_recs / len(results) * 100:.1f}%)")
    print(f"  capped at MAX_RECOMMENDATIONS    : "
          f"{sum(1 for c in rec_counts if c == cfg.MAX_RECOMMENDATIONS)}\n")

    # --- empirical weighting demonstration ----------------------------------
    print("=" * 74)
    print("FACTOR CORRELATION WITH CURRENT AI ADOPTION STAGE (Spearman)")
    print("=" * 74)
    print("  This is the method that would derive empirical factor weights from")
    print("  real survey data. On synthetic data it only reproduces the")
    print("  relationships the generator was told to create -- it is a")
    print("  demonstration of the method, not a finding.\n")

    stage_index = {stage: i for i, stage in enumerate(cfg.AI_ADOPTION_STAGES)}
    stages = [stage_index[r.context["current_ai_stage"]] for r in results]

    correlations = []
    for factor in cfg.FACTORS:
        scores = [r.factor(factor.id).score for r in results]
        correlations.append((factor.name, spearman(scores, stages)))

    for name, rho in sorted(correlations, key=lambda kv: -kv[1]):
        print(f"    {name:<42} rho = {rho:+.3f}  {bar(abs(rho), scale=1.0)}")

    total = sum(max(0.0, rho) for _, rho in correlations)
    if total > 0:
        print("\n  Implied weights if derived proportionally from these correlations:")
        for name, rho in sorted(correlations, key=lambda kv: -kv[1]):
            implied = max(0.0, rho) / total
            print(f"    {name:<42} {implied:.3f}   (currently {1/7:.3f})")
    print()


if __name__ == "__main__":
    main()