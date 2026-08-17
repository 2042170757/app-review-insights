"""Test case schema definitions for Phase 7a."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.requirement_schema import VALID_PRIORITIES


VALID_TEST_TYPES = {"functional", "validation", "edge_case", "regression"}


@dataclass(frozen=True)
class TestCase:
    test_case_id: str
    requirement_id: str
    acceptance_criteria_ids: list[str]
    title: str
    preconditions: list[str]
    steps: list[str]
    expected_result: str
    test_type: str
    priority: str
    source_review_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TestCaseGenerationOutput:
    test_cases: list[TestCase]


TEST_CASE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["test_cases"],
    "properties": {
        "test_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "test_case_id",
                    "requirement_id",
                    "acceptance_criteria_ids",
                    "title",
                    "preconditions",
                    "steps",
                    "expected_result",
                    "test_type",
                    "priority",
                    "source_review_ids",
                ],
                "properties": {
                    "test_case_id": {"type": "string", "minLength": 1},
                    "requirement_id": {"type": "string", "minLength": 1},
                    "acceptance_criteria_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "title": {"type": "string", "minLength": 1},
                    "preconditions": {"type": "array", "items": {"type": "string"}},
                    "steps": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "expected_result": {"type": "string", "minLength": 1},
                    "test_type": {"type": "string", "enum": sorted(VALID_TEST_TYPES)},
                    "priority": {"type": "string", "enum": sorted(VALID_PRIORITIES)},
                    "source_review_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
            },
        }
    },
}
