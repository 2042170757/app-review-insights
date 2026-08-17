"""Deterministic schema, eligibility, and evidence validation for Findings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from app.evidence_engine import EvidenceReport, calculate_evidence_report
from app.finding_schema import Finding


STATUS_SUCCESS = "Success"
STATUS_EMPTY_FINDINGS = "Empty Findings"
STATUS_INVALID_JSON = "Invalid JSON"
STATUS_SCHEMA_VALIDATION_FAILED = "Schema Validation Failed"
STATUS_UNKNOWN_ISSUE_ID = "Unknown Issue ID"
STATUS_UNKNOWN_REVIEW_ID = "Unknown Review ID"
STATUS_INELIGIBLE_ISSUE = "Ineligible Issue"
STATUS_EVIDENCE_MISMATCH = "Evidence Mismatch"
STATUS_SUPPORT_COUNT_MISMATCH = "Support Count Mismatch"
STATUS_CONFLICTING_EVIDENCE_INVALID = "Conflicting Evidence Invalid"


@dataclass
class FindingValidationResult:
    status: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    evidence_reports: list[EvidenceReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["findings"] = [asdict(finding) for finding in self.findings]
        payload["evidence_reports"] = [report.to_dict() for report in self.evidence_reports]
        return payload


def validate_finding_output(
    raw_text: str,
    *,
    issues_by_id: dict[str, dict[str, Any]],
    valid_review_ids: set[str],
    eligible_issue_ids: set[str],
) -> FindingValidationResult:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return FindingValidationResult(
            status=STATUS_INVALID_JSON,
            passed=False,
            errors=[f"Invalid JSON: {exc.msg}"],
        )
    return validate_finding_payload(
        payload,
        issues_by_id=issues_by_id,
        valid_review_ids=valid_review_ids,
        eligible_issue_ids=eligible_issue_ids,
    )


def validate_finding_payload(
    payload: Any,
    *,
    issues_by_id: dict[str, dict[str, Any]],
    valid_review_ids: set[str],
    eligible_issue_ids: set[str],
) -> FindingValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    findings: list[Finding] = []
    evidence_reports: list[EvidenceReport] = []

    if not isinstance(payload, dict):
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: root must be an object"])
    raw_findings = payload.get("findings")
    if raw_findings is None:
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: missing findings"])
    if not isinstance(raw_findings, list):
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: findings must be a list"])
    if not raw_findings:
        return FindingValidationResult(
            status=STATUS_EMPTY_FINDINGS,
            passed=True,
            warnings=["empty_findings"],
        )

    seen_finding_ids: set[str] = set()
    unknown_issue_errors: list[str] = []
    unknown_review_errors: list[str] = []
    ineligible_issue_errors: list[str] = []
    evidence_mismatch_errors: list[str] = []
    support_count_errors: list[str] = []
    conflicting_errors: list[str] = []

    for index, raw_finding in enumerate(raw_findings):
        prefix = f"findings[{index}]"
        if not isinstance(raw_finding, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        finding_id = _text(raw_finding.get("finding_id"))
        issue_ids = _normalize_id_list(raw_finding.get("issue_ids"), f"{prefix}.issue_ids", errors)
        review_ids = _normalize_id_list(raw_finding.get("review_ids"), f"{prefix}.review_ids", errors)
        title = _text(raw_finding.get("title"))
        statement = _text(raw_finding.get("statement"))
        evidence_summary = _text(raw_finding.get("evidence_summary"))
        uncertainty = _text_allow_empty(raw_finding.get("uncertainty"))
        support_count = raw_finding.get("support_count")
        confidence = raw_finding.get("confidence")
        conflicting_review_ids = _normalize_conflicting_review_ids(
            raw_finding.get("conflicting_review_ids"),
            f"{prefix}.conflicting_review_ids",
            errors,
        )

        if not finding_id:
            errors.append(f"{prefix}.finding_id: required")
        elif finding_id in seen_finding_ids:
            errors.append(f"{prefix}.finding_id: duplicate {finding_id}")
        else:
            seen_finding_ids.add(finding_id)
        if not title:
            errors.append(f"{prefix}.title: required")
        if not statement:
            errors.append(f"{prefix}.statement: required")
        if not evidence_summary:
            errors.append(f"{prefix}.evidence_summary: required")
        if uncertainty is None:
            errors.append(f"{prefix}.uncertainty: required")
        if not isinstance(support_count, int) or isinstance(support_count, bool) or support_count < 1:
            errors.append(f"{prefix}.support_count: must be an integer >= 1")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            errors.append(f"{prefix}.confidence: must be a number from 0 to 1")
            normalized_confidence = 0.0
        else:
            normalized_confidence = float(confidence)
            if normalized_confidence < 0 or normalized_confidence > 1:
                errors.append(f"{prefix}.confidence: out of range {normalized_confidence}")

        issue_evidence_review_ids: set[str] = set()
        for issue_id in issue_ids:
            issue = issues_by_id.get(issue_id)
            if not issue:
                unknown_issue_errors.append(f"{prefix}.issue_ids: unknown issue id {issue_id}")
                continue
            if issue_id not in eligible_issue_ids:
                ineligible_issue_errors.append(f"{prefix}.issue_ids: ineligible issue id {issue_id}")
            issue_evidence_review_ids.update(_list_text(issue.get("review_ids")))

        for review_id in review_ids:
            if review_id not in valid_review_ids:
                unknown_review_errors.append(f"{prefix}.review_ids: unknown review id {review_id}")
        if review_ids and issue_evidence_review_ids and not set(review_ids).intersection(issue_evidence_review_ids):
            evidence_mismatch_errors.append(
                f"{prefix}: review_ids have no overlap with referenced issue evidence"
            )

        if len(conflicting_review_ids) != len(set(conflicting_review_ids)):
            conflicting_errors.append(f"{prefix}.conflicting_review_ids: duplicate review id")
        for review_id in conflicting_review_ids:
            if review_id not in valid_review_ids:
                conflicting_errors.append(f"{prefix}.conflicting_review_ids: unknown review id {review_id}")
            elif issue_evidence_review_ids and review_id not in issue_evidence_review_ids:
                conflicting_errors.append(
                    f"{prefix}.conflicting_review_ids: review id {review_id} is outside referenced issue evidence"
                )
        if set(conflicting_review_ids).intersection(set(review_ids)):
            conflicting_errors.append(f"{prefix}.conflicting_review_ids: conflicts overlap support review_ids")

        evidence_report = calculate_evidence_report(raw_finding)
        if isinstance(support_count, int) and not isinstance(support_count, bool):
            if support_count != evidence_report.support_count:
                support_count_errors.append(
                    f"{prefix}.support_count: expected {evidence_report.support_count}, got {support_count}"
                )

        if (
            finding_id
            and issue_ids
            and review_ids
            and title
            and statement
            and evidence_summary
            and uncertainty is not None
            and isinstance(support_count, int)
            and not isinstance(support_count, bool)
            and support_count >= 1
            and isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and isinstance(raw_finding.get("conflicting_review_ids"), list)
        ):
            findings.append(
                Finding(
                    finding_id=finding_id,
                    issue_ids=issue_ids,
                    review_ids=review_ids,
                    title=title,
                    statement=statement,
                    evidence_summary=evidence_summary,
                    support_count=support_count,
                    confidence=normalized_confidence,
                    uncertainty=uncertainty,
                    conflicting_review_ids=conflicting_review_ids,
                )
            )
            evidence_reports.append(evidence_report)

    if unknown_issue_errors:
        return _fail(STATUS_UNKNOWN_ISSUE_ID, errors + unknown_issue_errors)
    if unknown_review_errors:
        return _fail(STATUS_UNKNOWN_REVIEW_ID, errors + unknown_review_errors)
    if ineligible_issue_errors:
        return _fail(STATUS_INELIGIBLE_ISSUE, errors + ineligible_issue_errors)
    if evidence_mismatch_errors:
        return _fail(STATUS_EVIDENCE_MISMATCH, errors + evidence_mismatch_errors)
    if support_count_errors:
        return _fail(STATUS_SUPPORT_COUNT_MISMATCH, errors + support_count_errors)
    if conflicting_errors:
        return _fail(STATUS_CONFLICTING_EVIDENCE_INVALID, errors + conflicting_errors)
    if errors:
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, errors)
    return FindingValidationResult(
        status=STATUS_SUCCESS,
        passed=True,
        errors=[],
        warnings=warnings,
        findings=findings,
        evidence_reports=evidence_reports,
    )


def _fail(status: str, errors: list[str]) -> FindingValidationResult:
    return FindingValidationResult(status=status, passed=False, errors=errors)


def _normalize_id_list(value: Any, field_name: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{field_name}: must contain at least one id")
        return []
    normalized = [_text(item) for item in value]
    for item in normalized:
        if not item:
            errors.append(f"{field_name}: empty id")
    return normalized


def _normalize_conflicting_review_ids(value: Any, field_name: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{field_name}: must be a list")
        return []
    normalized = [_text(item) for item in value]
    for item in normalized:
        if not item:
            errors.append(f"{field_name}: empty review id")
    return normalized


def _list_text(value: Any) -> list[str]:
    return [_text(item) for item in value] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _text_allow_empty(value: Any) -> str | None:
    return value if isinstance(value, str) else None
