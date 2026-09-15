"""
Worked example -- run this to see steps 1-3 working end to end.

    python run_example.py

Three fictional companies are scored to show the engine behaving differently
across scenarios: one weak almost everywhere, one with an uneven profile
(well funded but with poor data and governance), and one broadly ready.

"""

from src import score_configuration as cfg
from src.company_profile import CompanyProfile
from src.recommendation_engine import RecommendationEngine
from src.scoring_engine import ScoringEngine


def build(name: str, context: dict, factor_levels: dict) -> tuple:
    """
    Build a profile by setting every item in a factor to one agreement level.

    `factor_levels` maps factor_id -> the intended readiness level (1-5), and
    reverse-worded items are flipped automatically so the intent is preserved.
    """
    responses = {}
    for factor in cfg.FACTORS:
        level = factor_levels[factor.id]
        for item in factor.items:
            responses[item.id] = (cfg.REVERSE_PIVOT - level) if item.reverse else level
    return name, CompanyProfile.from_dict({**context, **responses})


COMPANIES = [
    build(
        "Company A -- early-stage retailer, little in place",
        {
            "industry_sector": "Retail",
            "employee_band": "1-9",
            "years_in_operation": "Under 2 years",
            "region": "UAE",
            "current_ai_stage": "Not considering",
        },
        {
            "budget": 2, "workforce": 2, "leadership": 2, "data": 1,
            "technology": 2, "culture": 3, "governance": 1,
        },
    ),
    build(
        "Company B -- funded manufacturer, weak on data and governance",
        {
            "industry_sector": "Manufacturing",
            "employee_band": "50-249",
            "years_in_operation": "10+ years",
            "region": "UK",
            "current_ai_stage": "Exploring",
        },
        {
            "budget": 5, "workforce": 3, "leadership": 4, "data": 2,
            "technology": 4, "culture": 3, "governance": 2,
        },
    ),
    build(
        "Company C -- technology firm, broadly ready",
        {
            "industry_sector": "Technology",
            "employee_band": "250+",
            "years_in_operation": "10+ years",
            "region": "USA",
            "current_ai_stage": "Piloting",
        },
        {
            "budget": 4, "workforce": 4, "leadership": 5, "data": 4,
            "technology": 5, "culture": 4, "governance": 4,
        },
    ),
]


def main() -> None:
    scoring_engine = ScoringEngine()
    recommendation_engine = RecommendationEngine()

    for name, profile in COMPANIES:
        errors = profile.validate()
        if errors:
            print(f"{name}: INVALID -> {errors}")
            continue

        results = scoring_engine.score(profile)
        recommendation_engine.recommend(results)

        print("=" * 78)
        print(name)
        print("=" * 78)
        print(f"Overall readiness: {results.overall_score:.1f}/100   "
              f"Tier: {results.readiness_tier}")
        print(f"  {results.tier_description}")
        print()

        print("Factor scores")
        print("-" * 78)
        for factor in results.ordered_factors():
            bar = "#" * int(round(factor.score / 4))
            print(f"  {factor.name:<42} {factor.score:5.1f}  {factor.band_label:<11} {bar}")
        print()

        if results.strengths:
            print("Strengths")
            print("-" * 78)
            for factor in results.strengths:
                print(f"  + {factor.name} ({factor.score:.0f}/100)")
            print()

        if results.barriers:
            print("Main barriers")
            print("-" * 78)
            for factor in results.barriers:
                print(f"  - {factor.name} ({factor.score:.0f}/100)")
            print()

        if results.item_barriers:
            print("Specific gaps (subfactors)")
            print("-" * 78)
            for item in results.item_barriers:
                print(f"  - [{item.item_id}] {item.text}  ({item.score:.0f}/100)")
            print()

        if results.recommendations:
            print("Recommendations, highest priority first")
            print("-" * 78)
            for n, rec in enumerate(results.recommendations, start=1):
                tag = f" (from {rec.triggered_by_item})" if rec.triggered_by_item else ""
                print(f"  {n}. [{rec.severity.upper():<8}] {rec.factor_name}{tag}")
                print(f"     {rec.title}")
                print(f"     {rec.action}")
                print()
        else:
            print("No recommendations -- all factors at or above the Advanced threshold.\n")

        print()


if __name__ == "__main__":
    main()
