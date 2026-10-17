# AI Adoption Readiness Assessment Tool

A tool that assesses a company's readiness for AI adoption across seven
readiness factors, assigns a readiness tier, identifies strengths and barriers,
and generates prioritised recommendations for the weaker areas.

All seven build steps are in place: the scoring configuration and input
schema, the scoring engine, the recommendation engine, synthetic data
generation for testing, the PDF/Excel export service, and the Streamlit
dashboard.

## Files
 • src/score_configuration.py - stores the fixed constants the scoring engine relies (factors, weigths, questions, items, thresholds)
    • src/company_profile.py - holds user inputs and checks their validation
     • src/scoring_engine.py - weighted scoring of factor scores, overall score, readiness tier, strengths, barriers and gaps.
      • src/recommendation_engine.py - converts answers into recommended actions based on severity and ranking of the results.
       • src/assessment_results.py - displays the user's results, recommendations and export files.
        • app.py - the streamlit application
