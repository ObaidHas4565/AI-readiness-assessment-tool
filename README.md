# AI Adoption Readiness Assessment Tool

MSc Data Science dissertation project (CST4090), Middlesex University Dubai.

A tool that assesses a company's readiness for AI adoption across seven
readiness factors, assigns a readiness tier, identifies strengths and barriers,
and generates prioritised recommendations for the weaker areas.

All seven build steps are in place: the scoring configuration and input
schema, the scoring engine, the recommendation engine, synthetic data
generation for testing, the PDF/Excel export service, and the Streamlit
dashboard.

To run the tool:

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## What is implemented

| Component | File | Status |
|---|---|---|
| `ScoreConfiguration` | `src/score_configuration.py` | Done |
| `CompanyProfile` (+ validation) | `src/company_profile.py` | Done |
| `AssessmentResults` | `src/assessment_results.py` | Done |
| `ScoringEngine` | `src/scoring_engine.py` | Done |
| `RecommendationEngine` | `src/recommendation_engine.py` | Done |
| Synthetic data | `src/synthetic_data.py` | Done |
| Survey import (any export format) | `src/survey_import.py` | Done |
| Open-value checks (country/sector) | `src/open_value_checks.py` | Done |
| `ExportService` (PDF/Excel) | `src/export_service.py` | Done |
| `AssessmentDashboard` (Streamlit) | `app.py` | Done |

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
│   ├── synthetic_data.py          # test data generator
│   ├── survey_import.py           # reads real survey exports, matches by meaning
│   ├── open_value_checks.py       # is this a real country / industry?
│   ├── text_analysis.py           # reads the written answers
│   └── export_service.py          # PDF and Excel output
├── app.py                         # Streamlit dashboard
└── tests/
    ├── test_scoring.py            # 37 tests
    ├── test_synthetic_data.py     # 19 tests
    ├── test_export_and_app.py     # 36 tests
    ├── test_text_analysis.py      # 42 tests
    └── test_survey_import.py      # 92 tests
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

The scoring logic itself needs nothing beyond the standard library. This installs what the exports and the dashboard need: `reportlab`, `openpyxl` and `streamlit`, plus `pytest` for the tests.

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

All 226 tests should pass. Run this after any change to the scoring logic or the configuration — it is much cheaper than checking output by hand.

### 6. Generate synthetic test data

```bash
python generate_synthetic_data.py
```

Writes three files — the coded CSV the tool reads, a readable copy with full
question text for opening in Excel, and a data dictionary — then scores all 300
companies and prints a report.

### 7. Run the dashboard

```bash
streamlit run app.py
```

It opens at `http://localhost:8501`. Two tabs:

**Assessment** — the questionnaire as a company would fill it in. Answers go
into the browser session only, nothing is written anywhere. When every question
is answered, it scores, shows the profile, and offers the PDF and Excel
downloads. Submitting an incomplete form lists which sections are still missing
rather than scoring anyway.

**Score a dataset** — upload a survey export (CSV or Excel) and every response
is scored with the same engine. The columns do not have to be named the tool's
way: it works out which column is which from the question wording and reads
word answers like "Agree" as readily as numbers, so a Google Forms export of
this questionnaire works exactly as downloaded. It shows what matched, the
score distribution, tier split, factor averages, a profile radar, and
breakdowns by adoption stage, sector, country, size and age — but only the
breakdowns the file can actually support. Open-ended answers are kept and shown
rather than discarded. This tab is for the evaluation chapter, not for SMEs.

The barrier-worded questions are shown exactly as written, with nothing marking
them out. Telling a respondent which questions are scored backwards would
change how they answer.

---

## Exports

`src/export_service.py` builds both downloads in memory and returns bytes —
nothing is written to the server's disk, which is what keeps the
nothing-is-stored design intact.

**PDF** — headline score and tier, factor bars, the profile-shape radar,
strengths, barriers, specific gaps, the recommendations in priority order, a
question-by-question breakdown of all 32 answers, and whatever was written in
the open questions.

**Excel** — five sheets: `Summary`, `Factor scores`, `Responses` (every
question with both the raw answer and the re-coded one, so the effect of
reverse coding is visible), `Recommendations`, and `Written answers`.
`Factor scores` carries a bar chart and a radar of the profile; `Responses`
carries a chart of all 32 questions, which is where a factor with a decent
average hiding one weak question shows up.

Every chart names its axes and labels its values, and the radar carries the
factor names round its edge. That last part needed work: openpyxl writes a
category range as a *numeric* reference even when the categories are words,
and Excel reads a numeric reference to a column of text as empty — which is
why a chart built the plain way arrives with no labels on it at all. The
categories are rewritten as string references in `_label_chart`.

