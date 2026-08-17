"""Deterministic finding eligibility gate for classified issues."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.analysis_intent import (
    ANALYSIS_FOCUS_MIXED,
    ANALYSIS_FOCUS_POSITIVE_FEEDBACK,
    ANALYSIS_FOCUS_PROBLEM,
    DEFAULT_ANALYSIS_FOCUS,
    normalize_analysis_focus,
)
from app.issue_schema import (
    ISSUE_TYPE_MIXED,
    ISSUE_TYPE_NEUTRAL_OBSERVATION,
    ISSUE_TYPE_POSITIVE_FEEDBACK,
    ISSUE_TYPE_PROBLEM,
    VALID_ISSUE_TYPES,
)


FINDING_TYPE_PRODUCT_PROBLEM = "product_problem"
FINDING_TYPE_POSITIVE_FEEDBACK = "positive_feedback"
FINDING_TYPE_NEUTRAL_OBSERVATION = "neutral_observation"

VALID_FINDING_TYPES = {
    FINDING_TYPE_PRODUCT_PROBLEM,
    FINDING_TYPE_POSITIVE_FEEDBACK,
    FINDING_TYPE_NEUTRAL_OBSERVATION,
}


@dataclass(frozen=True)
class FindingEligibility:
    issue_id: str
    issue_type: str
    eligible_for_finding: bool
    reason: str
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS
    finding_type: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_finding_eligibility(
    issue_id: str,
    issue_type: str,
    *,
    analysis_focus: str | None = DEFAULT_ANALYSIS_FOCUS,
) -> FindingEligibility:
    if issue_type not in VALID_ISSUE_TYPES:
        raise ValueError(f"Invalid issue_type: {issue_type}")
    focus = normalize_analysis_focus(analysis_focus)
    if focus == ANALYSIS_FOCUS_PROBLEM:
        return _problem_focus_eligibility(issue_id, issue_type, focus)
    if focus == ANALYSIS_FOCUS_POSITIVE_FEEDBACK:
        return _positive_focus_eligibility(issue_id, issue_type, focus)
    if focus == ANALYSIS_FOCUS_MIXED:
        return _mixed_focus_eligibility(issue_id, issue_type, focus)
    raise ValueError(f"Unhandled analysis_focus: {focus}")


def _problem_focus_eligibility(issue_id: str, issue_type: str, focus: str) -> FindingEligibility:
    if issue_type == ISSUE_TYPE_PROBLEM:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=True,
            reason="Problem issues are eligible for downstream Finding generation.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_PRODUCT_PROBLEM,
        )
    if issue_type == ISSUE_TYPE_MIXED:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=True,
            reason="Mixed issues are eligible, but downstream Finding must use only the problem portion.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_PRODUCT_PROBLEM,
        )
    if issue_type == ISSUE_TYPE_POSITIVE_FEEDBACK:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=False,
            reason="Positive feedback is retained but is not a product problem Finding candidate.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_POSITIVE_FEEDBACK,
        )
    if issue_type == ISSUE_TYPE_NEUTRAL_OBSERVATION:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=False,
            reason="Neutral observations are retained but are not product problem Finding candidates.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_NEUTRAL_OBSERVATION,
        )
    raise ValueError(f"Unhandled issue_type: {issue_type}")


def _positive_focus_eligibility(issue_id: str, issue_type: str, focus: str) -> FindingEligibility:
    if issue_type == ISSUE_TYPE_POSITIVE_FEEDBACK:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=True,
            reason="Positive feedback is eligible for Positive Finding generation under positive feedback analysis.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_POSITIVE_FEEDBACK,
        )
    if issue_type == ISSUE_TYPE_MIXED:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=True,
            reason="Mixed issues are eligible, but downstream Finding must preserve the positive feedback portion.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_POSITIVE_FEEDBACK,
        )
    if issue_type == ISSUE_TYPE_PROBLEM:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=False,
            reason="Problem issues are retained but are outside positive feedback analysis scope.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_PRODUCT_PROBLEM,
        )
    if issue_type == ISSUE_TYPE_NEUTRAL_OBSERVATION:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=False,
            reason="Neutral observations are retained but are not positive feedback Finding candidates.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_NEUTRAL_OBSERVATION,
        )
    raise ValueError(f"Unhandled issue_type: {issue_type}")


def _mixed_focus_eligibility(issue_id: str, issue_type: str, focus: str) -> FindingEligibility:
    if issue_type == ISSUE_TYPE_PROBLEM:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=True,
            reason="Problem issues are eligible under mixed analysis.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_PRODUCT_PROBLEM,
        )
    if issue_type == ISSUE_TYPE_MIXED:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=True,
            reason="Mixed issues are eligible and downstream Findings must preserve problem or positive type.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_PRODUCT_PROBLEM,
        )
    if issue_type == ISSUE_TYPE_POSITIVE_FEEDBACK:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=True,
            reason="Positive feedback is eligible for Positive Finding generation under mixed analysis.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_POSITIVE_FEEDBACK,
        )
    if issue_type == ISSUE_TYPE_NEUTRAL_OBSERVATION:
        return FindingEligibility(
            issue_id=issue_id,
            issue_type=issue_type,
            eligible_for_finding=False,
            reason="Neutral observations are retained but are not Finding candidates.",
            analysis_focus=focus,
            finding_type=FINDING_TYPE_NEUTRAL_OBSERVATION,
        )
    raise ValueError(f"Unhandled issue_type: {issue_type}")


def evaluate_finding_eligibilities(
    classifications: list[dict[str, str]],
    *,
    analysis_focus: str | None = DEFAULT_ANALYSIS_FOCUS,
) -> list[FindingEligibility]:
    return [
        evaluate_finding_eligibility(item["issue_id"], item["issue_type"], analysis_focus=analysis_focus)
        for item in classifications
    ]
