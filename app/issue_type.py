"""Deterministic issue type classification."""

from __future__ import annotations

import re
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

    problem_text = _remove_negated_problem_context(text)
    has_positive_signal = _contains_any(text, POSITIVE_SIGNALS)
    has_problem_signal = _contains_any(problem_text, PROBLEM_SIGNALS)
    has_strong_problem_signal = _contains_any(problem_text, STRONG_PROBLEM_SIGNALS)

    if has_strong_problem_signal:
        return IssueClassification(
            issue_id=issue_id,
            issue_type=ISSUE_TYPE_PROBLEM,
            classification_reason="Issue language describes a clear lack, failure, or unmet expected outcome.",
        )
    if has_positive_signal and not has_problem_signal:
        return IssueClassification(
            issue_id=issue_id,
            issue_type=ISSUE_TYPE_POSITIVE_FEEDBACK,
            classification_reason="Issue language is primarily positive feedback and does not describe an unnegated user problem.",
        )
    if has_positive_signal and has_problem_signal:
        return IssueClassification(
            issue_id=issue_id,
            issue_type=ISSUE_TYPE_MIXED,
            classification_reason="Issue language contains both positive experience signals and problem/friction signals.",
        )
    if _contains_any(text, NEUTRAL_SIGNALS) and not has_problem_signal:
        return IssueClassification(
            issue_id=issue_id,
            issue_type=ISSUE_TYPE_NEUTRAL_OBSERVATION,
            classification_reason="Issue language is descriptive or observational without clear user friction.",
        )
    if _contains_negated_problem_context(text) and not has_problem_signal:
        return IssueClassification(
            issue_id=issue_id,
            issue_type=ISSUE_TYPE_NEUTRAL_OBSERVATION,
            classification_reason="Issue language negates problem or complaint context and lacks unnegated user friction.",
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

STRONG_PROBLEM_SIGNALS = {
    "lack of",
    "lacks",
    "not feeling",
    "does not",
    "doesn't",
    "did not",
    "didn't",
    "no result",
    "no results",
    "not effective",
    "failed",
    "failure",
    "gap in",
    "unmet",
}

NEUTRAL_SIGNALS = {
    "observation",
    "describes",
    "mentions",
    "reports",
}


def _contains_any(text: str, signals: set[str]) -> bool:
    return any(signal in text for signal in signals)


def _contains_negated_problem_context(text: str) -> bool:
    return _remove_negated_problem_context(text) != text


def _remove_negated_problem_context(text: str) -> str:
    """Mask small negated-problem spans before keyword checks.

    This keeps the deterministic gate narrow: it handles explicit negation near
    problem nouns without trying to solve full semantic classification.
    """

    normalized = text
    for pattern in NEGATED_PROBLEM_PATTERNS:
        normalized = pattern.sub(" ", normalized)
    return normalized


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


NEGATED_PROBLEM_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bnot\s+(?:a\s+|an\s+|the\s+)?(?:product\s+)?(?:problem|issue|complaint|complaining)\b",
        r"\bno\s+(?:product\s+)?(?:problem|issue|complaint|complaints)\b",
        r"\bwithout\s+(?:a\s+|an\s+|any\s+)?(?:product\s+)?(?:problem|issue|complaint|complaints)\b",
        r"\bnot\s+\w+\s+(?:a\s+|an\s+|the\s+)?(?:product\s+)?(?:problem|issue|complaint|complaining)\b",
    )
)