Score charts are fixed to a 0–100 axis rather than auto-scaled, so a six-point
difference is drawn as six points and not as the whole width of the chart. The
radars hide their value axis, because a radar draws that axis as a column of
numbers straight down the middle of the shape; the rings still carry the scale.

**A note on testing the charts.** The tests read the chart XML as a parsed
tree, never as a string. openpyxl serialises through `lxml` when it is
installed and through the standard library when it is not, and the two write
empty elements differently — `<majorGridlines/>` against `<majorGridlines />`.
The workbooks are identical as far as Excel is concerned; only the bytes
differ. A test that matches the raw text therefore passes on one machine and
fails on the next, which is exactly what happened here before these tests were
rewritten to parse properly.

Neither file contains a company name or any identifying detail, because
`CompanyProfile` never collects any.

From code:

```python
from src.export_service import ExportService
ExportService().write_pdf(results, "report.pdf")
ExportService().write_excel(results, "report.xlsx")
```

---

## Synthetic data — what it can and can't show

`src/synthetic_data.py` makes up fake companies so the scoring engine can be
tested across many scenarios before real survey responses exist. It can show
the tool *behaves* correctly across a wide range of inputs. It cannot show the
scoring reflects real companies, because every pattern in it was assumed rather
than observed — only real responses can support that claim. Once those are
collected they become the main test data, with this kept for edge cases and
validation testing.

Eight readiness profiles are defined — Early_Stage_Adopter, Well_Funded,
Tech_Focused, Traditional_Company, Developing, Leadership_Driven,
Governance_Focused and Advanced_Adopter — each with an intended readiness level
per factor, plus per-company and per-item noise so no two generated firms are
alike.

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
- `Add synthetic data generation script`

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

The build itself is complete. What remains depends on real survey data:

1. Collect the survey responses and run them through the **Score a dataset**
   tab to check the tool behaves sensibly on real answers.
2. Derive **empirical factor weights** from those responses, replacing the
   equal weights currently used. `generate_synthetic_data.py` already prints
   the correlation method that would do this.
3. Resolve the two open decisions below.
4. Deploy the dashboard publicly (Streamlit Community Cloud) if the evaluation
   needs users to reach it.

## Open findings from synthetic testing

Running 300 generated companies surfaced one design issue worth a decision:
**87% of companies hit the 8-recommendation cap**, averaging 7.4 each. For a
mid-scoring firm that is a long list, and the prioritisation ordering is doing
all the work of deciding what matters. Consider lowering
`MAX_RECOMMENDATIONS`, or tightening `REFINE_BELOW`, so the output reads as a
focused action list rather than an audit. Both are one-line changes in
configuration.


---

## Reading real survey exports

`src/survey_import.py` exists because the first live survey run failed
completely: 17 responses, all rejected, purely over formatting. Google Forms
writes `Industry Sector` where the tool wanted `industry_sector`, writes the
full question text where the tool wanted `BUD_1`, and writes `Agree` where the
tool wanted `4`. Nothing about the responses was wrong.

What it does now:

- Matches columns by question wording rather than exact names. The matching is
  fuzzy on purpose — the live form has typos (`idenitfied`, `exisitng`) that
  the configuration spells correctly, and an exact match threw those questions
  away for no reason.
- Reads word answers, numbers, or `4 - Agree`, all the same.
- Accepts `.csv` and `.xlsx`.
- Keeps the open-ended answers instead of dropping them.
- Reports every column it couldn't place, so nothing disappears silently.

**Sector and country have no permitted list at all.** The first live run
returned Real Estate, Asset Management, Events, Transportation, Financial
Services and Canada — none on the original list, all real answers. A list of
five sectors and five countries cannot describe companies globally.

Open does not mean anything goes, though. `src/open_value_checks.py` checks
that an answer is a real one, because a nonsense value quietly ruins every
breakdown that groups by it afterwards:

- **Countries** are checked against the ~200 that exist, plus abbreviations,
  short forms and major cities. That is not a restriction — countries are
  genuinely enumerable. It also resolves "UAE", "Dubai" and "United Arab
  Emirates" onto one name, so a single country stops appearing as three bars.
- **Industries** are not enumerable, so they are checked against a vocabulary
  of industry words instead. Any answer containing something recognisable as
  an industry is accepted exactly as typed — "marine engineering consultancy"
  and "halal food logistics" both pass without appearing on any list.
- Anything with no country and no industry in it — `bahab`, `qwerty` — is sent
  back asking for a real answer.

Size, age and adoption stage stay closed, because they are ordered scales the
tool reasons about rather than descriptive labels. Common variants
(`250+ employees`, `over 10 years`, `Using`) are normalised onto the right band
instead of being rejected.

**A bare "Other" is not accepted.** It carries no information, so the form asks
what the other is and stores that answer instead.

### Matching by meaning

