"""Version planning schema definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VALID_VERSION_IDS = {"V1", "V2", "V3", "Deferred"}


@dataclass(frozen=True)
class Version:
    version_id: str
    name: str
    goal: str
    requirement_ids: list[str]
    rationale: str
    risks: list[str]
    success_metrics: list[str]


VERSION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["versions"],
    "properties": {
        "versions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "version_id",
                    "name",
                    "goal",
                    "requirement_ids",
                    "rationale",
                    "risks",
                    "success_metrics",
                ],
                "properties": {
                    "version_id": {"type": "string", "enum": sorted(VALID_VERSION_IDS)},
                    "name": {"type": "string", "minLength": 1},
                    "goal": {"type": "string", "minLength": 1},
                    "requirement_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "rationale": {"type": "string", "minLength": 1},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "success_metrics": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}
