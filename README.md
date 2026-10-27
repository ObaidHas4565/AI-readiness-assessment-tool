# AI Adoption Readiness Assessment Tool

[Try the live demo](https://ai-readiness-assessment-tool-mnjgtm5zzkf4rdvnoevjfo.streamlit.app/)
(The app runs on Streamlit's free hosting, so it may take a short while to start if nobody has used it recently.) 

A tool that assesses a company's readiness for AI adoption across seven readiness factors (workforce, leadership, data, budget, technology, organizational culture, and governance). A user answers a short questionnaire and gets a readiness score, assigns a readiness level, identifies strengths and barriers,
and a list of prioritised recommendations for the weaker areas. 
<img width="1916" height="807" alt="image" src="https://github.com/user-attachments/assets/0b789e50-481f-4f82-924c-faf5274503e8" />
<img width="1916" height="1250" alt="image" src="https://github.com/user-attachments/assets/0a873942-1549-4726-9f5a-7ea25bfd5966" />


## Why I build this tool

This is my MSc Data Science dissertation project at Middlesex University Dubai (2026). It is aimed to assist companies, especially small-to-medium-sized enterprises (SMEs), in identifying their readiness level for AI adoption. This is a prototype. The scoring logic is covered by 227 tests, and the limitations are listed near the end of this page.

## What it does
- Scores a company across 7 readiness factors: Budget, Workforce & Skills, Leadership, Data, Technology, Organizational Culture, and Governance.
- Places a company in one of the 3 readiness levels based on the overall score: Emerging, Developing, and Advanced
- Lists strengths, barriers, and specific questions where the company scored the lowest.
- Provides recommended actions for each weak area, ordered by how much improving them will improve the overall score.
- Accepts an uploaded CSV or Excel dataset and shows the results for the whole group, including a breakdown by sector and country.
- Exports both results as either Excel or PDF file.

[Try the live demo](https://ai-readiness-assessment-tool-mnjgtm5zzkf4rdvnoevjfo.streamlit.app/)
(The app runs on Streamlit's free hosting, so it may take a short while to start if nobody has used it recently.)

## How scoring works
The questionnaire has 32 questions across 7 factors answered on a 5-point agreement scale, 5 company details (sector, country, years in operation, size, and current AI stage), and 3 optional written questions.

1. 5 statements are worded negatively, so agreeing means the company is less ready. The answers are flipped, using 6 minus the answer, so a 5 becomes a 1.
2. The answers for each factor are averaged and rescaled to a score from 0 to 100.
3. The 7 factor scores are combined using the factor weights.
4. The overall score gives the readiness level: Emerging (below 40), Developing (40 to below 70) or Advanced (70 and above).
5. A factor scoring 70 or above counts as strength. A factor below 50 is a barrier.

### Recommendations

Recommendations are based on barriers and gaps, not on the raw answers. Each weak factor gets advice at one of the 3 severity levels:

- Critical: below 35
- Moderate: 35 to below 50
- Refine: 50 to below 70

Factors scoring 70 or above get no recommendation. Individual questions also have their own advice. The written answers can change which recommendations appear, but they do not change the score.

If an uploaded dataset covers only some of the 7 factors, the tool lists the missing ones and scores the rest.

## How the code is organized

Input → Scoring engine → Recommendation engine → Export

Inputs are checked before scoring, and incomplete or out-of-range entries are rejected. Scoring, recommendations, import, and export are kept in separate modules. The fixed scoring constants (weights and thresholds) live in their own file, so they can be changed without editing the application logic. 

<details>
<summary><strong> Project Structure </strong></summary>
  
- `app.py`: the streamlit application
- `src/score_configuration.py`: stores the fixed constants the scoring engine uses.
- `src/company_profile.py`: holds user inputs and checks their validation.
- `src/scoring_engine.py`: weighted scoring of factor scores, overall score, readiness tier, strengths, barriers and gaps.
- `src/recommendation_engine.py`: converts barriers and gaps into recommended actions based on severity and ranking of results.
- `src/assessment_results.py`: displays the user's results, recommendations and export files.
- `src/text_analysis.py`: matches written answers to factors and ignores non-answers.
- `src/survey_import.py`: reads uploaded datasets and  matches columns to questions.
- `src/open_value_checks.py`: checks the sector and country answers
- `src/export_service.py`: creates the downloadable PDF and Excel files. 
- `src/synthetic_data.py`, `generate_synthetic_data.py`: generates a synthetic dataset for testing the tool's performance.
- `requirements.txt`: installing the required libraries.
- `src/__init__.py`: Makes src a package and exposes the main classes, so that they can imported from src directly.
- `run_example.py`: Scores 3 company profile examples from the command line.
- `conftest.py`: an empty file that tells pytest where the project root is, so the tests can be imported from src.
- `measure_performance.py`: measures the tool's speed performance in generating the results within 10 seconds.
- `tests/test_export_and_app.py`: 37 tests for PDF and Excel contents and charts, dataset reports, and the dashboard.
- `tests/test_scoring.py`: 37 tests for configuration, scoring, levels, strengths, barriers, validation and recommendations.
- `tests/test_survey_import.py`: 92 tests for CSV and Excel uploads, answer formats, sector and country checks, and partial scoring.
- `tests/test_synthetic_data.py`: 19 tests for data generator and rejection of broken rows.
- `tests/test_text_analysis.py`: 42 tests for written answers, non-answer filtering, and factor matching.
  
</details>

## Running Locally

You need Python and Git. From the project folder:
```bash
python -m venv .venv

# Windows/Git Bash
source .venv/Scripts/activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python generate_synthetic_data.py # optional: creates the synthetic dataset for testing
pytest -v # optional: checks everything works before you start the app.
streamlit run app.py
```

The main libraries are Streamlit, ReportLab (PDF), openpyxl (Excel) and pytest.

## Data
The `data/` folder holds the `DATA_DICTIONARY.md`, which describes the columns in the synthetic dataset. The synthetic dataset is not stored in the repository. Generate it locally with 'python generate_synthetic_data.py'.

The synthetic dataset exists to test the tool. It should not be read as evidence about real companies.

## Privacy
The tool does not ask for any sensitive information like a company's name or contact details and has no database. Results are kept in the browser session and disappear when the tab is closed or refreshed. PDF and Excel files are generated automatically from the results and are not saved on the server.

## Basis for the factors and thresholds

The 7 factors come from research articles on AI readiness and maturity models like TOE, MDARA, or AIMAA frameworks. The thresholds (40 and 70 for readiness levels, and 35 and 50 for barriers and severity) are based on my own assumptions for this prototype. They are not taken from a published framework.

## Testing and early results

The tool was tested with 17 survey responses and a synthetic dataset. At this size, the results show that the scoring and recommendation logic behaves as designed. They do not show how accurately the tool predicts real AI adoption outcomes.

The tool was checked against its functional and non-functional requirements. Functional requirements were confirmed by 227 automated tests and by using the tool directly. Performance was measured with a stopwatch and a timing script (measure_performance.py), and the tool displayed the results within 10 seconds. Reliability was checked by running the same inputs from the dataset tab and the assessment form, which gave the same results each time. Availability was confirmed through the public Streamlit link. 

10 people tried the tool and completed a feedback questionnaire. Their responses were positive about ease of use, trust, usefulenss, and overall satisfaction. However, the main concern was the recommendations: 5/10 respondents felt that the suggested actions may be too generic, and a few found them to be unclear or not suited to their company's situation.


## Limitations and next steps
- All factors are weighted equally (1/7 each). This is a starting assumption, not a finding. The next step is to derive the weights from the survey data, for example by relating factor scores to current AI stage once the sample is larger.
- The sample is small (17 responses). More responses would allow the weight and threshold analysis to be repeated with more confidence.
- The tool does not identify which factor or factors have the greatest influence on AI adoption. Adjusting the weights would be the first step toward answering that.
- The thresholds are based on assumption. They could be checked against published data on how companies score in practice, and experts could review them.
- The tool only covers 7 factors. Other frameworks may point to factors that are missing here.
- Recommendations are general and are not tailored to a specific company. Sector-specific advice would be a useful addition.
- The synthetic dataset is for testing performance only. The scoring should be checked against more real responses.
