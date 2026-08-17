"""Finding schema definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.finding_eligibility import (
    FINDING_TYPE_NEUTRAL_OBSERVATION,
    FINDING_TYPE_POSITIVE_FEEDBACK,
    FINDING_TYPE_PRODUCT_PROBLEM,
)


VALID_FINDING_TYPES = {
    FINDING_TYPE_PRODUCT_PROBLEM,
    FINDING_TYPE_POSITIVE_FEEDBACK,
    FINDING_TYPE_NEUTRAL_OBSERVATION,
}


@dataclass(frozen=True)
class Finding:
    finding_id: str
    issue_ids: list[str]
    review_ids: list[str]
    title: str
    statement: str
    evidence_summary: str
    support_count: int
    confidence: float
    uncertainty: str
    conflicting_review_ids: list[str]
    finding_type: str = FINDING_TYPE_PRODUCT_PROBLEM


@dataclass(frozen=True)
class FindingGenerationOutput:
    findings: list[Finding]


FINDING_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "finding_id",
                    "issue_ids",
                    "review_ids",
                    "title",
                    "statement",
                    "evidence_summary",
                    "support_count",
                    "confidence",
                    "uncertainty",
                    "conflicting_review_ids",
                ],
                "properties": {
                    "finding_id": {"type": "string", "minLength": 1},
                    "finding_type": {
                        "type": "string",
                        "enum": sorted(VALID_FINDING_TYPES),
                    },
                    "issue_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "review_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "title": {"type": "string", "minLength": 1},
                    "statement": {"type": "string", "minLength": 1},
                    "evidence_summary": {"type": "string", "minLength": 1},
                    "support_count": {"type": "integer", "minimum": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "uncertainty": {"type": "string"},
                    "conflicting_review_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
            },
        }
    },
}
