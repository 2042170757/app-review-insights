"""Deterministic analysis scope constraints and review filtering."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_SCOPE_DIR = Path("artifacts/analysis_scope")
VALIDATION_PASS = "PASS"
VALIDATION_FAIL = "FAIL"


@dataclass(frozen=True)
class RatingConstraint:
    min: int
    max: int

    def to_dict(self) -> dict[str, int]:
        return {"min": self.min, "max": self.max}


@dataclass
class ScopeValidationResult:
    status: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScopeFilterResult:
    input_count: int
    selected_count: int
    excluded_count: int
    constraints: dict[str, Any]
    selected_reviews: list[dict[str, Any]]
    excluded_review_ids: list[str]
    validation: ScopeValidationResult

    def report(self) -> dict[str, Any]:
        return {
            "input_count": self.input_count,
            "selected_count": self.selected_count,
            "excluded_count": self.excluded_count,
            "constraint": self.constraints,
            "excluded_review_ids": self.excluded_review_ids,
        }


def normalize_constraints(value: Any) -> dict[str, Any]:
    if value is None or value == {}:
        return {}
    if not isinstance(value, dict):
        return {"_invalid": value}
    normalized: dict[str, Any] = {}
    rating = value.get("rating")
    if rating is not None:
        normalized["rating"] = rating
    for key in value:
        if key != "rating":
            normalized[key] = value[key]
    return normalized


def validate_constraints(value: Any) -> ScopeValidationResult:
    constraints = normalize_constraints(value)
    errors: list[str] = []
    if "_invalid" in constraints:
        errors.append("constraints must be an object")
    unsupported = sorted(key for key in constraints if key not in {"rating", "_invalid"})
    for key in unsupported:
        errors.append(f"unsupported constraint: {key}")

    rating = constraints.get("rating")
    normalized_rating: dict[str, int] | None = None
    if rating is not None:
        if not isinstance(rating, dict):
            errors.append("constraints.rating must be an object")
        else:
            min_rating = _integer_value(rating.get("min"))
            max_rating = _integer_value(rating.get("max"))
            if min_rating is None:
                errors.append("constraints.rating.min must be an integer")
            if max_rating is None:
                errors.append("constraints.rating.max must be an integer")
            if min_rating is not None and min_rating < 1:
                errors.append("constraints.rating.min must be >= 1")
            if max_rating is not None and max_rating > 5:
                errors.append("constraints.rating.max must be <= 5")
            if min_rating is not None and max_rating is not None and min_rating > max_rating:
                errors.append("constraints.rating.min must be <= max")
            if not errors and min_rating is not None and max_rating is not None:
                normalized_rating = RatingConstraint(min=min_rating, max=max_rating).to_dict()

    normalized: dict[str, Any] = {}
    if normalized_rating:
        normalized["rating"] = normalized_rating
    return ScopeValidationResult(
        status=VALIDATION_PASS if not errors else VALIDATION_FAIL,
        passed=not errors,
        errors=errors,
        constraints=normalized,
    )


def apply_analysis_scope(
    reviews: list[dict[str, Any]],
    constraints: Any,
) -> ScopeFilterResult:
    validation = validate_constraints(constraints)
    if not validation.passed:
        return ScopeFilterResult(
            input_count=len(reviews),
            selected_count=0,
            excluded_count=len(reviews),
            constraints=normalize_constraints(constraints),
            selected_reviews=[],
            excluded_review_ids=[_review_id(review) for review in reviews if _review_id(review)],
            validation=validation,
        )

    selected: list[dict[str, Any]] = []
    excluded: list[str] = []
    rating = validation.constraints.get("rating")
    for review in reviews:
        if _review_in_scope(review, rating):
            selected.append(review)
        else:
            review_id = _review_id(review)
            if review_id:
                excluded.append(review_id)

    filter_result = ScopeFilterResult(
        input_count=len(reviews),
        selected_count=len(selected),
        excluded_count=len(reviews) - len(selected),
        constraints=validation.constraints,
        selected_reviews=selected,
        excluded_review_ids=excluded,
        validation=validation,
    )
    selected_validation_errors = validate_selected_reviews(filter_result)
    if selected_validation_errors:
        filter_result.validation = ScopeValidationResult(
            status=VALIDATION_FAIL,
            passed=False,
            errors=selected_validation_errors,
            constraints=validation.constraints,
        )
    return filter_result


def validate_selected_reviews(result: ScopeFilterResult) -> list[str]:
    errors: list[str] = []
    rating = result.constraints.get("rating")
    if not rating:
        return errors
    for review in result.selected_reviews:
        review_id = _review_id(review) or "<unknown>"
        review_rating = _integer_value(review.get("rating"))
        if review_rating is None or review_rating < rating["min"] or review_rating > rating["max"]:
            errors.append(f"{review_id}: selected review rating outside constraint")
    return errors


def write_scope_outputs(
    result: ScopeFilterResult,
    *,
    output_dir: Path = DEFAULT_SCOPE_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_path = output_dir / "selected_reviews.json"
    report_path = output_dir / "scope_report.json"
    validation_path = output_dir / "scope_validation.json"
    selected_path.write_text(
        json.dumps({"reviews": result.selected_reviews}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path.write_text(json.dumps(result.report(), ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return {"selected_reviews": selected_path, "scope_report": report_path, "scope_validation": validation_path}


def _review_in_scope(review: dict[str, Any], rating: Any) -> bool:
    if not rating:
        return True
    review_rating = _integer_value(review.get("rating"))
    return review_rating is not None and rating["min"] <= review_rating <= rating["max"]


def _integer_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _review_id(review: dict[str, Any]) -> str:
    value = review.get("id")
    return value.strip() if isinstance(value, str) else ""
