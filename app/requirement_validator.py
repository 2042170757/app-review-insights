"""Deterministic validation for generated Requirements."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from app.requirement_schema import Requirement, VALID_PRIORITIES


STATUS_SUCCESS = "Success"
STATUS_EMPTY_REQUIREMENTS = "Empty Requirements"
STATUS_INVALID_JSON = "Invalid JSON"
STATUS_SCHEMA_VALIDATION_FAILED = "Schema Validation Failed"
STATUS_UNKNOWN_FINDING_ID = "Unknown Finding ID"
STATUS_FINDING_VALIDATION_FAILED = "Finding Validation Failed"
STATUS_INELIGIBLE_FINDING = "Ineligible Finding"
STATUS_TRACEABILITY_MISMATCH = "Traceability Mismatch"
STATUS_ACCEPTANCE_CRITERIA_INVALID = "Acceptance Criteria Invalid"
STATUS_PRIORITY_INVALID = "Priority Invalid"
STATUS_PROHIBITED_IMPLEMENTATION_DETAIL = "Prohibited Implementation Detail"


@dataclass
class RequirementValidationResult:
    status: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    unknown_finding_ids: list[str] = field(default_factory=list)
    ineligible_finding_ids: list[str] = field(default_factory=list)
    traceability_errors: list[str] = field(default_factory=list)
    acceptance_criteria_errors: list[str] = field(default_factory=list)
    implementation_detail_errors: list[str] = field(default_factory=list)
    implementation_detail_warnings: list[str] = field(default_factory=list)
    priority_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["requirements"] = [asdict(requirement) for requirement in self.requirements]
        return payload


def validate_requirement_output(
    raw_text: str,
    *,
    findings_by_id: dict[str, dict[str, Any]],
    finding_validation_passed: bool,
    eligible_finding_ids: set[str],
) -> RequirementValidationResult:
    if not finding_validation_passed:
        return RequirementValidationResult(
            status=STATUS_FINDING_VALIDATION_FAILED,
            passed=False,
            errors=["finding validation is not PASS"],
        )
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return RequirementValidationResult(
            status=STATUS_INVALID_JSON,
            passed=False,
            errors=[f"Invalid JSON: {exc.msg}"],
        )
    return validate_requirement_payload(
        payload,
        findings_by_id=findings_by_id,
        eligible_finding_ids=eligible_finding_ids,
    )


def validate_requirement_payload(
    payload: Any,
    *,
    findings_by_id: dict[str, dict[str, Any]],
    eligible_finding_ids: set[str],
) -> RequirementValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    requirements: list[Requirement] = []

    if not isinstance(payload, dict):
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: root must be an object"])
    raw_requirements = payload.get("requirements")
    if raw_requirements is None:
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: missing requirements"])
    if not isinstance(raw_requirements, list):
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: requirements must be a list"])
    if not raw_requirements:
        return RequirementValidationResult(
            status=STATUS_EMPTY_REQUIREMENTS,
            passed=True,
            warnings=["empty_requirements"],
        )

    seen_requirement_ids: set[str] = set()
    unknown_finding_errors: list[str] = []
    unknown_finding_ids: set[str] = set()
    ineligible_finding_errors: list[str] = []
    ineligible_finding_ids: set[str] = set()
    traceability_errors: list[str] = []
    criteria_errors: list[str] = []
    priority_errors: list[str] = []
    implementation_errors: list[str] = []
    implementation_warnings: list[str] = []

    for index, raw_requirement in enumerate(raw_requirements):
        prefix = f"requirements[{index}]"
        if not isinstance(raw_requirement, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        requirement_id = _text(raw_requirement.get("requirement_id"))
        finding_ids = _normalize_id_list(raw_requirement.get("finding_ids"), f"{prefix}.finding_ids", errors)
        title = _text(raw_requirement.get("title"))
        description = _text(raw_requirement.get("description"))
        acceptance_criteria = _normalize_text_list(
            raw_requirement.get("acceptance_criteria"),
            f"{prefix}.acceptance_criteria",
            errors,
            min_items=1,
        )
        priority = _text(raw_requirement.get("priority"))
        priority_rationale = _text(raw_requirement.get("priority_rationale"))
        risks = _normalize_text_list(raw_requirement.get("risks"), f"{prefix}.risks", errors, min_items=0)
        success_metrics = _normalize_text_list(
            raw_requirement.get("success_metrics"),
            f"{prefix}.success_metrics",
            errors,
            min_items=0,
        )
        uncertainty = _text_allow_empty(raw_requirement.get("uncertainty"))
        source_review_ids = _optional_id_list(raw_requirement.get("source_review_ids"), f"{prefix}.source_review_ids", errors)

        if not requirement_id:
            errors.append(f"{prefix}.requirement_id: required")
        elif requirement_id in seen_requirement_ids:
            errors.append(f"{prefix}.requirement_id: duplicate {requirement_id}")
        else:
            seen_requirement_ids.add(requirement_id)
        if not title:
            errors.append(f"{prefix}.title: required")
        if not description:
            errors.append(f"{prefix}.description: required")
        if not priority_rationale:
            errors.append(f"{prefix}.priority_rationale: required")
        if uncertainty is None:
            errors.append(f"{prefix}.uncertainty: required")
        if priority not in VALID_PRIORITIES:
            priority_errors.append(f"{prefix}.priority: invalid {priority!r}")

        finding_review_ids: set[str] = set()
        for finding_id in finding_ids:
            finding = findings_by_id.get(finding_id)
            if not finding:
                unknown_finding_errors.append(f"{prefix}.finding_ids: unknown finding id {finding_id}")
                unknown_finding_ids.add(finding_id)
                continue
            if finding_id not in eligible_finding_ids:
                ineligible_finding_errors.append(f"{prefix}.finding_ids: ineligible finding id {finding_id}")
                ineligible_finding_ids.add(finding_id)
            finding_review_ids.update(_list_text(finding.get("review_ids")))

        if source_review_ids is not None and finding_ids:
            if source_review_ids and finding_review_ids and not set(source_review_ids).intersection(finding_review_ids):
                traceability_errors.append(
                    f"{prefix}.source_review_ids: no overlap with referenced finding evidence"
                )
            for review_id in source_review_ids:
                if review_id not in finding_review_ids:
                    traceability_errors.append(
                        f"{prefix}.source_review_ids: review id {review_id} is outside referenced finding evidence"
                    )

        for criterion_index, criterion in enumerate(acceptance_criteria):
            if _is_bad_acceptance_criterion(criterion):
                criteria_errors.append(
                    f"{prefix}.acceptance_criteria[{criterion_index}]: not specific or verifiable enough"
                )
        implementation_text = " ".join(
            [title, description, *acceptance_criteria, *risks, *success_metrics]
        ).lower()
        for term in SEVERE_IMPLEMENTATION_TERMS:
            if term in implementation_text:
                implementation_errors.append(f"{prefix}: prohibited implementation detail {term!r}")
        for term in WARNING_IMPLEMENTATION_TERMS:
            if term in implementation_text:
                implementation_warnings.append(f"{prefix}: possible implementation detail {term!r}")

        if (
            requirement_id
            and finding_ids
            and title
            and description
            and acceptance_criteria
            and priority in VALID_PRIORITIES
            and priority_rationale
            and uncertainty is not None
            and not criteria_errors
            and not implementation_errors
        ):
            requirements.append(
                Requirement(
                    requirement_id=requirement_id,
                    finding_ids=finding_ids,
                    title=title,
                    description=description,
                    acceptance_criteria=acceptance_criteria,
                    priority=priority,
                    priority_rationale=priority_rationale,
                    risks=risks,
                    success_metrics=success_metrics,
                    uncertainty=uncertainty,
                    source_review_ids=source_review_ids,
                )
            )

    if unknown_finding_errors:
        return _fail(
            STATUS_UNKNOWN_FINDING_ID,
            errors + unknown_finding_errors,
            unknown_finding_ids=sorted(unknown_finding_ids),
        )
    if ineligible_finding_errors:
        return _fail(
            STATUS_INELIGIBLE_FINDING,
            errors + ineligible_finding_errors,
            ineligible_finding_ids=sorted(ineligible_finding_ids),
        )
    if traceability_errors:
        return _fail(
            STATUS_TRACEABILITY_MISMATCH,
            errors + traceability_errors,
            traceability_errors=traceability_errors,
        )
    if priority_errors:
        return _fail(STATUS_PRIORITY_INVALID, errors + priority_errors, priority_errors=priority_errors)
    if criteria_errors:
        return _fail(
            STATUS_ACCEPTANCE_CRITERIA_INVALID,
            errors + criteria_errors,
            acceptance_criteria_errors=criteria_errors,
        )
    if implementation_errors:
        return _fail(
            STATUS_PROHIBITED_IMPLEMENTATION_DETAIL,
            errors + implementation_errors,
            implementation_detail_errors=implementation_errors,
            implementation_detail_warnings=implementation_warnings,
        )
    if errors:
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, errors)
    warnings.extend(implementation_warnings)
    return RequirementValidationResult(
        status=STATUS_SUCCESS,
        passed=True,
        errors=[],
        warnings=warnings,
        requirements=requirements,
        implementation_detail_warnings=implementation_warnings,
    )


SEVERE_IMPLEMENTATION_TERMS = {
    "react",
    "vue",
    "angular",
    "postgresql",
    "redis",
    "rest api",
    "graphql",
    "database",
    "database schema",
    "sql",
    "class",
    "function",
    "component",
    "api",
    "endpoint",
    ".py",
    ".js",
    ".tsx",
    "code file",
}

WARNING_IMPLEMENTATION_TERMS = {
    "modal",
    "screen",
    "service",
}


GENERIC_CRITERIA = {
    "功能正常",
    "前端页面做好",
    "works",
    "works correctly",
    "make it work",
    "feature works",
}


def _is_bad_acceptance_criterion(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in GENERIC_CRITERIA:
        return True
    if len(normalized) < 8:
        return True
    return False


def _fail(
    status: str,
    errors: list[str],
    *,
    unknown_finding_ids: list[str] | None = None,
    ineligible_finding_ids: list[str] | None = None,
    traceability_errors: list[str] | None = None,
    acceptance_criteria_errors: list[str] | None = None,
    implementation_detail_errors: list[str] | None = None,
    implementation_detail_warnings: list[str] | None = None,
    priority_errors: list[str] | None = None,
) -> RequirementValidationResult:
    return RequirementValidationResult(
        status=status,
        passed=False,
        errors=errors,
        unknown_finding_ids=unknown_finding_ids or [],
        ineligible_finding_ids=ineligible_finding_ids or [],
        traceability_errors=traceability_errors or [],
        acceptance_criteria_errors=acceptance_criteria_errors or [],
        implementation_detail_errors=implementation_detail_errors or [],
        implementation_detail_warnings=implementation_detail_warnings or [],
        priority_errors=priority_errors or [],
    )


def _normalize_id_list(value: Any, field_name: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{field_name}: must contain at least one id")
        return []
    normalized = [_text(item) for item in value]
    for item in normalized:
        if not item:
            errors.append(f"{field_name}: empty id")
    return normalized


def _optional_id_list(value: Any, field_name: str, errors: list[str]) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        errors.append(f"{field_name}: must be a list")
        return []
    normalized = [_text(item) for item in value]
    for item in normalized:
        if not item:
            errors.append(f"{field_name}: empty id")
    return normalized


def _normalize_text_list(value: Any, field_name: str, errors: list[str], *, min_items: int) -> list[str]:
    if not isinstance(value, list) or len(value) < min_items:
        errors.append(f"{field_name}: must contain at least {min_items} item(s)")
        return []
    normalized = [_text(item) for item in value]
    for item in normalized:
        if not item:
            errors.append(f"{field_name}: empty item")
    return normalized


def _list_text(value: Any) -> list[str]:
    return [_text(item) for item in value] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _text_allow_empty(value: Any) -> str | None:
    return value if isinstance(value, str) else None
