"""Deterministic schema and evidence validation for consolidated issues."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from app.issue_schema import Issue


STATUS_SUCCESS = "Success"
STATUS_INVALID_JSON = "Invalid JSON"
STATUS_SCHEMA_VALIDATION_FAILED = "Schema Validation Failed"
STATUS_UNKNOWN_TOPIC_ID = "Unknown Topic ID"
STATUS_UNKNOWN_REVIEW_ID = "Unknown Review ID"
STATUS_EVIDENCE_MISMATCH = "Evidence Mismatch"
STATUS_EMPTY_ISSUES = "Empty Issues"


@dataclass
class IssueValidationResult:
    status: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    unmerged_topic_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [asdict(issue) for issue in self.issues]
        return payload


def validate_issue_output(
    raw_text: str,
    *,
    valid_topic_ids: set[str],
    valid_review_ids: set[str],
    topic_review_ids: dict[str, set[str]],
) -> IssueValidationResult:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return IssueValidationResult(
            status=STATUS_INVALID_JSON,
            passed=False,
            errors=[f"Invalid JSON: {exc.msg}"],
        )
    return validate_issue_payload(
        payload,
        valid_topic_ids=valid_topic_ids,
        valid_review_ids=valid_review_ids,
        topic_review_ids=topic_review_ids,
    )


def validate_issue_payload(
    payload: Any,
    *,
    valid_topic_ids: set[str],
    valid_review_ids: set[str],
    topic_review_ids: dict[str, set[str]],
) -> IssueValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    issues: list[Issue] = []

    if not isinstance(payload, dict):
        return IssueValidationResult(
            status=STATUS_SCHEMA_VALIDATION_FAILED,
            passed=False,
            errors=["schema: root must be an object"],
        )

    raw_issues = payload.get("issues")
    raw_unmerged_topic_ids = payload.get("unmerged_topic_ids")
    unknown_topic_errors: list[str] = []
    if raw_issues is None:
        return IssueValidationResult(
            status=STATUS_SCHEMA_VALIDATION_FAILED,
            passed=False,
            errors=["schema: missing issues"],
        )
    if raw_unmerged_topic_ids is None:
        return IssueValidationResult(
            status=STATUS_SCHEMA_VALIDATION_FAILED,
            passed=False,
            errors=["schema: missing unmerged_topic_ids"],
        )
    if not isinstance(raw_issues, list):
        return IssueValidationResult(
            status=STATUS_SCHEMA_VALIDATION_FAILED,
            passed=False,
            errors=["schema: issues must be a list"],
        )
    if not isinstance(raw_unmerged_topic_ids, list):
        return IssueValidationResult(
            status=STATUS_SCHEMA_VALIDATION_FAILED,
            passed=False,
            errors=["schema: unmerged_topic_ids must be a list"],
        )

    normalized_unmerged_topic_ids = [_text(item) for item in raw_unmerged_topic_ids]
    for topic_id in normalized_unmerged_topic_ids:
        if not topic_id:
            errors.append("unmerged_topic_ids: empty topic id")
        elif topic_id not in valid_topic_ids:
            unknown_topic_errors.append(f"unmerged_topic_ids: unknown topic id {topic_id}")

    if unknown_topic_errors and not raw_issues:
        return IssueValidationResult(
            status=STATUS_UNKNOWN_TOPIC_ID,
            passed=False,
            errors=errors + unknown_topic_errors,
            warnings=warnings,
            issues=[],
            unmerged_topic_ids=[],
        )

    if not raw_issues and not errors:
        return IssueValidationResult(
            status=STATUS_EMPTY_ISSUES,
            passed=True,
            warnings=["empty_issues"],
            issues=[],
            unmerged_topic_ids=normalized_unmerged_topic_ids,
        )

    seen_issue_ids: set[str] = set()
    unknown_review_errors: list[str] = []
    evidence_mismatch_errors: list[str] = []
    for index, raw_issue in enumerate(raw_issues):
        issue_prefix = f"issues[{index}]"
        if not isinstance(raw_issue, dict):
            errors.append(f"{issue_prefix}: must be an object")
            continue

        issue_id = _text(raw_issue.get("issue_id"))
        name = _text(raw_issue.get("name"))
        description = _text(raw_issue.get("description"))
        merge_rationale = _text(raw_issue.get("merge_rationale"))
        uncertainty = _text_allow_empty(raw_issue.get("uncertainty"))
        topic_ids = raw_issue.get("topic_ids")
        review_ids = raw_issue.get("review_ids")
        confidence = raw_issue.get("confidence")

        if not issue_id:
            errors.append(f"{issue_prefix}.issue_id: required")
        elif issue_id in seen_issue_ids:
            errors.append(f"{issue_prefix}.issue_id: duplicate {issue_id}")
        else:
            seen_issue_ids.add(issue_id)

        if not name:
            errors.append(f"{issue_prefix}.name: required")
        if not description:
            errors.append(f"{issue_prefix}.description: required")
        if not merge_rationale:
            errors.append(f"{issue_prefix}.merge_rationale: required")
        if uncertainty is None:
            errors.append(f"{issue_prefix}.uncertainty: required")

        normalized_topic_ids = _normalize_id_list(topic_ids, f"{issue_prefix}.topic_ids", errors)
        normalized_review_ids = _normalize_id_list(review_ids, f"{issue_prefix}.review_ids", errors)

        for topic_id in normalized_topic_ids:
            if topic_id not in valid_topic_ids:
                unknown_topic_errors.append(f"{issue_prefix}.topic_ids: unknown topic id {topic_id}")
        for review_id in normalized_review_ids:
            if review_id not in valid_review_ids:
                unknown_review_errors.append(f"{issue_prefix}.review_ids: unknown review id {review_id}")

        if normalized_topic_ids and normalized_review_ids:
            evidence_ids: set[str] = set()
            for topic_id in normalized_topic_ids:
                evidence_ids.update(topic_review_ids.get(topic_id, set()))
            if valid_topic_ids.issuperset(normalized_topic_ids) and not evidence_ids.intersection(normalized_review_ids):
                evidence_mismatch_errors.append(
                    f"{issue_prefix}: review_ids have no overlap with referenced topic evidence"
                )

        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            errors.append(f"{issue_prefix}.confidence: must be a number from 0 to 1")
            normalized_confidence = 0.0
        else:
            normalized_confidence = float(confidence)
            if normalized_confidence < 0 or normalized_confidence > 1:
                errors.append(f"{issue_prefix}.confidence: out of range {normalized_confidence}")

        if (
            issue_id
            and name
            and description
            and normalized_topic_ids
            and normalized_review_ids
            and merge_rationale
            and uncertainty is not None
            and isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
        ):
            issues.append(
                Issue(
                    issue_id=issue_id,
                    name=name,
                    description=description,
                    topic_ids=normalized_topic_ids,
                    review_ids=normalized_review_ids,
                    merge_rationale=merge_rationale,
                    confidence=normalized_confidence,
                    uncertainty=uncertainty,
                )
            )

    if unknown_topic_errors:
        return IssueValidationResult(
            status=STATUS_UNKNOWN_TOPIC_ID,
            passed=False,
            errors=errors + unknown_topic_errors,
            warnings=warnings,
            issues=[],
            unmerged_topic_ids=[],
        )
    if unknown_review_errors:
        return IssueValidationResult(
            status=STATUS_UNKNOWN_REVIEW_ID,
            passed=False,
            errors=errors + unknown_review_errors,
            warnings=warnings,
            issues=[],
            unmerged_topic_ids=[],
        )
    if evidence_mismatch_errors:
        return IssueValidationResult(
            status=STATUS_EVIDENCE_MISMATCH,
            passed=False,
            errors=errors + evidence_mismatch_errors,
            warnings=warnings,
            issues=[],
            unmerged_topic_ids=[],
        )
    if errors:
        return IssueValidationResult(
            status=STATUS_SCHEMA_VALIDATION_FAILED,
            passed=False,
            errors=errors,
            warnings=warnings,
            issues=[],
            unmerged_topic_ids=[],
        )
    return IssueValidationResult(
        status=STATUS_SUCCESS,
        passed=True,
        errors=[],
        warnings=warnings,
        issues=issues,
        unmerged_topic_ids=normalized_unmerged_topic_ids,
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


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _text_allow_empty(value: Any) -> str | None:
    return value if isinstance(value, str) else None
