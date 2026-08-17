"""Deterministic evidence calculations for Findings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


EVIDENCE_LOW = "Low"
EVIDENCE_MEDIUM = "Medium"
EVIDENCE_HIGH = "High"
EVIDENCE_INVALID = "Invalid"


@dataclass(frozen=True)
class EvidenceReport:
    finding_id: str
    support_count: int
    unique_support_count: int
    conflicting_count: int
    evidence_strength: str
    evidence_limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_evidence_report(finding: dict[str, Any]) -> EvidenceReport:
    review_ids = [_text(item) for item in finding.get("review_ids", []) if _text(item)]
    conflicting_review_ids = [
        _text(item) for item in finding.get("conflicting_review_ids", []) if _text(item)
    ]
    unique_support_count = len(set(review_ids))
    conflicting_count = len(set(conflicting_review_ids))
    evidence_strength = classify_evidence_strength(unique_support_count)
    limitations = build_evidence_limitations(unique_support_count, conflicting_count)
    return EvidenceReport(
        finding_id=_text(finding.get("finding_id")),
        support_count=unique_support_count,
        unique_support_count=unique_support_count,
        conflicting_count=conflicting_count,
        evidence_strength=evidence_strength,
        evidence_limitations=limitations,
    )


def calculate_evidence_reports(findings: list[dict[str, Any]]) -> list[EvidenceReport]:
    return [calculate_evidence_report(finding) for finding in findings]


def classify_evidence_strength(unique_support_count: int) -> str:
    if unique_support_count <= 0:
        return EVIDENCE_INVALID
    if unique_support_count == 1:
        return EVIDENCE_LOW
    if unique_support_count <= 3:
        return EVIDENCE_MEDIUM
    return EVIDENCE_HIGH


def build_evidence_limitations(unique_support_count: int, conflicting_count: int) -> list[str]:
    limitations: list[str] = []
    if unique_support_count <= 0:
        limitations.append("no supporting reviews")
    elif unique_support_count == 1:
        limitations.append("only one supporting review")
    elif unique_support_count <= 3:
        limitations.append("limited sample size")
    if conflicting_count > 0:
        limitations.append("conflicting reviews exist")
    if not limitations:
        limitations.append("deterministic evidence strength based on support count only")
    return limitations


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
