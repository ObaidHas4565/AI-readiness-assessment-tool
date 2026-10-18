# AI Adoption Readiness Assessment Tool

A tool that assesses a company's readiness for AI adoption across seven
readiness factors, assigns a readiness tier, identifies strengths and barriers,
and generates prioritised recommendations for the weaker areas.

All seven build steps are in place: the scoring configuration and input
schema, the scoring engine, the recommendation engine, synthetic data
generation for testing, the PDF/Excel export service, and the Streamlit
dashboard.

Live version: https://ai-readiness-assessment-tool-mnjgtm5zzkf4rdvnoevjfo.streamlit.app/

## Project Structure
- app.py - the streamlit application
- src/score_configuration.py - stores the fixed constants the scoring engine uses.
- src/company_profile.py - holds user inputs and checks their validation.
- src/scoring_engine.py - weighted scoring of factor scores, overall score, readiness tier, strengths, barriers and gaps.
- src/recommendation_engine.py - converts barriers and gaps into recommended actions based on severity and ranking of results.
- src/assessment_results.py - displays the user's results, recommendations and export files.
- src/text_analysis.py - matches written answers to factors and ignores non-answers.
- src/survey_import.py - reads uploaded datasets and  matches columns to questions.
- src/open_value_checks.py  - checks the sector and country answers
- src/export_service.py - creates the downloadable PDF and Excel files. 
- src/synthetic_data.py, generate_synthetic_data.py - generates a synthetic dataset for testing the tool's performance.
- requirements.txt - installing the required libraries.
- src/__init__.py - Makes src a package and exposes the main classes, so that they can imported from src directly.
- run_example.py - Scores 3 company profile examples from the command line.
- conftest.py - an empty file that tells pytest where the project root is, so the tests can be imported from src.
- tests/test_export_and_app.py - 37 tests for PDF and Excel contents and charts, dataset reports, and the dashboard.
- tests/test_scoring.py - 37 tests for configuration, scoring, levels, strengths, barriers, validation and recommendations.
- tests/test_survey_import.py - 92 tests for CSV and Excel uploads, answer formats, sector and country checks, and partial scoring.
- tests/test_synthetic_data.py - 19 tests for data generator and rejection of broken rows.
- tests/test_text_analysis.py - 42 tests for written answers, non-answer filtering, and factor matching.
- data/ - survey responses, synthetic dataset, and DATA_DICTIONARY.MD (explaination of each column in the synthetic dataset)

