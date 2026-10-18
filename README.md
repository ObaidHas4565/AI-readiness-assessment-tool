# AI Adoption Readiness Assessment Tool

A tool that assesses a company's readiness for AI adoption across seven readiness factors (workforce, leadership, data, budget, technology, organizational culture, and governance). A user answers short questionnaire and gets a readiness score, assigns a readiness level, identifies strengths and barriers,
and a list of prioritised recommendations for the weaker areas. Results can be download as a PDF or Excel file.

## How it works
- Scores a company across 7 readiness factors: Budget, Workforce & Skills, Leadership, Data, Technology, Organizational Culture, and Governance.
- Places a company in one of the 3 readiness levels based on the overall score: Emerging, Developing, and Advanced
- List strengths, barriers, and specific questions where the company scored the lowest.
- Provides recommended actions for each weak area, ordered by how much improving them will improve the overall score
- Accepts an uploaded CSV or Excel dataset and shows the results for the whole group, including a breakdown by sector and country.
- Exports both results as either Excel or PDF file.

#### Live version: https://ai-readiness-assessment-tool-mnjgtm5zzkf4rdvnoevjfo.streamlit.app/

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
- src/_ _init_ _.py - Makes src a package and exposes the main classes, so that they can imported from src directly.
- run_example.py - Scores 3 company profile examples from the command line.
- conftest.py - an empty file that tells pytest where the project root is, so the tests can be imported from src.
- tests/test_export_and_app.py - 37 tests for PDF and Excel contents and charts, dataset reports, and the dashboard.
- tests/test_scoring.py - 37 tests for configuration, scoring, levels, strengths, barriers, validation and recommendations.
- tests/test_survey_import.py - 92 tests for CSV and Excel uploads, answer formats, sector and country checks, and partial scoring.
- tests/test_synthetic_data.py - 19 tests for data generator and rejection of broken rows.
- tests/test_text_analysis.py - 42 tests for written answers, non-answer filtering, and factor matching.
- data/ - survey responses, synthetic dataset, and DATA_DICTIONARY.MD (explaination of each column in the synthetic dataset)

## Limitations
- Factors are equally weighted (1/7 to provide the same amount to the overall score) as a starting assumption, not a finalized result.
- The tool's results may not be accurate as it was tested with a small survey dataset.
- The tool does not determine the factor or factors that have the greatest influence on AI adoption.
- The tool only covers 7 factors, does not include factors it is not familiar with.
- The tool's recommendations may be too generic.