Wording matching only works on this questionnaire retyped. It scores near zero
on the same question asked in someone else's words, because it compares
characters. So there is a second pass that compares meaning: stopwords removed,
words reduced to stems, domain vocabulary folded into shared concepts
(`broadband`, `servers` and `infrastructure` all become one concept), weighted
by how rare each term is across the 32 questions, compared by cosine
similarity.

This is classical information retrieval rather than a pretrained language
model, on purpose. A sentence-transformer would match slightly better at the
cost of a large dependency, a download at startup, and results that can't be
explained to an examiner or reproduced identically a year later. Everything
here is deterministic and readable off the page.

Measured against a genuinely different survey, meaning-matching picks the right
**factor** 7 times out of 8, and the right individual **question** about 2
times out of 6. That gap is why it is used the way it is.

### What it will not do

A file that doesn't contain this questionnaire's questions is **not scored**.
The seven factors are defined by 32 specific statements; a number built from
different questions would look like a readiness score without being one, and
item-level matching is not accurate enough to pretend otherwise.

What it does instead is compare the two instruments: which of the seven factors
that survey covers, which it leaves untouched, and which of its questions
correspond to nothing here. Run against a public-sector AI survey, it reports
coverage of five factors, nothing at all on Data Readiness or Organizational
Culture, and three questions that measure outcomes (whether AI has already
improved services) rather than readiness. That comparison is useful for the
evaluation chapter in a way that a fabricated score would not be.


---

## Partial coverage, and the dataset report

A dataset that only answers some of the questions is scored on the factors it
does cover. The overall figure is re-weighted across the factors present, so a
factor nobody asked about is left out rather than counted as zero — the
difference matters, because treating "not asked" as "answered badly" makes an
incomplete dataset look like a weak one.

Anything scored this way is marked as partial, on screen and in the report,
with the missing factors named.

The dataset tab produces its own PDF and Excel analysis, built from the same
figures shown on screen — which is deliberate, since a report that disagrees
with the page that produced it is worse than no report.

**Profile shapes are split by country and by sector** whenever the data holds
more than one of either. A single averaged radar across four countries draws a
company that exists nowhere in the file.

**Written answers are read, not just stored** — see the next section.

**Cohort recommendations** come from the average profile across the dataset,
run through the same rules a single assessment uses, so the two can never
drift apart.

---

## What happens to the written answers

The questionnaire's three open questions, and any free-text column found in an
imported survey, are the only place a respondent can say something the 32 fixed
questions never asked. `src/text_analysis.py` reads them.

### Non-answers are thrown out first

A real survey's free text is full of `N/A`, `none`, `no`, `yes`, `-` and
blanks. Counting those as evidence of anything would be worse than ignoring the
column, so they are discarded before anything is measured, together with
answers too short to place (`good`, `not sure`, `more time`).

The counts are reported rather than hidden — a tool that quietly drops half the
answers and reports on the rest is reporting on a sample it has not described.
Run against the first live survey: 39 answers seen, 27 used, 12 set aside
(6 non-answers, 5 too short to place, 1 blank).

**Shares are taken over everyone surveyed, not over the people whose answers
could be read.** This was wrong first time round and worth naming: with 19
people writing "nothing" and one writing about data quality, the wrong
denominator reports that one person as 100% agreement.

### What is left is placed against the factors

Each remaining answer is matched to the readiness factor it concerns, using the
concept lexicon that matches survey columns to questions, plus a supplementary
vocabulary for the everyday words free text actually uses — a respondent writes
"the internet here is slow", not "our IT infrastructure is inadequate". That
supplementary list lives in `text_analysis.py` rather than in
`CONCEPT_LEXICON`, because the lexicon feeds the IDF weighting used for column
matching and adding words to it would move results that are already tested.

### What it does, and the line it does not cross

**It does not change any score.** The readiness score is a weighted average of
Likert responses, and moving it on the strength of a keyword match would make
it neither reproducible nor defensible. What the text changes is the
interpretation:

* every recommendation for a factor people wrote about carries their own words
  beneath it as evidence, on screen and in both exports;
* a factor the comments name repeatedly that **no score flagged** is added as
  its own item, labelled *Raised in comments* and coloured differently from the
  scored severities.

That second one is the point of collecting free text at all. A disagreement
between the numbers and the comments is a finding, and it is reported rather
than smoothed away. On a dataset it needs 20% of respondents before it is
raised, because one person out of two hundred is an anecdote; on a single
assessment there is no share to reach, so any mention counts.

### Limitations worth stating in the write-up

* Matching is lexical. An answer that names a concern without using any of the
  vocabulary, or one that uses a factor's words to say the opposite ("budget is
  the one thing we *do* have"), will be placed wrongly. Polarity is not
  detected.
* The 20% threshold is a chosen starting value, not an empirically derived one.
* Set-aside answers are counted but not inspected; a genuine answer written in
  two words is lost along with the non-answers.
