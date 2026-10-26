# AI Adoption Readiness Assessment Tool

A tool that assesses a company's readiness for AI adoption across seven readiness factors (workforce, leadership, data, budget, technology, organizational culture, and governance). A user answers a short questionnaire and gets a readiness score, assigns a readiness level, identifies strengths and barriers,
and a list of prioritised recommendations for the weaker areas. 

## Why I build this tool

This is my MSc Data Science dissertation project at Middlesex University Dubai (2026). It is aimed to assist companies, especially small-to-medium-sized enterprises (SMEs), in identifying their readiness level for AI adoption. This is a prototype. The scoring logic is covered by 227 tests, and the limitations are listed near the end of this page.

## What it does
- Scores a company across 7 readiness factors: Budget, Workforce & Skills, Leadership, Data, Technology, Organizational Culture, and Governance.
- Places a company in one of the 3 readiness levels based on the overall score: Emerging, Developing, and Advanced
- List strengths, barriers, and specific questions where the company scored the lowest.
- Provides recommended actions for each weak area, ordered by how much improving them will improve the overall score.
- Accepts an uploaded CSV or Excel dataset and shows the results for the whole group, including a breakdown by sector and country.
- Exports both results as either Excel or PDF file.

#### Try the live demo: https://ai-readiness-assessment-tool-mnjgtm5zzkf4rdvnoevjfo.streamlit.app/
(The app run on Streamlit's free hosting, so it may take a short while to start if nobody has used it recently.)

## How scoring works
The questionnaire has 32 questions across 7 factors answered on a 5-point agreement scale, 5 company details (sector, country, years in operation, size, and current AI stage), and 3 optional written questions.

1. 5 statements are worded negatively, so agreeing means the company is less ready. The answers are flipped, using 6 minus the answers, so a 5 becomes a 1.
2. Answers are averaged within each factor, then converted to a 0 to 100 score.
3. The 7 factor scores are combined using the factor weights.
4. The overall score gives the readiness level: Emerging (below 40), Developing (40 to 70) or Advanced (70 and above).
5. A factor at 70 or above counts as strength. A factor below 50 counts as a barrier.

### Recommendations

Recommendations are based on barriers and gaps, not on the raw answers. Each weak factor gets an advice at one of the 3 severity levels:

- Critical: below 35
- Moderate: 35 to below 50
- Refine: 50 to below 70

Factors scoring 70 or above get no recommendation. Individual questions also have their own advice. The written answers can change which recommendations appear, but they do not change the score.

If an uploaded dataset covers only some of the 7 factors, the tool lists the missing ones and scores the rest.

## Project Structure
- `app.py` - the streamlit application
- `src/score_configuration.py` - stores the fixed constants the scoring engine uses.
- `src/company_profile.py` - holds user inputs and checks their validation.
- `src/scoring_engine.py` - weighted scoring of factor scores, overall score, readiness tier, strengths, barriers and gaps.
- `src/recommendation_engine.py` - converts barriers and gaps into recommended actions based on severity and ranking of results.
- `src/assessment_results.py` - displays the user's results, recommendations and export files.
- `src/text_analysis.py` - matches written answers to factors and ignores non-answers.
- `src/survey_import.py` - reads uploaded datasets and  matches columns to questions.
- `src/open_value_checks.py`  - checks the sector and country answers
- `src/export_service.py` - creates the downloadable PDF and Excel files. 
- `src/synthetic_data.py`, generate_synthetic_data.py - generates a synthetic dataset for testing the tool's performance.
- `requirements.txt` - installing the required libraries.
- `src/__init__.py` - Makes src a package and exposes the main classes, so that they can imported from src directly.
- `run_example.py` - Scores 3 company profile examples from the command line.
- `conftest.py` - an empty file that tells pytest where the project root is, so the tests can be imported from src.
- `tests/test_export_and_app.py` - 37 tests for PDF and Excel contents and charts, dataset reports, and the dashboard.
- `tests/test_scoring.py` - 37 tests for configuration, scoring, levels, strengths, barriers, validation and recommendations.
- `tests/test_survey_import.py` - 92 tests for CSV and Excel uploads, answer formats, sector and country checks, and partial scoring.
- `tests/test_synthetic_data.py` - 19 tests for data generator and rejection of broken rows.
- `tests/test_text_analysis.py` - 42 tests for written answers, non-answer filtering, and factor matching.

## Running Locally

You need Python and Git. From the project folder:
```bash
python -m venv .venv

# Windows/Git Bash
source .venv/Scripts/activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python generate_synthetic_data.py #optional: creates the synthetic dataset for testing
pytest -v # optional: checks everything works before you start the app.
streamlit run app.py
```


The main libraries are Streamlit, ReportLab (PDF), openpyxl (Excel) and pytest.

## Data
The `data/` folder holds the `DATA_DICTIONARY.md`, which describes the columns in the synthetic dataset. The synthetic dataset is not stored in the repository. Generate it locally with 'python generate_synthetic_data,py'.

The synthetic dataset exists to test the tool. It should not be read as evidence about real companies.

## Privacy
The tool does not ask for any sensitive information like a company's name or contact details and has no database. Results are kept in the browser session and disappear when the tab is closed or refreshed. PDF and Excel files are generated automatically from the results and are not saved on the server.

## Basis for the factors and thresholds

The 7 factors come from research articles of AI readiness and maturity models, especially TOE, MRADA, AIMAA. The thresholds (40 and 70 for readiness levels, and 35 to 50 for barriers and severity) are based on assumption for this prototype. They are not taken from a published framework.

## Limitations
- All factors are weighted equally (1/7 each). This is a starting assumption, not as a finding.
- The tool was tested with a small survey dataset of 17 responses, so its results may not be accurate.
- The tool does not identify which factor or factors have the greatest influence on AI adoption.
- The tool only covers 7 factors and does not account for other factors.
- Recommendations are general and are not tailored to a specific company.
