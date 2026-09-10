"""
AI Adoption Readiness Assessment Tool -- core package.

Steps 1-3 of the build: configuration/schema, scoring engine, recommendation
engine. The Streamlit dashboard and export service are added later and import
from here.
"""

from .assessment_results import (
    AssessmentResults,
    FactorScore,
    ItemScore,
    Recommendation,
)
from .company_profile import CompanyProfile, ValidationError
from .recommendation_engine import RecommendationEngine
from .scoring_engine import ScoringEngine

__all__ = [
    "AssessmentResults",
    "CompanyProfile",
    "FactorScore",
    "ItemScore",
    "Recommendation",
    "RecommendationEngine",
    "ScoringEngine",
    "ValidationError",
]
