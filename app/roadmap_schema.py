"""Roadmap item and dependency schema definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.requirement_schema import VALID_PRIORITIES


@dataclass(frozen=True)
class Dependency:
    requirement_id: str
    depends_on: str


@dataclass(frozen=True)
class RoadmapItem:
    requirement_id: str
    version_id: str
    priority: str
    rationale: str
    dependencies: list[str]


@dataclass(frozen=True)
class RoadmapPlan:
    versions: list[dict[str, Any]]
    roadmap_items: list[dict[str, Any]]
    deferred_requirement_ids: list[str]
    deferred_rationale: dict[str, str]


ROADMAP_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["versions", "roadmap_items"],
    "properties": {
        "versions": {
            "type": "array",
            "items": {"type": "object"},
        },
        "roadmap_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["requirement_id", "version_id", "priority", "rationale", "dependencies"],
                "properties": {
                    "requirement_id": {"type": "string", "minLength": 1},
                    "version_id": {"type": "string", "minLength": 1},
                    "priority": {"type": "string", "enum": sorted(VALID_PRIORITIES)},
                    "rationale": {"type": "string", "minLength": 1},
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
        "deferred_requirement_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "deferred_rationale": {
            "type": "object",
            "additionalProperties": {"type": "string", "minLength": 1},
        },
    },
}
