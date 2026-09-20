#!/usr/bin/env python3
"""
Run the factor influence analysis over a survey export.

    python analyse_influence.py responses.csv
    python analyse_influence.py responses.xlsx --out influence_report.txt

With no file given it runs on the synthetic dataset in data/, which is useful
for checking the analysis works but says nothing about real companies -- the
synthetic responses were generated from the tool's own assumptions, so any
pattern found in them is a pattern that was put there.

This script only reads. It does not change the questionnaire, the weights or
any score.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.company_profile import ValidationError
from src.influence_analysis import analyse, format_report
from src.scoring_engine import ScoringEngine
from src.survey_import import import_survey, profiles_from_report

DEFAULT_DATA = Path("data/synthetic_companies.csv")


def load_profiles(path: Path):
    """Read a survey export and return (identifier, CompanyProfile) pairs."""
    report = import_survey(path.read_bytes(), path.name)
    if report.error:
        raise SystemExit(f"Could not read {path}: {report.error}")
    pairs = profiles_from_report(report)
    if not pairs:
        raise SystemExit(f"No rows found in {path}.")
    return report, pairs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=str(DEFAULT_DATA),
                        help="survey export (.csv or .xlsx)")
    parser.add_argument("--out", help="also write the report to this file")
    parser.add_argument("--trials", type=int, default=2000,
                        help="permutation trials (default 2000)")
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"{path} does not exist.")

    if path.resolve() == DEFAULT_DATA.resolve():
        print("NOTE: running on the synthetic dataset. Findings from synthetic")
        print("      data describe the generator, not real companies.\n")

    report, pairs = load_profiles(path)

    engine = ScoringEngine()
    scored = []
    skipped = 0
    for _, profile in pairs:
        try:
            scored.append(engine.score(profile, validate=False, allow_partial=True))
        except ValidationError:
            skipped += 1

    if not scored:
        raise SystemExit("Nothing could be scored from this file.")
    if skipped:
        print(f"{skipped} row(s) had no scoreable answers and were left out.\n")

    text = format_report(analyse(scored, trials=args.trials))
    print(text)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"\nWritten to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
