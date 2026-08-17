"""Runtime vs submission validation state for workflow runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALIDATION_PENDING = "pending"
VALIDATION_PASS = "pass"
VALIDATION_FAIL = "fail"
VALIDATION_SKIPPED = "skipped"

PASS_VALUE = "PASS"
RUNTIME_STATUS_FIELDS = (
    "forward_traceability",
    "backward_traceability",
    "artifact_consistency",
    "evidence_traceability",
    "statistics_model_separation",
    "failure_state_audit",
    "uncertainty_conflict_audit",
    "ai_deterministic_boundary",
    "generalization",
    "downstream_safety",
)


@dataclass(frozen=True)
class WorkflowValidationSplit:
    runtime_validation_status: str
    submission_validation_status: str
    runtime_errors: list[str] = field(default_factory=list)
    submission_blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def split_final_validation_report(report: dict[str, Any]) -> WorkflowValidationSplit:
    """Separate backend runtime validity from final project submission readiness."""
    runtime_errors = []
    for field_name in RUNTIME_STATUS_FIELDS:
        if report.get(field_name) != PASS_VALUE:
            runtime_errors.append(f"{field_name}: {report.get(field_name)}")
    runtime_errors.extend(_text_list(report.get("critical_issues")))
    runtime_status = VALIDATION_PASS if not runtime_errors else VALIDATION_FAIL

    submission_blockers = _text_list(report.get("missing_final_deliverables"))
    submission_status = VALIDATION_PENDING if submission_blockers else VALIDATION_PASS
    warnings = []
    if runtime_status == VALIDATION_PASS and submission_status == VALIDATION_PENDING:
        warnings.append("Backend analysis pipeline completed, but final submission requirements are not yet complete.")

    return WorkflowValidationSplit(
        runtime_validation_status=runtime_status,
        submission_validation_status=submission_status,
        runtime_errors=runtime_errors,
        submission_blockers=submission_blockers,
        warnings=warnings,
    )


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
