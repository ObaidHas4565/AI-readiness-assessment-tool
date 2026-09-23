"""
Synthetic data generation

This file makes up fake companies to test the assessment tool with, since real
survey responses aren't in yet. Each company is built from one of the readiness
profiles defined below (early stage, well funded, tech focused, and so on),
each of which sets an intended readiness level per factor. Answers are then
sampled around that level with some random variation and written out as raw
survey answers, so reverse-worded items get inverted the same way a real
respondent's answer would be. That means the CSV this writes looks exactly like
a real survey export and goes through the same validation and scoring path.

Worth being clear about what this can and can't show: it's useful for checking
the scoring and recommendation logic behaves sensibly across a wide range of
inputs, but it can't tell us whether the scoring reflects real companies,
because the patterns in it are ones that were assumed rather than observed in
real responses. Only real survey data can answer that. Once responses are
collected they should become the main test data, with this kept mainly for
edge-case and validation testing.

The categorical fields (industry, size, years in operation and so on) aren't
random either -- they're linked in sensible ways, e.g. larger firms tend to
have more budget and IT capability, and `current_ai_stage` is set from each
company's overall readiness. That last link matters because it's what lets the
factor-weighting method be tried out on this data before real responses exist.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import score_configuration as cfg
from .company_profile import CompanyProfile


# ---------------------------------------------------------------------------
# Readiness Profiles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Readiness_Profile:
    """
    A company pattern.

    `factor_levels` gives the intended readiness level (1-5) per factor, before
    per-item noise is added. `weight` is how often this profile gets picked.
    `size_bias` and `age_bias` steer the categorical fields so a company's size
    and age make sense alongside its readiness pattern.
    """

    name: str
    weight: float
    factor_levels: Dict[str, float]
    size_bias: Sequence[str]
    age_bias: Sequence[str]
    sector_bias: Optional[Sequence[str]] = None


READINESS_PROFILES: Tuple[Readiness_Profile, ...] = (
    Readiness_Profile(
        name="Early_Stage_Adopter",
        weight=0.18,
        factor_levels={
            "budget": 1.6, "workforce": 1.8, "leadership": 2.0, "data": 1.7,
            "technology": 1.8, "culture": 2.6, "governance": 1.6,
        },
        size_bias=("1-9", "1-9", "10-49"),
        age_bias=("Under 2 years", "2-5 years"),
    ),
    Readiness_Profile(
        name="Well_Funded",
        weight=0.14,
        factor_levels={
            "budget": 4.3, "workforce": 2.2, "leadership": 3.6, "data": 1.9,
            "technology": 2.8, "culture": 3.0, "governance": 2.0,
        },
        size_bias=("50-249", "250+", "10-49"),
        age_bias=("6-10 years", "10+ years"),
        sector_bias=("Manufacturing", "Retail", "Healthcare"),
    ),
    Readiness_Profile(
        name="Tech_Focused",
        weight=0.14,
        factor_levels={
            "budget": 2.4, "workforce": 3.9, "leadership": 3.0, "data": 4.0,
            "technology": 4.4, "culture": 3.8, "governance": 2.6,
        },
        size_bias=("1-9", "10-49", "10-49"),
        age_bias=("Under 2 years", "2-5 years", "6-10 years"),
        sector_bias=("Technology", "Marketing"),
    ),
    Readiness_Profile(
        name="Traditional_Company",
        weight=0.15,
        factor_levels={
            "budget": 3.2, "workforce": 2.4, "leadership": 2.6, "data": 2.8,
            "technology": 2.2, "culture": 1.9, "governance": 3.0,
        },
        size_bias=("50-249", "250+", "10-49"),
        age_bias=("10+ years", "10+ years", "6-10 years"),
        sector_bias=("Manufacturing", "Retail", "Healthcare"),
    ),
    Readiness_Profile(
        name="Developing",
        weight=0.16,
        factor_levels={
            "budget": 3.1, "workforce": 3.0, "leadership": 3.2, "data": 3.0,
            "technology": 3.2, "culture": 3.1, "governance": 2.9,
        },
        size_bias=("10-49", "50-249"),
        age_bias=("2-5 years", "6-10 years", "10+ years"),
    ),
    Readiness_Profile(
        name="Leadership_Driven",
        weight=0.10,
        factor_levels={
            "budget": 3.0, "workforce": 2.3, "leadership": 4.4, "data": 2.4,
            "technology": 2.5, "culture": 4.0, "governance": 2.8,
        },
        size_bias=("10-49", "50-249"),
        age_bias=("2-5 years", "6-10 years"),
    ),
    Readiness_Profile(
        name="Governance_Focused",
        weight=0.08,
        factor_levels={
            "budget": 3.4, "workforce": 3.1, "leadership": 3.4, "data": 3.8,
            "technology": 3.3, "culture": 2.8, "governance": 4.5,
        },
        size_bias=("250+", "50-249"),
        age_bias=("10+ years",),
        sector_bias=("Healthcare", "Technology"),
    ),
    Readiness_Profile(
        name="Advanced_Adopter",
        weight=0.05,
        factor_levels={
            "budget": 4.4, "workforce": 4.3, "leadership": 4.6, "data": 4.4,
            "technology": 4.5, "culture": 4.3, "governance": 4.1,
        },
        size_bias=("250+", "50-249"),
        age_bias=("10+ years", "6-10 years"),
        sector_bias=("Technology", "Marketing"),
    ),
)


# Noise applied to each item around the profile's factor level. Higher values
# give more variation within a factor (some items strong, some weak), which is
# what makes the item-level gap detection worth testing.
ITEM_NOISE_SD: float = 0.75

# Extra per-company drift on each factor, so two companies built from the same
# profile don't come out nearly identical.
FACTOR_DRIFT_SD: float = 0.45


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _clamp(value: int, low: int = cfg.RATING_MIN, high: int = cfg.RATING_MAX) -> int:
    return max(low, min(high, value))


def _sample_stage(mean_readiness: float, rng: random.Random) -> str:
    """
    Assign current_ai_stage from overall readiness, with noise.

    The relationship is deliberate: it gives the dataset an ordinal outcome
    variable that factor scores can be correlated against, which is how
    empirical factor weights would be derived from real data.
    """
    jittered = mean_readiness + rng.gauss(0, 0.45)

    if jittered < 2.0:
        weights = (0.55, 0.33, 0.09, 0.03, 0.00)
    elif jittered < 2.75:
        weights = (0.25, 0.42, 0.23, 0.09, 0.01)
    elif jittered < 3.5:
        weights = (0.08, 0.27, 0.35, 0.24, 0.06)
    elif jittered < 4.25:
        weights = (0.02, 0.10, 0.27, 0.46, 0.15)
    else:
        weights = (0.00, 0.03, 0.13, 0.44, 0.40)

    return rng.choices(cfg.AI_ADOPTION_STAGES, weights=weights, k=1)[0]


# Sector and country are open fields, so generated companies use real names
# rather than the dropdown shortlist. "Other" is deliberately absent: it is not
# a sector, and the tool now asks for a specific answer instead of accepting it.
GENERATED_SECTORS: Tuple[str, ...] = (
    "Retail", "Technology", "Manufacturing", "Marketing", "Healthcare",
    "Construction", "Logistics", "Hospitality", "Financial Services",
    "Real Estate", "Education", "Professional Services",
)

GENERATED_REGIONS: Tuple[str, ...] = (
    "UAE", "UK", "India", "USA", "Saudi Arabia", "Canada",
    "Singapore", "Germany", "Australia", "Nigeria",
)


def _sample_categoricals(
    read_profile: Readiness_Profile, mean_readiness: float, rng: random.Random
) -> Dict[str, str]:
    sectors = read_profile.sector_bias or GENERATED_SECTORS
    return {
        "industry_sector": rng.choice(tuple(sectors)),
        "employee_band": rng.choice(tuple(read_profile.size_bias)),
        "years_in_operation": rng.choice(tuple(read_profile.age_bias)),
        # Country is not tied to readiness -- there is no evidence base for
        # assuming a country effect, so it is drawn independently.
        "region": rng.choice(GENERATED_REGIONS),
        "current_ai_stage": _sample_stage(mean_readiness, rng),
    }


def generate_company(
    rng: random.Random, read_profile: Optional[Readiness_Profile] = None
) -> Dict[str, object]:
    """
    Generate one synthetic company as a flat dict in the tool's schema.

    Returned values for rating items are RAW answers -- reverse-worded items are
    inverted here, exactly as a real respondent would have answered them, so
    the row exercises the same reverse-coding path as genuine survey data.
    """
    if read_profile is None:
        read_profile = rng.choices(
            READINESS_PROFILES, weights=[p.weight for p in READINESS_PROFILES], k=1
        )[0]

    row: Dict[str, object] = {"profile": read_profile.name}
    readiness_values: List[int] = []

    for factor in cfg.FACTORS:
        level = read_profile.factor_levels[factor.id] + rng.gauss(0, FACTOR_DRIFT_SD)

        for item in factor.items:
            readiness = _clamp(round(rng.gauss(level, ITEM_NOISE_SD)))
            readiness_values.append(readiness)
            # Convert intended readiness into the answer the respondent gives.
            row[item.id] = (cfg.REVERSE_PIVOT - readiness) if item.reverse else readiness

    mean_readiness = sum(readiness_values) / len(readiness_values)
    row.update(_sample_categoricals(read_profile, mean_readiness, rng))
    return row


def generate_dataset(n: int = 300, seed: Optional[int] = 42) -> List[Dict[str, object]]:
    """
    Generate `n` synthetic companies.

    A fixed seed is used by default so the dataset is reproducible -- the same
    seed always gives the same data, which is what makes results reported in
    the write-up verifiable by anyone re-running the script.
    """
    rng = random.Random(seed)
    rows = []
    for index in range(n):
        row = generate_company(rng)
        row["company_id"] = f"SYN{index + 1:04d}"
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# CSV round-trip
# ---------------------------------------------------------------------------

CSV_FIELDNAMES: List[str] = (
    ["company_id", "profile"]
    + list(cfg.CATEGORICAL_FIELDS.keys())
    + [item.id for item in cfg.ALL_ITEMS]
)


def write_csv(rows: Iterable[Dict[str, object]], path: str) -> int:
    """Write generated rows to CSV. Returns the number of rows written."""
    rows = list(rows)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_FIELDNAMES})
    return len(rows)


def load_profiles_from_lines(lines: Iterable[str]) -> List[Tuple[str, CompanyProfile]]:
    """
    Parse CSV lines in the tool's schema into (identifier, CompanyProfile) pairs.

    Takes any iterable of lines rather than a path, so an uploaded file can be
    read straight from memory without being written to disk first -- which is
    what the dashboard needs, since nothing about a submission is meant to be
    stored anywhere.

    CSV values arrive as strings, so rating columns are cast to int here.
    Anything non-numeric is left alone on purpose, so CompanyProfile validation
    reports it properly instead of this loader crashing on it.
    """
    profiles: List[Tuple[str, CompanyProfile]] = []

    for raw_row in csv.DictReader(lines):
        row: Dict[str, object] = dict(raw_row)
        for item in cfg.ALL_ITEMS:
            value = row.get(item.id)
            if value is None or value == "":
                row.pop(item.id, None)
                continue
            try:
                row[item.id] = int(value)
            except (TypeError, ValueError):
                pass  # left as-is; validation will report it
        identifier = str(row.get("company_id") or f"row{len(profiles) + 1}")
        profiles.append((identifier, CompanyProfile.from_dict(row)))

    return profiles


def load_profiles_from_csv(path: str) -> List[Tuple[str, CompanyProfile]]:
    """
    Load a CSV file in the tool's schema into (identifier, CompanyProfile) pairs.

    Works for this module's output and for any real survey export mapped to the
    same column names.
    """
    with open(path, newline="", encoding="utf-8") as handle:
        return load_profiles_from_lines(handle)


# ---------------------------------------------------------------------------
# Human-readable outputs
# ---------------------------------------------------------------------------
# The canonical CSV uses short item codes (BUD_1, WRK_3, ...) because they are
# stable identifiers that the code, the tests and the write-up can all refer to
# unambiguously. They are not readable on their own, so the two functions below
# produce the companion artefacts that make the dataset inspectable by a person.

def write_data_dictionary(path: str) -> None:
    """
    Write a Markdown data dictionary explaining every column.

    This is the reference to keep beside the dataset -- and the thing to put in
    the appendix, since an examiner reading the raw CSV has the same problem
    anyone else does: the codes mean nothing without it.
    """
    lines: List[str] = [
        "# Data Dictionary",
        "",
        "Column reference for the AI Adoption Readiness assessment dataset.",
        "",
        "## Context columns",
        "",
        "| Column | Meaning | Allowed values |",
        "|---|---|---|",
        "| `company_id` | Synthetic row identifier | SYN0001, SYN0002, ... |",
        "| `profile` | Readiness profile used (synthetic data only; absent from real data) | "
        + ", ".join(f"`{p.name}`" for p in READINESS_PROFILES)
        + " |",
    ]

    labels = {
        "industry_sector": "Industry sector",
        "employee_band": "Number of employees",
        "years_in_operation": "Years in operation",
        "region": "Region / country of operation",
        "current_ai_stage": "Current stage of AI adoption",
    }
    for field, allowed in cfg.CATEGORICAL_FIELDS.items():
        values = ", ".join(f"`{v}`" for v in allowed)
        lines.append(f"| `{field}` | {labels[field]} | {values} |")

    lines += [
        "",
        "None of these context columns is scored. They provide segmentation "
        "context only. `current_ai_stage` is ordinal and is the outcome "
        "variable against which empirical factor weights would be derived.",
        "",
        "## Response scale",
        "",
        "Every readiness column holds a **raw** answer on a 5-point agreement scale:",
        "",
        "| Value | Label |",
        "|---|---|",
    ]
    for value in sorted(cfg.RATING_LABELS, reverse=True):
        lines.append(f"| {value} | {cfg.RATING_LABELS[value]} |")

    lines += [
        "",
        "**Reverse-worded items are marked below.** For these, the statement "
        "describes a *barrier*, so agreeing indicates LOWER readiness. The "
        "scoring engine re-codes them as `6 - raw` before averaging. Values in "
        "the CSV are raw, exactly as a respondent would answer.",
        "",
        "## Readiness columns",
        "",
    ]

    for factor in cfg.FACTORS:
        lines += [
            f"### {factor.name}",
            "",
            f"Weight: `{factor.weight:.4f}` &nbsp;|&nbsp; Items: {len(factor.items)}",
            "",
            "| Column | Statement | Reverse? |",
            "|---|---|---|",
        ]
        for item in factor.items:
            mark = "**Yes**" if item.reverse else "No"
            lines.append(f"| `{item.id}` | {item.text} | {mark} |")
        lines.append("")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


# Values like "1-9" and "10-49" are silently converted to dates by Excel when a
# CSV is opened directly -- "1-9" becomes 01-Sep and "10-49" becomes Oct-49,
# because Excel reads them as day-month and month-year. The underlying file is
# unaffected, but the spreadsheet is then wrong on screen and permanently wrong
# if saved. Since the readable CSV exists specifically to be opened in Excel,
# its values are written in a form Excel cannot misread.

_EXCEL_SAFE_EMPLOYEE_BANDS: Dict[str, str] = {
    "1-9": "1 to 9 employees",
    "10-49": "10 to 49 employees",
    "50-249": "50 to 249 employees",
    "250+": "250+ employees",
}


def _excel_safe(field: str, value: object) -> object:
    """Rewrite values Excel would mis-parse as dates. Readable CSV only."""
    if field == "employee_band":
        return _EXCEL_SAFE_EMPLOYEE_BANDS.get(str(value), value)
    return value


def write_readable_csv(rows: Iterable[Dict[str, object]], path: str) -> int:
    """
    Write a second CSV using full question text as headers and word labels
    ("Agree") instead of numbers.

    Intended for opening in Excel to eyeball the data. It is NOT the file the
    tool reads -- `load_profiles_from_csv` expects the coded version, because
    stable short identifiers are what the code and tests refer to.
    """
    rows = list(rows)

    header = ["company_id", "readiness_profile"]
    header += [f.replace("_", " ").title() for f in cfg.CATEGORICAL_FIELDS]
    for item in cfg.ALL_ITEMS:
        factor_name = cfg.FACTORS_BY_ID[cfg.ITEM_TO_FACTOR[item.id]].name
        suffix = "  [REVERSE-WORDED]" if item.reverse else ""
        header.append(f"{factor_name} | {item.id} | {item.text}{suffix}")

    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            record = [row.get("company_id", ""), row.get("profile", "")]
            record += [
                _excel_safe(field, row.get(field, ""))
                for field in cfg.CATEGORICAL_FIELDS
            ]
            for item in cfg.ALL_ITEMS:
                value = row.get(item.id)
                record.append(
                    f"{value} - {cfg.RATING_LABELS[value]}"
                    if isinstance(value, int) and value in cfg.RATING_LABELS
                    else value
                )
            writer.writerow(record)

    return len(rows)


# ---------------------------------------------------------------------------
# Deliberately invalid rows, for testing validation
# ---------------------------------------------------------------------------

def generate_invalid_rows(seed: Optional[int] = 13) -> List[Tuple[str, Dict[str, object]]]:
    """
    Produce rows with the defects a REAL survey export actually contains.

    The clean synthetic dataset never exercises the validation path, so on its
    own it would give false confidence: the tool would look robust simply
    because nothing malformed was ever sent to it. Each row below pairs a
    description with a broken row, so a test can assert that validation
    rejects it and says something useful about why.
    """
    rng = random.Random(seed)
    base = generate_company(rng)

    def variant(**changes: object) -> Dict[str, object]:
        row = dict(base)
        row.update(changes)
        return row

    dropped_item = variant()
    del dropped_item[cfg.ALL_ITEMS[0].id]

    blank_item = variant(**{cfg.ALL_ITEMS[3].id: ""})

    return [
        ("skipped question (respondent left one blank)", dropped_item),
        ("empty string where a number is expected", blank_item),
        ("out-of-range answer (scale mis-mapped on import)", variant(**{cfg.ALL_ITEMS[5].id: 7})),
        ("zero-indexed scale (0-4 instead of 1-5)", variant(**{cfg.ALL_ITEMS[6].id: 0})),
        # Note: an unfamiliar sector or country is NOT in this list any more.
        # Those fields are open, so "Logistics" or "Canada" are ordinary
        # answers rather than errors -- a fixed list can't describe companies
        # globally, and rejecting them was the tool's mistake, not the data's.
        ("sector left blank", variant(industry_sector="")),
        ("bare 'Other' with nothing specified", variant(industry_sector="Other")),
        ("employee band outside the survey's options", variant(employee_band="500+")),
        ("missing required context field", variant(region=None)),
    ]
