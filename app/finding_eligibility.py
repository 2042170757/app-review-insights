"""Deterministic finding eligibility gate for classified issues."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.issue_schema import (
    ISSUE_TYPE_MIXED,
    ISSUE_TYPE_NEUTRAL_OBSERVATION,
    ISSUE_TYPE_POSITIVE_FEEDBACK,
    ISSUE_TYPE_PROBLEM,
    VALID_ISSUE_TYPES,
)


@dataclass(frozen=True)
class FindingEligibility:
    issue_id: str
    issue_type: str
    eligible_for_finding: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_finding_eligibility(issue_id: str, issue_type: str) -> FindingEligibility:
    if issue_type not in VALID_ISSUE_TYPES:
        raise ValueError(f"Invalid issue_type: {issue_type}")
    if issue_type == ISSUE_TYPE_PROBLEM:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=True,
            reason="Problem issues are eligible for downstream Finding generation.",
        )
    if issue_type == ISSUE_TYPE_MIXED:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=True,
            reason="Mixed issues are eligible, but downstream Finding must use only the problem portion.",
        )
    if issue_type == ISSUE_TYPE_POSITIVE_FEEDBACK:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=False,
            reason="Positive feedback is retained but is not a product problem Finding candidate.",
        )
    if issue_type == ISSUE_TYPE_NEUTRAL_OBSERVATION:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=False,
            reason="Neutral observations are retained but are not product problem Finding candidates.",
        )
    raise ValueError(f"Unhandled issue_type: {issue_type}")


def evaluate_finding_eligibilities(classifications: list[dict[str, str]]) -> list[FindingEligibility]:
    return [
        evaluate_finding_eligibility(item["issue_id"], item["issue_type"])
        for item in classifications
    ]
