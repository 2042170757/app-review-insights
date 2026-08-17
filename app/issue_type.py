"""Deterministic issue type classification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.issue_schema import (
    ISSUE_TYPE_MIXED,
    ISSUE_TYPE_NEUTRAL_OBSERVATION,
    ISSUE_TYPE_POSITIVE_FEEDBACK,
    ISSUE_TYPE_PROBLEM,
    VALID_ISSUE_TYPES,
)


@dataclass(frozen=True)
class IssueClassification:
    issue_id: str
    issue_type: str
    classification_reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def validate_issue_type(issue_type: str) -> bool:
    return issue_type in VALID_ISSUE_TYPES


def classify_issue(issue: dict[str, Any]) -> IssueClassification:
    issue_id = _text(issue.get("issue_id"))
    if not issue_id:
        raise ValueError("Unknown issue_id: issue_id is required")

    text = " ".join(
        [
            _text(issue.get("name")),
            _text(issue.get("description")),
            _text(issue.get("merge_rationale")),
            _text(issue.get("uncertainty")),
        ]
    ).lower()

    if _contains_any(text, POSITIVE_SIGNALS) and not _contains_any(text, PROBLEM_SIGNALS):
        return IssueClassification(
            issue_id=issue_id,
            issue_type=ISSUE_TYPE_POSITIVE_FEEDBACK,
            classification_reason="Issue language is primarily positive feedback and does not describe a user problem.",
        )
    if _contains_any(text, POSITIVE_SIGNALS) and _contains_any(text, PROBLEM_SIGNALS):
        return IssueClassification(
            issue_id=issue_id,
            issue_type=ISSUE_TYPE_MIXED,
            classification_reason="Issue language contains both positive experience signals and problem/friction signals.",
        )
    if _contains_any(text, NEUTRAL_SIGNALS) and not _contains_any(text, PROBLEM_SIGNALS):
        return IssueClassification(
            issue_id=issue_id,
            issue_type=ISSUE_TYPE_NEUTRAL_OBSERVATION,
            classification_reason="Issue language is descriptive or observational without clear user friction.",
        )
    return IssueClassification(
        issue_id=issue_id,
        issue_type=ISSUE_TYPE_PROBLEM,
        classification_reason="Issue language describes user friction, pain, failure, or dissatisfaction.",
    )


def classify_issues(issues: list[dict[str, Any]]) -> list[IssueClassification]:
    return [classify_issue(issue) for issue in issues]


POSITIVE_SIGNALS = {
    "positive feedback",
    "positive workout experience",
    "positive experience",
    "love",
    "liked",
    "enjoy",
    "enjoyed",
    "effective",
    "effectiveness",
    "motivation",
    "motivating",
    "great",
    "amazing",
    "satisfied",
}

PROBLEM_SIGNALS = {
    "problem",
    "frustration",
    "frustrating",
    "poor",
    "decline",
    "declining",
    "crash",
    "billing",
    "subscription",
    "paywall",
    "hidden charges",
    "ads",
    "redirects",
    "cannot",
    "unable",
    "difficulty",
    "misleading",
    "unrealistic",
    "outdated",
    "support",
    "account access",
    "injury",
    "not respecting",
    "lacking",
}

NEUTRAL_SIGNALS = {
    "observation",
    "describes",
    "mentions",
    "reports",
}


def _contains_any(text: str, signals: set[str]) -> bool:
    return any(signal in text for signal in signals)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
