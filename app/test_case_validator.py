"""Deterministic validation for generated test cases."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from app.requirement_schema import VALID_PRIORITIES
from app.test_case_schema import TestCase, VALID_TEST_TYPES
from app.test_coverage import TestCoverageReport, build_acceptance_criteria_index, calculate_test_coverage


STATUS_SUCCESS = "Success"
STATUS_EMPTY_TEST_CASES = "Empty Test Cases"
STATUS_INVALID_JSON = "Invalid JSON"
STATUS_SCHEMA_VALIDATION_FAILED = "Schema Validation Failed"
STATUS_INPUT_VALIDATION_FAILED = "Input Validation Failed"
STATUS_UNKNOWN_REQUIREMENT_ID = "Unknown Requirement ID"
STATUS_UNKNOWN_ACCEPTANCE_CRITERION_ID = "Unknown Acceptance Criterion ID"
STATUS_ACCEPTANCE_CRITERION_MISMATCH = "Acceptance Criterion Mismatch"
STATUS_DUPLICATE_TEST_CASE_ID = "Duplicate Test Case ID"
STATUS_INVALID_TEST_TYPE = "Invalid Test Type"
STATUS_INVALID_PRIORITY = "Invalid Priority"
STATUS_PRIORITY_MISMATCH = "Priority Mismatch"
STATUS_GENERIC_TEST_CASE = "Generic Test Case"
STATUS_TRACEABILITY_MISMATCH = "Traceability Mismatch"
STATUS_SCOPE_OVERREACH = "Scope Overreach"
STATUS_COVERAGE_INCOMPLETE = "Coverage Incomplete"

GENERIC_PHRASES = {
    "测试功能是否正常",
    "确认用户体验良好",
    "test whether the feature works",
    "verify the feature works",
    "make sure it works",
    "check user experience",
    "confirm good user experience",
}


@dataclass
class TestCaseValidationResult:
    status: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)
    coverage: TestCoverageReport | None = None
    unknown_requirement_ids: list[str] = field(default_factory=list)
    unknown_acceptance_criteria_ids: list[str] = field(default_factory=list)
    acceptance_criteria_mismatches: list[str] = field(default_factory=list)
    duplicate_test_case_ids: list[str] = field(default_factory=list)
    invalid_test_type_errors: list[str] = field(default_factory=list)
    invalid_priority_errors: list[str] = field(default_factory=list)
    priority_mismatches: list[str] = field(default_factory=list)
    generic_test_case_errors: list[str] = field(default_factory=list)
    traceability_errors: list[str] = field(default_factory=list)
    scope_overreach_errors: list[str] = field(default_factory=list)
    duplicate_source_review_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["test_cases"] = [asdict(test_case) for test_case in self.test_cases]
        payload["coverage"] = self.coverage.to_dict() if self.coverage else None
        return payload


def validate_test_case_output(
    raw_text: str,
    *,
    requirements: list[dict[str, Any]],
    requirement_validation_passed: bool,
    prd_validation_passed: bool,
    findings_by_id: dict[str, dict[str, Any]] | None = None,
    valid_review_ids: set[str] | None = None,
    enforce_full_coverage: bool = False,
) -> TestCaseValidationResult:
    if not (requirement_validation_passed and prd_validation_passed):
        return TestCaseValidationResult(
            status=STATUS_INPUT_VALIDATION_FAILED,
            passed=False,
            errors=["Requirement Validation and PRD Validation must both be PASS before Test Case validation."],
            coverage=calculate_test_coverage(requirements=requirements, test_cases=[]),
        )
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return TestCaseValidationResult(
            status=STATUS_INVALID_JSON,
            passed=False,
            errors=[f"Invalid JSON: {exc.msg}"],
            coverage=calculate_test_coverage(requirements=requirements, test_cases=[]),
        )
    return validate_test_case_payload(
        payload,
        requirements=requirements,
        findings_by_id=findings_by_id or {},
        valid_review_ids=valid_review_ids or set(),
        enforce_full_coverage=enforce_full_coverage,
    )


def validate_test_case_payload(
    payload: Any,
    *,
    requirements: list[dict[str, Any]],
    findings_by_id: dict[str, dict[str, Any]] | None = None,
    valid_review_ids: set[str] | None = None,
    enforce_full_coverage: bool = False,
) -> TestCaseValidationResult:
    if not isinstance(payload, dict):
        return _fail(
            STATUS_SCHEMA_VALIDATION_FAILED,
            ["schema: root must be an object"],
            coverage=calculate_test_coverage(requirements=requirements, test_cases=[]),
        )
    raw_test_cases = payload.get("test_cases")
    if raw_test_cases is None:
        return _fail(
            STATUS_SCHEMA_VALIDATION_FAILED,
            ["schema: missing test_cases"],
            coverage=calculate_test_coverage(requirements=requirements, test_cases=[]),
        )
    if not isinstance(raw_test_cases, list):
        return _fail(
            STATUS_SCHEMA_VALIDATION_FAILED,
            ["schema: test_cases must be a list"],
            coverage=calculate_test_coverage(requirements=requirements, test_cases=[]),
        )
    if not raw_test_cases:
        return TestCaseValidationResult(
            status=STATUS_EMPTY_TEST_CASES,
            passed=True,
            warnings=["empty_test_cases"],
            coverage=calculate_test_coverage(requirements=requirements, test_cases=[]),
        )

    requirements_by_id = {
        requirement["requirement_id"]: requirement
        for requirement in requirements
        if isinstance(requirement, dict) and isinstance(requirement.get("requirement_id"), str)
    }
    acceptance_criteria_by_id = build_acceptance_criteria_index(requirements)
    findings_by_id = findings_by_id or {}
    valid_review_ids = valid_review_ids or set()
    errors: list[str] = []
    test_cases: list[TestCase] = []
    seen_test_case_ids: set[str] = set()
    duplicate_test_case_ids: set[str] = set()
    unknown_requirement_ids: set[str] = set()
    unknown_acceptance_criteria_ids: set[str] = set()
    ac_mismatches: list[str] = []
    test_type_errors: list[str] = []
    priority_errors: list[str] = []
    priority_mismatch_errors: list[str] = []
    generic_errors: list[str] = []
    traceability_errors: list[str] = []
    scope_overreach_errors: list[str] = []
    duplicate_source_review_ids: set[str] = set()

    for index, raw_test_case in enumerate(raw_test_cases):
        prefix = f"test_cases[{index}]"
        if not isinstance(raw_test_case, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        test_case_id = _text(raw_test_case.get("test_case_id"))
        requirement_id = _text(raw_test_case.get("requirement_id"))
        acceptance_criteria_ids = _text_list(raw_test_case.get("acceptance_criteria_ids"), f"{prefix}.acceptance_criteria_ids", errors, min_items=1)
        title = _text(raw_test_case.get("title"))
        preconditions = _text_list(raw_test_case.get("preconditions"), f"{prefix}.preconditions", errors, min_items=0)
        steps = _text_list(raw_test_case.get("steps"), f"{prefix}.steps", errors, min_items=1)
        expected_result = _text(raw_test_case.get("expected_result"))
        test_type = _text(raw_test_case.get("test_type"))
        priority = _text(raw_test_case.get("priority"))
        has_source_review_ids = "source_review_ids" in raw_test_case
        source_review_ids = _text_list(raw_test_case.get("source_review_ids"), f"{prefix}.source_review_ids", errors, min_items=0)
        duplicate_source_review_ids.update(_duplicates(source_review_ids))
        source_review_ids = _stable_unique(source_review_ids)

        if not test_case_id:
            errors.append(f"{prefix}.test_case_id: required")
        elif test_case_id in seen_test_case_ids:
            duplicate_test_case_ids.add(test_case_id)
        else:
            seen_test_case_ids.add(test_case_id)
        if not requirement_id:
            errors.append(f"{prefix}.requirement_id: required")
        elif requirement_id not in requirements_by_id:
            unknown_requirement_ids.add(requirement_id)
        if not title:
            errors.append(f"{prefix}.title: required")
        if not expected_result:
            errors.append(f"{prefix}.expected_result: required")
        if test_type not in VALID_TEST_TYPES:
            test_type_errors.append(f"{prefix}.test_type: invalid {test_type!r}")
        if priority not in VALID_PRIORITIES:
            priority_errors.append(f"{prefix}.priority: invalid {priority!r}")
        elif requirement_id in requirements_by_id:
            requirement_priority = _text(requirements_by_id[requirement_id].get("priority"))
            if requirement_priority and priority != requirement_priority:
                priority_mismatch_errors.append(
                    f"{prefix}.priority: {priority} != requirement priority {requirement_priority}"
                )

        referenced_criteria_texts: list[str] = []
        for acceptance_criteria_id in acceptance_criteria_ids:
            acceptance_criterion = acceptance_criteria_by_id.get(acceptance_criteria_id)
            if not acceptance_criterion:
                unknown_acceptance_criteria_ids.add(acceptance_criteria_id)
                continue
            referenced_criteria_texts.append(_text(acceptance_criterion.get("text")))
            if requirement_id and acceptance_criterion["requirement_id"] != requirement_id:
                ac_mismatches.append(
                    f"{prefix}.acceptance_criteria_ids: {acceptance_criteria_id} belongs to {acceptance_criterion['requirement_id']}, not {requirement_id}"
                )

        if _is_generic_test_case(title, steps, expected_result):
            generic_errors.append(f"{prefix}: test case is too generic to execute")
        if requirement_id in requirements_by_id:
            _validate_requirement_traceability(
                prefix=prefix,
                requirement=requirements_by_id[requirement_id],
                findings_by_id=findings_by_id,
                valid_review_ids=valid_review_ids,
                traceability_errors=traceability_errors,
            )
            _validate_source_review_ids(
                prefix=prefix,
                requirement=requirements_by_id[requirement_id],
                source_review_ids=source_review_ids,
                has_source_review_ids=has_source_review_ids,
                findings_by_id=findings_by_id,
                valid_review_ids=valid_review_ids,
                traceability_errors=traceability_errors,
            )
        scope_error = _scope_overreach_error(prefix, title, steps, expected_result, referenced_criteria_texts)
        if scope_error:
            scope_overreach_errors.append(scope_error)

        if (
            test_case_id
            and requirement_id
            and acceptance_criteria_ids
            and title
            and steps
            and expected_result
            and test_type in VALID_TEST_TYPES
            and priority in VALID_PRIORITIES
            and has_source_review_ids
        ):
            test_cases.append(
                TestCase(
                    test_case_id=test_case_id,
                    requirement_id=requirement_id,
                    acceptance_criteria_ids=acceptance_criteria_ids,
                    title=title,
                    preconditions=preconditions,
                    steps=steps,
                    expected_result=expected_result,
                    test_type=test_type,
                    priority=priority,
                    source_review_ids=source_review_ids,
                )
            )

    coverage = calculate_test_coverage(
        requirements=requirements,
        test_cases=[asdict(test_case) for test_case in test_cases],
    )
    if duplicate_test_case_ids:
        return _fail(
            STATUS_DUPLICATE_TEST_CASE_ID,
            [f"duplicate test_case_id {test_case_id}" for test_case_id in sorted(duplicate_test_case_ids)],
            coverage=coverage,
            duplicate_test_case_ids=sorted(duplicate_test_case_ids),
        )
    if unknown_requirement_ids:
        return _fail(
            STATUS_UNKNOWN_REQUIREMENT_ID,
            [f"unknown requirement_id {requirement_id}" for requirement_id in sorted(unknown_requirement_ids)],
            coverage=coverage,
            unknown_requirement_ids=sorted(unknown_requirement_ids),
        )
    if unknown_acceptance_criteria_ids:
        return _fail(
            STATUS_UNKNOWN_ACCEPTANCE_CRITERION_ID,
            [f"unknown acceptance_criteria_id {acceptance_criteria_id}" for acceptance_criteria_id in sorted(unknown_acceptance_criteria_ids)],
            coverage=coverage,
            unknown_acceptance_criteria_ids=sorted(unknown_acceptance_criteria_ids),
        )
    if ac_mismatches:
        return _fail(
            STATUS_ACCEPTANCE_CRITERION_MISMATCH,
            ac_mismatches,
            coverage=coverage,
            acceptance_criteria_mismatches=ac_mismatches,
        )
    if test_type_errors:
        return _fail(STATUS_INVALID_TEST_TYPE, test_type_errors, coverage=coverage, invalid_test_type_errors=test_type_errors)
    if priority_errors:
        return _fail(STATUS_INVALID_PRIORITY, priority_errors, coverage=coverage, invalid_priority_errors=priority_errors)
    if priority_mismatch_errors:
        return _fail(
            STATUS_PRIORITY_MISMATCH,
            priority_mismatch_errors,
            coverage=coverage,
            priority_mismatches=priority_mismatch_errors,
        )
    if generic_errors:
        return _fail(STATUS_GENERIC_TEST_CASE, generic_errors, coverage=coverage, generic_test_case_errors=generic_errors)
    if scope_overreach_errors:
        return _fail(
            STATUS_SCOPE_OVERREACH,
            scope_overreach_errors,
            coverage=coverage,
            scope_overreach_errors=scope_overreach_errors,
        )
    if duplicate_source_review_ids:
        warnings = [f"duplicate source_review_id {review_id} was de-duplicated" for review_id in sorted(duplicate_source_review_ids)]
    else:
        warnings = []
    if traceability_errors:
        result = _fail(
            STATUS_TRACEABILITY_MISMATCH,
            traceability_errors,
            coverage=coverage,
            traceability_errors=traceability_errors,
        )
        result.warnings.extend(warnings)
        result.duplicate_source_review_ids = sorted(duplicate_source_review_ids)
        return result
    if errors:
        result = _fail(STATUS_SCHEMA_VALIDATION_FAILED, errors, coverage=coverage)
        result.warnings.extend(warnings)
        result.duplicate_source_review_ids = sorted(duplicate_source_review_ids)
        return result
    if enforce_full_coverage and (coverage.uncovered_requirement_ids or coverage.uncovered_acceptance_criteria_ids):
        coverage_errors = []
        if coverage.uncovered_requirement_ids:
            coverage_errors.append(f"uncovered requirements: {coverage.uncovered_requirement_ids}")
        if coverage.uncovered_acceptance_criteria_ids:
            coverage_errors.append(f"uncovered acceptance criteria: {coverage.uncovered_acceptance_criteria_ids}")
        return _fail(STATUS_COVERAGE_INCOMPLETE, coverage_errors, coverage=coverage)
    return TestCaseValidationResult(
        status=STATUS_SUCCESS,
        passed=True,
        test_cases=test_cases,
        coverage=coverage,
        warnings=warnings,
        duplicate_source_review_ids=sorted(duplicate_source_review_ids),
    )


def _validate_requirement_traceability(
    *,
    prefix: str,
    requirement: dict[str, Any],
    findings_by_id: dict[str, dict[str, Any]],
    valid_review_ids: set[str],
    traceability_errors: list[str],
) -> None:
    finding_ids = _list_text(requirement.get("finding_ids"))
    if not finding_ids:
        traceability_errors.append(f"{prefix}: requirement has no finding_ids")
        return
    if not findings_by_id:
        return
    for finding_id in finding_ids:
        finding = findings_by_id.get(finding_id)
        if not finding:
            traceability_errors.append(f"{prefix}: unknown finding_id {finding_id}")
            continue
        review_ids = _list_text(finding.get("review_ids"))
        if not review_ids:
            traceability_errors.append(f"{prefix}: finding {finding_id} has no review evidence")
        if valid_review_ids:
            for review_id in review_ids:
                if review_id not in valid_review_ids:
                    traceability_errors.append(f"{prefix}: finding {finding_id} references unknown review_id {review_id}")


def enrich_test_case_source_review_ids(
    payload: Any,
    *,
    requirements: list[dict[str, Any]],
    findings_by_id: dict[str, dict[str, Any]],
) -> Any:
    if not isinstance(payload, dict):
        return payload
    raw_test_cases = payload.get("test_cases")
    if not isinstance(raw_test_cases, list):
        return payload
    requirements_by_id = {
        _text(requirement.get("requirement_id")): requirement
        for requirement in requirements
        if isinstance(requirement, dict) and _text(requirement.get("requirement_id"))
    }
    enriched_test_cases: list[Any] = []
    for raw_test_case in raw_test_cases:
        if not isinstance(raw_test_case, dict):
            enriched_test_cases.append(raw_test_case)
            continue
        requirement = requirements_by_id.get(_text(raw_test_case.get("requirement_id")))
        source_review_ids = (
            source_review_ids_for_requirement(requirement, findings_by_id)
            if requirement
            else []
        )
        enriched_test_cases.append({**raw_test_case, "source_review_ids": source_review_ids})
    return {**payload, "test_cases": enriched_test_cases}


def source_review_ids_for_requirement(
    requirement: dict[str, Any] | None,
    findings_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    if not requirement:
        return []
    source_review_ids: set[str] = set()
    for finding_id in _list_text(requirement.get("finding_ids")):
        finding = findings_by_id.get(finding_id)
        if finding:
            source_review_ids.update(_list_text(finding.get("review_ids")))
    return sorted(source_review_ids)


def _validate_source_review_ids(
    *,
    prefix: str,
    requirement: dict[str, Any],
    source_review_ids: list[str],
    has_source_review_ids: bool,
    findings_by_id: dict[str, dict[str, Any]],
    valid_review_ids: set[str],
    traceability_errors: list[str],
) -> None:
    if not has_source_review_ids:
        traceability_errors.append(f"{prefix}: missing source_review_ids")
        return
    if valid_review_ids:
        for review_id in source_review_ids:
            if review_id not in valid_review_ids:
                traceability_errors.append(f"{prefix}: source_review_ids references unknown review_id {review_id}")
    if not findings_by_id:
        return
    expected_review_ids = set(source_review_ids_for_requirement(requirement, findings_by_id))
    if expected_review_ids and not source_review_ids:
        traceability_errors.append(f"{prefix}: source_review_ids must include review evidence from requirement findings")
        return
    unrelated_review_ids = sorted(set(source_review_ids) - expected_review_ids)
    if unrelated_review_ids:
        traceability_errors.append(
            f"{prefix}: source_review_ids outside requirement finding evidence {unrelated_review_ids}"
        )
    if expected_review_ids and not set(source_review_ids).intersection(expected_review_ids):
        traceability_errors.append(f"{prefix}: source_review_ids do not match requirement finding evidence")


def _fail(
    status: str,
    errors: list[str],
    *,
    coverage: TestCoverageReport,
    unknown_requirement_ids: list[str] | None = None,
    unknown_acceptance_criteria_ids: list[str] | None = None,
    acceptance_criteria_mismatches: list[str] | None = None,
    duplicate_test_case_ids: list[str] | None = None,
    invalid_test_type_errors: list[str] | None = None,
    invalid_priority_errors: list[str] | None = None,
    priority_mismatches: list[str] | None = None,
    generic_test_case_errors: list[str] | None = None,
    traceability_errors: list[str] | None = None,
    scope_overreach_errors: list[str] | None = None,
    duplicate_source_review_ids: list[str] | None = None,
) -> TestCaseValidationResult:
    return TestCaseValidationResult(
        status=status,
        passed=False,
        errors=errors,
        coverage=coverage,
        unknown_requirement_ids=unknown_requirement_ids or [],
        unknown_acceptance_criteria_ids=unknown_acceptance_criteria_ids or [],
        acceptance_criteria_mismatches=acceptance_criteria_mismatches or [],
        duplicate_test_case_ids=duplicate_test_case_ids or [],
        invalid_test_type_errors=invalid_test_type_errors or [],
        invalid_priority_errors=invalid_priority_errors or [],
        priority_mismatches=priority_mismatches or [],
        generic_test_case_errors=generic_test_case_errors or [],
        traceability_errors=traceability_errors or [],
        scope_overreach_errors=scope_overreach_errors or [],
        duplicate_source_review_ids=duplicate_source_review_ids or [],
    )


def _is_generic_test_case(title: str, steps: list[str], expected_result: str) -> bool:
    combined = " ".join([title, *steps, expected_result]).strip().lower()
    if combined in GENERIC_PHRASES:
        return True
    return any(phrase in combined for phrase in GENERIC_PHRASES)


def _scope_overreach_error(prefix: str, title: str, steps: list[str], expected_result: str, criteria_texts: list[str]) -> str | None:
    test_text = " ".join([title, *steps, expected_result]).lower()
    criteria_text = " ".join(criteria_texts).lower()
    overreach_terms = {
        "refund": {"refund", "退款"},
        "coupon": {"coupon", "discount", "promo", "优惠券", "折扣"},
        "payment_failure": {"payment failed", "payment failure", "card declined", "支付失败"},
        "new_plan": {"new membership", "new plan", "loyalty", "会员等级"},
        "technical": {"api", "database", "endpoint", "sql", "react", "vue"},
    }
    for label, terms in overreach_terms.items():
        if any(term in test_text for term in terms) and not any(term in criteria_text for term in terms):
            return f"{prefix}: scope overreach introduces {label}"
    return None


def _text_list(value: Any, field_name: str, errors: list[str], *, min_items: int) -> list[str]:
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


def _stable_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _duplicates(items: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        else:
            seen.add(item)
    return duplicates
