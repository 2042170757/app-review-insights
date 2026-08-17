"""Deterministic schema and evidence validation for discovered topics."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from app.topic_schema import Topic


STATUS_SUCCESS = "Success"
STATUS_INVALID_JSON = "Invalid JSON"
STATUS_SCHEMA_VALIDATION_FAILED = "Schema Validation Failed"
STATUS_UNKNOWN_REVIEW_ID = "Unknown Review ID"
STATUS_EMPTY_TOPICS = "Empty Topics"


@dataclass
class TopicValidationResult:
    status: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    topics: list[Topic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["topics"] = [asdict(topic) for topic in self.topics]
        return payload


def validate_topic_output(raw_text: str, valid_review_ids: set[str]) -> TopicValidationResult:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return TopicValidationResult(
            status=STATUS_INVALID_JSON,
            passed=False,
            errors=[f"Invalid JSON: {exc.msg}"],
        )
    return validate_topic_payload(payload, valid_review_ids)


def validate_topic_payload(payload: Any, valid_review_ids: set[str]) -> TopicValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    topics: list[Topic] = []

    if not isinstance(payload, dict):
        return TopicValidationResult(
            status=STATUS_SCHEMA_VALIDATION_FAILED,
            passed=False,
            errors=["schema: root must be an object"],
        )

    raw_topics = payload.get("topics")
    if raw_topics is None:
        return TopicValidationResult(
            status=STATUS_SCHEMA_VALIDATION_FAILED,
            passed=False,
            errors=["schema: missing topics"],
        )
    if not isinstance(raw_topics, list):
        return TopicValidationResult(
            status=STATUS_SCHEMA_VALIDATION_FAILED,
            passed=False,
            errors=["schema: topics must be a list"],
        )
    if not raw_topics:
        return TopicValidationResult(
            status=STATUS_EMPTY_TOPICS,
            passed=True,
            warnings=["empty_topics"],
            topics=[],
        )

    seen_topic_ids: set[str] = set()
    unknown_review_errors: list[str] = []
    for index, raw_topic in enumerate(raw_topics):
        topic_prefix = f"topics[{index}]"
        if not isinstance(raw_topic, dict):
            errors.append(f"{topic_prefix}: must be an object")
            continue

        topic_id = _text(raw_topic.get("topic_id"))
        name = _text(raw_topic.get("name"))
        description = _text(raw_topic.get("description"))
        uncertainty = _text_allow_empty(raw_topic.get("uncertainty"))
        review_ids = raw_topic.get("review_ids")
        confidence = raw_topic.get("confidence")

        if not topic_id:
            errors.append(f"{topic_prefix}.topic_id: required")
        elif topic_id in seen_topic_ids:
            errors.append(f"{topic_prefix}.topic_id: duplicate {topic_id}")
        else:
            seen_topic_ids.add(topic_id)

        if not name:
            errors.append(f"{topic_prefix}.name: required")
        if not description:
            errors.append(f"{topic_prefix}.description: required")
        if uncertainty is None:
            errors.append(f"{topic_prefix}.uncertainty: required")
        if not isinstance(review_ids, list) or not review_ids:
            errors.append(f"{topic_prefix}.review_ids: must contain at least one review id")
            normalized_review_ids: list[str] = []
        else:
            normalized_review_ids = [_text(item) for item in review_ids]
            for review_id in normalized_review_ids:
                if not review_id:
                    errors.append(f"{topic_prefix}.review_ids: empty review id")
                elif review_id not in valid_review_ids:
                    unknown_review_errors.append(
                        f"{topic_prefix}.review_ids: unknown review id {review_id}"
                    )

        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            errors.append(f"{topic_prefix}.confidence: must be a number from 0 to 1")
            normalized_confidence = 0.0
        else:
            normalized_confidence = float(confidence)
            if normalized_confidence < 0 or normalized_confidence > 1:
                errors.append(f"{topic_prefix}.confidence: out of range {normalized_confidence}")

        if (
            topic_id
            and name
            and description
            and uncertainty is not None
            and isinstance(review_ids, list)
            and normalized_review_ids
            and isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
        ):
            topics.append(
                Topic(
                    topic_id=topic_id,
                    name=name,
                    description=description,
                    review_ids=normalized_review_ids,
                    confidence=normalized_confidence,
                    uncertainty=uncertainty,
                )
            )

    if unknown_review_errors:
        return TopicValidationResult(
            status=STATUS_UNKNOWN_REVIEW_ID,
            passed=False,
            errors=errors + unknown_review_errors,
            warnings=warnings,
            topics=[],
        )
    if errors:
        return TopicValidationResult(
            status=STATUS_SCHEMA_VALIDATION_FAILED,
            passed=False,
            errors=errors,
            warnings=warnings,
            topics=[],
        )
    return TopicValidationResult(
        status=STATUS_SUCCESS,
        passed=True,
        errors=[],
        warnings=warnings,
        topics=topics,
    )


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _text_allow_empty(value: Any) -> str | None:
    return value if isinstance(value, str) else None

