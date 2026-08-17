"""PRD schema definitions for Phase 6a."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PRD:
    prd_id: str
    version_id: str
    title: str
    overview: str
    problem_statement: str
    evidence_summary: str
    goals: list[str]
    non_goals: list[str]
    requirement_ids: list[str]
    risks: list[str]
    success_metrics: list[str]
    open_questions: list[str]


@dataclass(frozen=True)
class PRDGenerationOutput:
    prds: list[PRD]


PRD_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["prds"],
    "properties": {
        "prds": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "prd_id",
                    "version_id",
                    "title",
                    "overview",
                    "problem_statement",
                    "evidence_summary",
                    "goals",
                    "non_goals",
                    "requirement_ids",
                    "risks",
                    "success_metrics",
                    "open_questions",
                ],
                "properties": {
                    "prd_id": {"type": "string", "minLength": 1},
                    "version_id": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1},
                    "overview": {"type": "string", "minLength": 1},
                    "problem_statement": {"type": "string", "minLength": 1},
                    "evidence_summary": {"type": "string", "minLength": 1},
                    "goals": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "non_goals": {"type": "array", "items": {"type": "string"}},
                    "requirement_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "success_metrics": {"type": "array", "items": {"type": "string"}},
                    "open_questions": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}
