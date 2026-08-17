"""Topic discovery schema definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Topic:
    topic_id: str
    name: str
    description: str
    review_ids: list[str]
    confidence: float
    uncertainty: str


@dataclass(frozen=True)
class TopicDiscoveryOutput:
    topics: list[Topic]


TOPIC_DISCOVERY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topics"],
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "topic_id",
                    "name",
                    "description",
                    "review_ids",
                    "confidence",
                    "uncertainty",
                ],
                "properties": {
                    "topic_id": {"type": "string", "minLength": 1},
                    "name": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1},
                    "review_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "uncertainty": {"type": "string"},
                },
            },
        }
    },
}

