"""Deterministic Requirement priority scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PriorityEngineConfig:
    evidence_scores: dict[str, float]
    support_thresholds: tuple[tuple[int, float], ...]
    confidence_thresholds: tuple[tuple[float, float], ...]
    uncertainty_keywords: tuple[str, ...]
    uncertainty_penalty: float
    conflict_penalty_per_review: float
    conflict_penalty_cap: float
    p0_threshold: float
    p1_threshold: float
    p2_threshold: float


DEFAULT_PRIORITY_CONFIG = PriorityEngineConfig(
    evidence_scores={"High": 3.0, "Medium": 2.0, "Low": 1.0},
    support_thresholds=((10, 3.0), (4, 2.0), (1, 1.0)),
    confidence_thresholds=((0.9, 1.5), (0.75, 1.0), (0.6, 0.5)),
    uncertainty_keywords=("limited", "small sample", "unclear", "unknown", "uncertain", "not implemented"),
    uncertainty_penalty=0.5,
    conflict_penalty_per_review=0.4,
    conflict_penalty_cap=1.2,
    p0_threshold=8.5,
    p1_threshold=5.5,
    p2_threshold=3.0,
)


@dataclass(frozen=True)
class PriorityDecision:
    requirement_id: str
    finding_ids: list[str]
    evidence_score: float
    support_score: float
    confidence_score: float
    uncertainty_penalty: float
    conflict_penalty: float
    final_score: float
    final_priority: str
    rationale: str
    suggested_priority: str | None = None
    suggested_priority_rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assign_requirement_priorities(
    payload: dict[str, Any],
    *,
    findings_by_id: dict[str, dict[str, Any]],
    evidence_reports_by_id: dict[str, dict[str, Any]],
    config: PriorityEngineConfig = DEFAULT_PRIORITY_CONFIG,
) -> tuple[dict[str, Any], list[PriorityDecision]]:
    requirements = payload.get("requirements")
    if not isinstance(requirements, list):
        return payload, []

    normalized_requirements: list[Any] = []
    decisions: list[PriorityDecision] = []
    for raw_requirement in requirements:
        if not isinstance(raw_requirement, dict):
            normalized_requirements.append(raw_requirement)
            continue
        requirement = dict(raw_requirement)
        decision = calculate_requirement_priority(
            requirement,
            findings_by_id=findings_by_id,
            evidence_reports_by_id=evidence_reports_by_id,
            config=config,
        )
        requirement["priority"] = decision.final_priority
        requirement["priority_rationale"] = decision.rationale
        requirement.pop("suggested_priority", None)
        requirement.pop("suggested_priority_rationale", None)
        normalized_requirements.append(requirement)
        decisions.append(decision)

    normalized_payload = dict(payload)
    normalized_payload["requirements"] = normalized_requirements
    return normalized_payload, decisions


def calculate_requirement_priority(
    requirement: dict[str, Any],
    *,
    findings_by_id: dict[str, dict[str, Any]],
    evidence_reports_by_id: dict[str, dict[str, Any]],
    config: PriorityEngineConfig = DEFAULT_PRIORITY_CONFIG,
) -> PriorityDecision:
    requirement_id = _text(requirement.get("requirement_id")) or "UNKNOWN"
    finding_ids = _id_list(requirement.get("finding_ids"))
    findings = [findings_by_id[finding_id] for finding_id in finding_ids if finding_id in findings_by_id]
    evidence_reports = [
        evidence_reports_by_id[finding_id] for finding_id in finding_ids if finding_id in evidence_reports_by_id
    ]

    evidence_score = _max_evidence_score(evidence_reports, config)
    support_count = _max_number(
        [report.get("support_count") for report in evidence_reports]
        + [finding.get("support_count") for finding in findings]
    )
    support_score = _support_score(support_count, config)
    confidence = _average_number(finding.get("confidence") for finding in findings)
    confidence_score = _confidence_score(confidence, config)
    uncertainty_penalty = _uncertainty_penalty(requirement, findings, config)
    conflict_count = _max_number(
        [report.get("conflicting_count") for report in evidence_reports]
        + [len(finding.get("conflicting_review_ids", [])) for finding in findings if isinstance(finding.get("conflicting_review_ids"), list)]
    )
    conflict_penalty = min(config.conflict_penalty_cap, conflict_count * config.conflict_penalty_per_review)
    final_score = max(0.0, evidence_score + support_score + confidence_score - uncertainty_penalty - conflict_penalty)
    final_priority = _priority_from_score(final_score, config)
    rationale = (
        f"Deterministic priority from evidence_strength={_best_evidence_strength(evidence_reports)}, "
        f"support_count={support_count}, average_confidence={confidence:.2f}, "
        f"uncertainty_penalty={uncertainty_penalty:.1f}, conflict_penalty={conflict_penalty:.1f}. "
        "Impact is not independently scored in Phase 4b, so priority remains conservative."
    )
    suggested_priority = _text_or_none(requirement.get("suggested_priority") or requirement.get("priority"))
    suggested_rationale = _text_or_none(requirement.get("suggested_priority_rationale"))
    return PriorityDecision(
        requirement_id=requirement_id,
        finding_ids=finding_ids,
        evidence_score=round(evidence_score, 3),
        support_score=round(support_score, 3),
        confidence_score=round(confidence_score, 3),
        uncertainty_penalty=round(uncertainty_penalty, 3),
        conflict_penalty=round(conflict_penalty, 3),
        final_score=round(final_score, 3),
        final_priority=final_priority,
        rationale=rationale,
        suggested_priority=suggested_priority,
        suggested_priority_rationale=suggested_rationale,
    )


def _max_evidence_score(evidence_reports: list[dict[str, Any]], config: PriorityEngineConfig) -> float:
    if not evidence_reports:
        return 0.0
    return max(config.evidence_scores.get(_text(report.get("evidence_strength")), 0.0) for report in evidence_reports)


def _support_score(support_count: int, config: PriorityEngineConfig) -> float:
    for threshold, score in config.support_thresholds:
        if support_count >= threshold:
            return score
    return 0.0


def _confidence_score(confidence: float, config: PriorityEngineConfig) -> float:
    for threshold, score in config.confidence_thresholds:
        if confidence >= threshold:
            return score
    return 0.0


def _uncertainty_penalty(
    requirement: dict[str, Any],
    findings: list[dict[str, Any]],
    config: PriorityEngineConfig,
) -> float:
    text = " ".join(
        [_text(requirement.get("uncertainty"))]
        + [_text(finding.get("uncertainty")) for finding in findings]
    ).lower()
    return config.uncertainty_penalty if any(keyword in text for keyword in config.uncertainty_keywords) else 0.0


def _priority_from_score(score: float, config: PriorityEngineConfig) -> str:
    if score >= config.p0_threshold:
        return "P0"
    if score >= config.p1_threshold:
        return "P1"
    if score >= config.p2_threshold:
        return "P2"
    return "P3"


def _best_evidence_strength(evidence_reports: list[dict[str, Any]]) -> str:
    if not evidence_reports:
        return "Unknown"
    order = {"High": 3, "Medium": 2, "Low": 1}
    return max((_text(report.get("evidence_strength")) or "Unknown" for report in evidence_reports), key=lambda item: order.get(item, 0))


def _max_number(values: list[Any]) -> int:
    numbers = [int(value) for value in values if isinstance(value, int) and not isinstance(value, bool)]
    return max(numbers) if numbers else 0


def _average_number(values: Any) -> float:
    numbers = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    return sum(numbers) / len(numbers) if numbers else 0.0


def _id_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _text_or_none(value: Any) -> str | None:
    text = _text(value)
    return text or None
