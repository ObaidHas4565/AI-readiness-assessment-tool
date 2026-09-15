# AI Adoption Readiness Assessment Tool

MSc Data Science Thesis Project

A tool that assesses a company's readiness for AI adoption across several
readiness factors, assigns a readiness tier, identifies strengths and barriers,
and generates prioritised recommendations for the weaker areas.

This repository currently contains **steps 1–5** of the build: the scoring
configuration and input schema, the scoring engine, the recommendation engine,
and rule-based synthetic data generation for testing. The export service and
Streamlit dashboard are added in later steps.

---

## What is implemented

| Component | File | Status |
|---|---|---|
| `ScoreConfiguration` | `src/score_configuration.py` | Done |
| `CompanyProfile` (+ validation) | `src/company_profile.py` | Done |
| `AssessmentResults` | `src/assessment_results.py` | Done |
| `ScoringEngine` | `src/scoring_engine.py` | Done |
| `RecommendationEngine` | `src/recommendation_engine.py` | Done |
| Synthetic data (fake data) | `src/synthetic_data.py` | Done |
| Survey, questionnare and datasets (SDV) | — | Needs real survey export |
| `ExportService` (PDF/Excel) | — | Later |
| `AssessmentDashboard` (Streamlit) | — | Later |

The module names map deliberately onto the classes in the Class Diagram in
Chapter 4, so the code and the documented design can be read side by side.

---

## Scoring method

1. **Reverse-code** the six reverse-worded items (`BUD_2`, `WRK_3`, `LDR_1`,
   `DAT_5`, `TEC_5`, `GOV_5`) as `6 − raw`, so that 5 always means "more ready".
2. **Average** the re-coded items within each factor → a 1–5 factor mean.
3. **Normalise** each factor mean to 0–100 via `(mean − 1) / 4 × 100`.
4. **Combine** the factor scores using the weights in `ScoreConfiguration` to
   produce the overall readiness score.
5. **Assign a tier** from the score bands.
6. **Select** strengths, factor-level barriers, and item-level (subfactor) gaps.

Anchor points on the 0–100 scale: all-Disagree = 25, all-Neutral = 50,
all-Agree = 75.

**Readiness tiers:** Emerging (0–40), Developing (40–70), Advanced (70–100).

### Two decisions worth knowing about

**Weights are currently equal (1/7 each).** This is a deliberate starting
position, not a finding — Objective 4 is to *determine* which areas matter most,
so hard-coding uneven weights before the analysis would assume the answer. The
`current_ai_stage` field gives an ordinal outcome variable to derive empirical
weights against once *n* is large enough. Only the `weight=` values in
`score_configuration.py` need to change.

**`WRK_3` is treated as reverse-worded.** "We have identified specific skill
gaps that block AI adoption" is ambiguous: it could mean diagnostic
self-awareness (positive) or a report of a blocking gap (negative). It is
currently read as negative, consistent with the other barrier-worded items.
Flip `reverse` on that one line to switch readings — see `W3_NOTE` in
`score_configuration.py`.

---

## Project structure

```
ai_readiness_tool/
├── README.md
├── requirements.txt
├── .gitignore
├── conftest.py                    # lets pytest resolve the src package
├── run_example.py                 # worked example — run this first
├── generate_synthetic_data.py     # synthetic dataset + engine report
├── data/                          # generated + real data (never committed)
├── src/
│   ├── __init__.py
│   ├── score_configuration.py     # factors, items, weights, thresholds
│   ├── company_profile.py         # input schema + validation
│   ├── assessment_results.py      # output objects
│   ├── scoring_engine.py          # weighted scoring
│   ├── recommendation_engine.py   # gap → action rules
│   └── synthetic_data.py          # rule-based synthetic data generator 
└── tests/
    ├── test_scoring.py            # 37 tests
    └── test_synthetic_data.py     # 19 tests
```

---

## Running it in Visual Studio Code

### 1. Open the project

Open VS Code → **File → Open Folder…** → select the `ai_readiness_tool` folder.
Install the **Python** extension (by Microsoft) if you do not already have it.

### 2. Create a virtual environment

Open the integrated terminal (`` Ctrl+` `` on Windows/Linux, `` Cmd+` `` on Mac):

