"""
CompanyProfile
==============

Represents the data a single company submits to the assessment tool: five
categorical context fields plus the 32 Likert responses.

Per the Class Diagram, CompanyProfile is the input object that is passed to the
ScoringEngine. Per the Session Diagram, validation happens before the data
reaches the ScoringEngine -- so validation lives here as a method the dashboard
calls, and the ScoringEngine can assume it receives a valid profile.

Privacy (NFR): this object deliberately holds no company name, address or any
other identifying field. Region is coarse (country level) and is collected for
segmentation only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from .score_configuration import (
    ALL_ITEMS,
    CATEGORICAL_FIELDS,
    ITEMS_BY_ID,
    LIKERT_MAX,
    LIKERT_MIN,
    NEEDS_SPECIFIC_VALUE,
    OPEN_FIELDS,
)


class ValidationError(ValueError):
    """Raised when a profile is scored without passing validation first."""


@dataclass
class CompanyProfile:
    """
    A single company's submitted assessment data.

    Attributes
    ----------
    responses:
        Mapping of item id -> raw Likert value (1-5), as answered. Raw means
        NOT reverse-coded; re-coding is the ScoringEngine's job so that the
        original response is always recoverable.
    industry_sector, employee_band, years_in_operation, region, current_ai_stage:
        Categorical context fields. Not scored.
    """

    responses: Dict[str, int] = field(default_factory=dict)

    industry_sector: Optional[str] = None
    employee_band: Optional[str] = None
    years_in_operation: Optional[str] = None
    region: Optional[str] = None
    current_ai_stage: Optional[str] = None

    # Optional free-text answers from the survey's Section 3. Never scored,
    # never required, and excluded from the context summary by default.
    open_biggest_barrier: str = ""
    open_what_would_help: str = ""
    open_additional_comments: str = ""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CompanyProfile":
        """
        Build a profile from a flat dictionary.

        Accepts either a nested {"responses": {...}} form or a flat form where
        item ids sit alongside the categorical fields. The flat form is what a
        CSV row of survey data looks like, which keeps loading real and
        synthetic data straightforward.
        """
        data = dict(data)
        responses: Dict[str, int] = dict(data.get("responses") or {})

        for item in ALL_ITEMS:
            if item.id in data:
                responses[item.id] = data[item.id]

        # Tidy the categorical answers here, at the one point every profile
        # passes through, so a country typed into the form and the same
        # country read from a CSV are stored identically. Without this, "UAE"
        # from the questionnaire and "United Arab Emirates" from an import end
        # up as two separate groups in the same analysis.
        from .score_configuration import normalise_category

        return cls(
            responses=responses,
            industry_sector=normalise_category(
                "industry_sector", data.get("industry_sector")),
            employee_band=normalise_category(
                "employee_band", data.get("employee_band")),
            years_in_operation=normalise_category(
                "years_in_operation", data.get("years_in_operation")),
            region=normalise_category("region", data.get("region")),
            current_ai_stage=normalise_category(
                "current_ai_stage", data.get("current_ai_stage")),
            open_biggest_barrier=data.get("open_biggest_barrier", "") or "",
            open_what_would_help=data.get("open_what_would_help", "") or "",
            open_additional_comments=data.get("open_additional_comments", "") or "",
        )

    # ------------------------------------------------------------------
    # Validation (FR2: reject incomplete or out-of-range entries)
    # ------------------------------------------------------------------

    def validate(self) -> List[str]:
        """
        Return a list of human-readable validation errors. Empty list == valid.

        Returning messages rather than raising lets the dashboard show every
        problem at once instead of one per submission attempt.
        """
        errors: List[str] = []

        # --- categorical fields ---
        for field_name, allowed in CATEGORICAL_FIELDS.items():
            value = getattr(self, field_name)

            if value is None or str(value).strip() == "":
                errors.append(
                    f"'{_label(field_name)}' is required "
                    f"(column '{field_name}')."
                )
                continue

            text = str(value).strip()

            # "Other" on its own says nothing about the company, so it is sent
            # back for a specific answer rather than stored as a category.
            if text.lower() in NEEDS_SPECIFIC_VALUE:
                errors.append(
                    f"'{_label(field_name)}' needs a specific answer — "
                    f"{text!r} on its own doesn't say which."
                )
                continue

            # Sector and country are open -- there is no permitted list, so a
            # company anywhere in any industry can answer. What is checked is
            # that the answer is a real one: a country that exists, or
            # something that reads as an industry. Gibberish is sent back,
            # because a nonsense value quietly ruins every breakdown that
            # groups by it later.
            if field_name in OPEN_FIELDS:
                from .open_value_checks import check_open_value

                _, problem = check_open_value(field_name, text)
                if problem:
                    errors.append(problem)
                continue

            if text not in allowed:
                errors.append(
                    f"'{_label(field_name)}' must be one of {', '.join(allowed)} "
                    f"(got {value!r})."
                )

        # --- Likert responses ---
        missing = [item.id for item in ALL_ITEMS if item.id not in self.responses]
        if missing:
            errors.append(
                f"{len(missing)} readiness question(s) not answered: "
                f"{', '.join(missing)}."
            )

        for item_id, value in self.responses.items():
            if item_id not in ITEMS_BY_ID:
                errors.append(f"Unknown question id: {item_id!r}.")
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(
                    f"Answer to {item_id} must be a whole number "
                    f"{LIKERT_MIN}-{LIKERT_MAX} (got {value!r})."
                )
            elif not (LIKERT_MIN <= value <= LIKERT_MAX):
                errors.append(
                    f"Answer to {item_id} is out of range: {value} "
                    f"(allowed {LIKERT_MIN}-{LIKERT_MAX})."
                )

        return errors

    def is_valid(self) -> bool:
        return not self.validate()

    def raise_if_invalid(self) -> None:
        errors = self.validate()
        if errors:
            raise ValidationError("; ".join(errors))

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def notes(self) -> Dict[str, str]:
        """
        The written answers, keyed by the question that prompted them.

        Never scored. They are where a respondent explains what a number
        cannot, so they travel with the results and appear in the report.
        """
        written = {
            "Biggest barrier to adopting AI": self.open_biggest_barrier,
            "What would help most": self.open_what_would_help,
            "Anything else": self.open_additional_comments,
        }
        return {q: a.strip() for q, a in written.items() if a and a.strip()}

    def context_summary(self) -> Dict[str, Optional[str]]:
        """Non-identifying context carried through onto the results object."""
        return {
            "industry_sector": self.industry_sector,
            "employee_band": self.employee_band,
            "years_in_operation": self.years_in_operation,
            "region": self.region,
            "current_ai_stage": self.current_ai_stage,
        }


def _label(field_name: str) -> str:
    return field_name.replace("_", " ").title()
