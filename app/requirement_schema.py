"""Requirement schema definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}


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