**Windows**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

VS Code will usually prompt "We noticed a new virtual environment" — click
**Yes** to select it. If it does not, press `Ctrl+Shift+P` → **Python: Select
Interpreter** → choose the one inside `.venv`.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Steps 1–5 use only the Python standard library, so this installs just `pytest`.

### 4. Run the worked example

```bash
python run_example.py
```

This scores three fictional companies and prints their full readiness profiles.
You should see one Emerging (21.4), one Developing (57.1) and one Advanced
(82.1).

### 5. Run the tests

```bash
pytest -v
```

All 56 tests should pass. Run this after any change to the scoring logic or the
configuration — it is much cheaper than checking output by hand.

### 6. Generate synthetic test data

```bash
python generate_synthetic_data.py
```

Writes three files — the coded CSV the tool reads, a readable copy with full
question text for opening in Excel, and a data dictionary — then scores all 300
companies and prints a report.

---

## Synthetic data

`src/synthetic_data.py` is a fake dataset.

**Rule-based (implemented)** invents companies from archetypes the researcher
defines. It needs no real data and exists to exercise the scoring engine across
many scenarios. It can show the tool *behaves* correctly. It cannot show the
scoring reflects real companies, because every pattern in it was assumed rather
than observed.


Eight profiles are defined — struggling micro-business, funded but
unprepared, tech-savvy small firm, traditional established firm, balanced
developing, leadership-led but capability-lagging, governance-first, and
advanced adopter — each with an intended readiness level per factor, plus
per-company and per-item noise so no two generated firms are alike.

Two properties are deliberate and worth knowing:

**Reverse items are inverted in the output.** A generated company that is
*strong* on data answers "poor data quality is our barrier" with a *low* value,
exactly as a real respondent would. The CSV is therefore raw survey data and
goes through the same reverse-coding path as genuine responses.

**`current_ai_stage` is correlated with overall readiness.** This gives the
dataset an ordinal outcome variable, so the empirical weight-derivation method
can be exercised before real data arrives. On synthetic data this only
reproduces the relationship the generator was told to create — it is a
demonstration of method, never a finding.

### Understanding the columns

The dataset uses short codes (`BUD_1`, `WRK_3`, ...) because they are stable
identifiers that the code, the tests and the write-up can all refer to
unambiguously. They are not readable on their own, so two companion files are
generated alongside:

| File | Purpose |
|---|---|
| `data/synthetic_companies.csv` | What the tool reads. Coded columns, numeric answers. |
| `data/synthetic_companies_readable.csv` | For opening in Excel. Full question text as headers, `4 - Agree` instead of `4`, reverse items marked, employee bands written as `10 to 49 employees`. |
| `data/DATA_DICTIONARY.md` | Column reference: every code, its question, its factor, and whether it is reverse-worded. Worth putting in the appendix. |

### Why the readable copy says "10 to 49 employees"

Excel silently converts `1-9` to `01-Sep` and `10-49` to `Oct-49` when a CSV is
opened by double-clicking, because it reads them as day-month and month-year.
The file on disk is unaffected, but the spreadsheet is wrong on screen — and
permanently wrong if saved from Excel. Since the readable copy exists
specifically to be opened in Excel, its employee bands are written in a form
Excel cannot misread. A test enforces this.

The coded CSV keeps the survey's exact values (`10-49`), because that is what
the tool validates against. Open that one via **Data → Get Data → From
Text/CSV** if you need to inspect it in Excel, which lets you set the column
type to Text and skips the conversion.

### Testing against messy data

The clean dataset alone gives false confidence — the tool looks robust only
because nothing malformed was ever sent to it. `generate_invalid_rows()`
produces the defects a real export actually contains (skipped questions, blank
cells, out-of-range values, a 0–4 scale, un-recoded text answers, unrecognised
categories) and the test suite asserts each is rejected with a message naming
the offending field.

The CSV is **not committed to the repository**. It is exactly reproducible from
the seed, so the generator plus its seed is the artefact worth version
controlling, and keeping `data/` excluded removes any risk of real survey
responses being pushed by accident. Regenerate with the command above.

---

## Using the engines in code

