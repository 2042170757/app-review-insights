"""Requirement schema definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
REQUIREMENT_TYPE_PROBLEM = "problem"
REQUIREMENT_TYPE_POSITIVE_FEEDBACK = "positive_feedback"
REQUIREMENT_TYPE_MIXED = "mixed"
VALID_REQUIREMENT_TYPES = {
    REQUIREMENT_TYPE_PROBLEM,
    REQUIREMENT_TYPE_POSITIVE_FEEDBACK,
    REQUIREMENT_TYPE_MIXED,
}


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    finding_ids: list[str]
    title: str
    description: str
    acceptance_criteria: list[str]
    priority: str
    priority_rationale: str
    risks: list[str]
    success_metrics: list[str]
    uncertainty: str
    source_review_ids: list[str] | None = None
    requirement_type: str = REQUIREMENT_TYPE_PROBLEM


@dataclass(frozen=True)
class RequirementGenerationOutput:
    requirements: list[Requirement]


REQUIREMENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["requirements"],
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "requirement_id",
                    "finding_ids",
                    "title",
                    "description",
                    "acceptance_criteria",
                    "priority",
                    "priority_rationale",
                    "risks",
                    "success_metrics",
                    "uncertainty",
                ],
                "properties": {
                    "requirement_id": {"type": "string", "minLength": 1},
                    "requirement_type": {
                        "type": "string",
                        "enum": sorted(VALID_REQUIREMENT_TYPES),
                    },
                    "finding_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "title": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1},
                    "acceptance_criteria": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "priority": {"type": "string", "enum": sorted(VALID_PRIORITIES)},
                    "priority_rationale": {"type": "string", "minLength": 1},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "success_metrics": {"type": "array", "items": {"type": "string"}},
                    "uncertainty": {"type": "string"},
                    "source_review_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
            },
        }
    },
}
