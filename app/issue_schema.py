"""Issue consolidation schema definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ISSUE_TYPE_PROBLEM = "problem"
ISSUE_TYPE_MIXED = "mixed"
ISSUE_TYPE_POSITIVE_FEEDBACK = "positive_feedback"
ISSUE_TYPE_NEUTRAL_OBSERVATION = "neutral_observation"
VALID_ISSUE_TYPES = {
    ISSUE_TYPE_PROBLEM,
    ISSUE_TYPE_MIXED,
    ISSUE_TYPE_POSITIVE_FEEDBACK,
    ISSUE_TYPE_NEUTRAL_OBSERVATION,
}


@dataclass(frozen=True)
class Issue:
    issue_id: str
    name: str
    description: str
    topic_ids: list[str]
    review_ids: list[str]
    merge_rationale: str
    confidence: float
    uncertainty: str
    issue_type: str | None = None


@dataclass(frozen=True)
class IssueConsolidationOutput:
    issues: list[Issue]
    unmerged_topic_ids: list[str]


ISSUE_CONSOLIDATION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["issues", "unmerged_topic_ids"],
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "issue_id",
                    "name",
                    "description",
                    "topic_ids",
                    "review_ids",
                    "merge_rationale",
                    "confidence",
                    "uncertainty",
                ],
                "properties": {
                    "issue_id": {"type": "string", "minLength": 1},
                    "name": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1},
                    "topic_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "review_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "merge_rationale": {"type": "string", "minLength": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "uncertainty": {"type": "string"},
                },
            },
        },
        "unmerged_topic_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
}


CLASSIFIED_ISSUE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "issue_id",
        "issue_type",
        "name",
        "description",
        "topic_ids",
        "review_ids",
        "merge_rationale",
        "confidence",
        "uncertainty",
    ],
    "properties": {
        "issue_id": {"type": "string", "minLength": 1},
        "issue_type": {"type": "string", "enum": sorted(VALID_ISSUE_TYPES)},
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 1},
        "topic_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "review_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "merge_rationale": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "uncertainty": {"type": "string"},
    },
}