```python
from src.company_profile import CompanyProfile
from src.scoring_engine import ScoringEngine
from src.recommendation_engine import RecommendationEngine

profile = CompanyProfile.from_dict({
    "industry_sector": "Retail",
    "employee_band": "10-49",
    "years_in_operation": "2-5 years",
    "region": "UAE",
    "current_ai_stage": "Exploring",
    "BUD_1": 2, "BUD_2": 4, "BUD_3": 2, "BUD_4": 4,
    # ... all 32 item ids
})

errors = profile.validate()          # [] means valid
if not errors:
    results = ScoringEngine().score(profile)
    RecommendationEngine().recommend(results)

    print(results.overall_score)     # e.g. 43.8
    print(results.readiness_tier)    # e.g. "Developing"
    for rec in results.recommendations:
        print(rec.title, "-", rec.action)
```

`results.to_dict()` returns a flat serialisable view — this is what the export
service will build the PDF and Excel output from.

---

## Publishing to a new, empty GitHub repository

Do this once, then use the "Saving changes" section below for all later work.

### 1. Create the empty repository on GitHub

On [github.com](https://github.com), click **+ → New repository**. Give it a
name (for example `ai-readiness-assessment-tool`), choose **Private** while the
dissertation is in progress, and — importantly — **do not** tick "Add a README",
"Add .gitignore" or "Choose a license". The repository must be completely empty,
otherwise the first push will be rejected.

Copy the HTTPS URL it shows you, which looks like:
`https://github.com/your-username/ai-readiness-assessment-tool.git`

### 2. Set your identity (first time on this machine only)

```bash
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"
```

### 3. Initialise and push

Run these from inside the `ai_readiness_tool` folder, in the VS Code terminal:

```bash
git init
git add .
git commit -m "Add scoring configuration, scoring engine and recommendation engine"
git branch -M main
git remote add origin https://github.com/your-username/ai-readiness-assessment-tool.git
git push -u origin main
```

If you are asked for a password, GitHub no longer accepts your account password
from the terminal. Either sign in through the browser popup VS Code offers, or
create a **Personal Access Token** (GitHub → Settings → Developer settings →
Personal access tokens → Tokens (classic) → Generate new token, with the `repo`
scope) and paste that token as the password.

### 4. Confirm

Refresh the repository page on GitHub — your files should be there.

---

## Saving changes as you develop

Every time you finish a piece of work:

```bash
git add .
git commit -m "Describe what changed"
git push
```

After the first `push -u origin main`, plain `git push` is enough.

You can also do this without the terminal: open the **Source Control** panel in
VS Code (`Ctrl+Shift+G`), type a message in the box, click **Commit**, then
click **Sync Changes**.

### Useful commands

```bash
git status                 # what has changed
git log --oneline          # commit history
git diff                   # exact lines changed since the last commit
git pull                   # bring down changes made elsewhere
```

### Commit message suggestions

Write what changed and why, in the present tense:

- `Add recommendation rules for governance factor`
- `Fix reverse coding on WRK_3`
- `Adjust readiness band boundaries after supervisor feedback`
- `Add SDV synthetic data generation script`

Committing after each meaningful change gives you a history you can point at in
Chapter 5, and a working state to fall back on if something breaks.

---

## Important: keep survey data out of the repository

`.gitignore` already excludes `data/raw/`, `*.csv`, `*.xlsx` and `*.db`, so real
survey responses are not committed by accident. Keep it that way — the survey
was approved as anonymous, and pushing raw response files to a hosted repository
would be an avoidable disclosure risk even with a private repository.

If you need the data on more than one machine, keep it in university storage
rather than in Git.

---

## Next steps
5. `ExportService` for PDF and Excel download.
6. `AssessmentDashboard` in Streamlit, and public deployment.

## Open findings from synthetic testing

Running 300 generated companies surfaced one design issue worth a decision:
**87% of companies hit the 8-recommendation cap**, averaging 7.4 each. For a
mid-scoring firm that is a long list, and the prioritisation ordering is doing
all the work of deciding what matters. Consider lowering
`MAX_RECOMMENDATIONS`, or tightening `REFINE_BELOW`, so the output reads as a
focused action list rather than an audit. Both are one-line changes in
configuration.
