"""Runtime LLM topic discovery over processed reviews."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.llm.base import (
    LLMProvider,
    LLMRequest,
    MissingAPIKeyError,
    ModelAuthenticationError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
)
from app.llm.json_recovery import parse_json_response
from app.topic_schema import Topic
from app.topic_validator import TopicValidationResult, validate_topic_output


DEFAULT_PROCESSED_REVIEWS_PATH = Path("artifacts/processed/reviews.json")
DEFAULT_ANALYSIS_DIR = Path("artifacts/analysis")


SYSTEM_PROMPT = """You are performing dynamic topic discovery over app store reviews.

Rules:
1. Only use the input Reviews provided in this request.
2. Do not use external knowledge to infer user feedback.
3. Every Topic must have Review Evidence.
4. Every review_id must be selected exactly from VALID REVIEW IDS in the input.
5. When uncertain, lower confidence and explain uncertainty.
6. Do not invent weak topics just to increase topic count.
7. Do not generate Requirements.
8. Do not generate product solutions.
9. The current task is only Topic discovery.
10. Topics must be dynamically induced from the current data, not from a predefined taxonomy.
11. Do not use a predefined Topic list.
12. Do not choose fixed Topics from app name or app id.
13. Do not create, modify, abbreviate, or infer review_id values.
14. Do not use model memory or external data to guess review_id values.
15. If evidence is uncertain, reduce review_ids instead of fabricating IDs.

Return only JSON matching the required schema."""


REFERENCE_REPAIR_SYSTEM_PROMPT = """You are repairing Topic Discovery review_id references only.

Rules:
1. Preserve each topic_id, name, description, confidence, and uncertainty.
2. Only edit review_ids.
3. Every review_id must be selected exactly from VALID REVIEW IDS.
4. Do not create, modify, abbreviate, or infer review_id values.
5. Do not automatically substitute a similar-looking review_id.
6. If an invalid review_id cannot be verified from the provided Reviews, remove it.
7. If removing invalid IDs leaves a topic without evidence, leave review_ids empty and let validation decide.
8. Do not add new topics, Requirements, product solutions, Roadmap, PRD, or Test Cases.

Return only JSON matching the Topic Discovery schema."""


@dataclass
class TopicDiscoveryResult:
    status: str
    raw_output: str
    validation: TopicValidationResult
    topics: list[Topic]
    provider: str | None
    model: str | None
    analysis_goal: str
    saved_paths: dict[str, str]
    error: str | None = None
    extracted_json: str | None = None
    response_metadata: dict[str, Any] | None = None
    initial_raw_response: str | None = None
    initial_extracted_json: str | None = None
    repair_raw_response: str | None = None
    repair_extracted_json: str | None = None
    repair_response_metadata: dict[str, Any] | None = None
    reference_integrity: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return self.validation.passed and self.status in {"Success", "Empty Topics"}


def discover_topics(
    reviews: list[dict[str, Any]],
    *,
    analysis_goal: str,
    provider: LLMProvider,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> TopicDiscoveryResult:
    request = build_topic_request(reviews, analysis_goal=analysis_goal)
    try:
        response = provider.generate(request)
    except MissingAPIKeyError as exc:
        return create_provider_failure_result("Missing API Key", analysis_goal, str(exc), output_dir, provider)
    except ModelAuthenticationError as exc:
        return create_provider_failure_result("Authentication Error", analysis_goal, str(exc), output_dir, provider)
    except ModelRateLimitError as exc:
        return create_provider_failure_result("Rate Limit", analysis_goal, str(exc), output_dir, provider)
    except ModelTimeoutError as exc:
        return create_provider_failure_result("Timeout", analysis_goal, str(exc), output_dir, provider)
    except ModelRequestError as exc:
        return create_provider_failure_result("Model Request Error", analysis_goal, str(exc), output_dir, provider)

    valid_review_ids = {_review_id(review) for review in reviews if _review_id(review)}
    initial_extracted_json = extract_json_text(response.raw_text)
    extracted_json = initial_extracted_json
    repair_raw_response: str | None = None
    repair_extracted_json: str | None = None
    repair_response_metadata: dict[str, Any] | None = None
    initial_unknown_review_ids = find_unknown_topic_review_ids(initial_extracted_json, valid_review_ids)
    reference_integrity = {
        "initial_unknown_review_ids": initial_unknown_review_ids,
        "repair_attempted": False,
        "repair_reason": None,
        "repair_success": False,
        "final_unknown_review_ids": initial_unknown_review_ids,
    }
    if initial_unknown_review_ids:
        reference_integrity["repair_attempted"] = True
        reference_integrity["repair_reason"] = "unknown_review_id"
        repair_request = build_topic_reference_repair_request(
            initial_extracted_json,
            reviews=reviews,
            valid_review_ids=valid_review_ids,
            invalid_review_ids=initial_unknown_review_ids,
            analysis_goal=analysis_goal,
        )
        try:
            repair_response = provider.generate(repair_request)
        except MissingAPIKeyError as exc:
            return create_reference_repair_failure_result(
                "Missing API Key",
                analysis_goal,
                str(exc),
                output_dir,
                provider,
                initial_response=response,
                initial_extracted_json=initial_extracted_json,
                reference_integrity=reference_integrity,
            )
        except ModelAuthenticationError as exc:
            return create_reference_repair_failure_result(
                "Authentication Error",
                analysis_goal,
                str(exc),
                output_dir,
                provider,
                initial_response=response,
                initial_extracted_json=initial_extracted_json,
                reference_integrity=reference_integrity,
            )
        except ModelRateLimitError as exc:
            return create_reference_repair_failure_result(
                "Rate Limit",
                analysis_goal,
                str(exc),
                output_dir,
                provider,
                initial_response=response,
                initial_extracted_json=initial_extracted_json,
                reference_integrity=reference_integrity,
            )
        except ModelTimeoutError as exc:
            return create_reference_repair_failure_result(
                "Timeout",
                analysis_goal,
                str(exc),
                output_dir,
                provider,
                initial_response=response,
                initial_extracted_json=initial_extracted_json,
                reference_integrity=reference_integrity,
            )
        except ModelRequestError as exc:
            return create_reference_repair_failure_result(
                "Model Request Error",
                analysis_goal,
                str(exc),
                output_dir,
                provider,
                initial_response=response,
                initial_extracted_json=initial_extracted_json,
                reference_integrity=reference_integrity,
            )
        repair_raw_response = repair_response.raw_text
        repair_extracted_json = extract_json_text(repair_raw_response)
        repair_response_metadata = repair_response.metadata
        extracted_json = repair_extracted_json
        final_unknown_review_ids = find_unknown_topic_review_ids(extracted_json, valid_review_ids)
        reference_integrity["final_unknown_review_ids"] = final_unknown_review_ids
        reference_integrity["repair_success"] = not final_unknown_review_ids

    validation = validate_topic_output(extracted_json, valid_review_ids)
    topics = validation.topics if validation.passed else []
    result = TopicDiscoveryResult(
        status=validation.status,
        raw_output=response.raw_text,
        validation=validation,
        topics=topics,
        provider=response.provider,
        model=response.model,
        analysis_goal=analysis_goal,
        saved_paths={},
        extracted_json=extracted_json,
        response_metadata=response.metadata,
        initial_raw_response=response.raw_text,
        initial_extracted_json=initial_extracted_json,
        repair_raw_response=repair_raw_response,
        repair_extracted_json=repair_extracted_json,
        repair_response_metadata=repair_response_metadata,
        reference_integrity=reference_integrity,
    )
    save_topic_outputs(result, output_dir=output_dir)
    return result


def build_topic_request(reviews: list[dict[str, Any]], *, analysis_goal: str) -> LLMRequest:
    review_payload = []
    for review in reviews:
        review_id = _review_id(review)
        if not review_id:
            continue
        review_payload.append(
            {
                "review_id": review_id,
                "rating": review.get("rating"),
                "title": review.get("clean_title") or review.get("title"),
                "body": review.get("clean_body") or review.get("body"),
                "created_at": review.get("created_at"),
                "language": review.get("language"),
            }
        )
    user_prompt = json.dumps(
        {
            "analysis_goal": analysis_goal,
            "valid_review_ids": [item["review_id"] for item in review_payload],
            "reviews": review_payload,
            "required_output_schema": {
                "topics": [
                    {
                        "topic_id": "TOPIC-001",
                        "name": "string",
                        "description": "string",
                        "review_ids": ["review-id"],
                        "confidence": 0.0,
                        "uncertainty": "string",
                    }
                ]
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    return LLMRequest(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        analysis_goal=analysis_goal,
    )


def build_topic_reference_repair_request(
    extracted_json: str,
    *,
    reviews: list[dict[str, Any]],
    valid_review_ids: set[str],
    invalid_review_ids: list[str],
    analysis_goal: str,
) -> LLMRequest:
    review_payload = []
    for review in reviews:
        review_id = _review_id(review)
        if not review_id:
            continue
        review_payload.append(
            {
                "review_id": review_id,
                "rating": review.get("rating"),
                "title": review.get("clean_title") or review.get("title"),
                "body": review.get("clean_body") or review.get("body"),
                "created_at": review.get("created_at"),
                "language": review.get("language"),
            }
        )
    try:
        topic_output_to_repair: Any = json.loads(extracted_json)
    except json.JSONDecodeError:
        topic_output_to_repair = extracted_json
    user_prompt = json.dumps(
        {
            "task": "topic_review_id_reference_repair",
            "analysis_goal": analysis_goal,
            "invalid_review_ids": invalid_review_ids,
            "valid_review_ids": sorted(valid_review_ids),
            "valid_review_ids_label": "VALID REVIEW IDS",
            "reviews": review_payload,
            "topic_output_to_repair": topic_output_to_repair,
            "required_output_schema": {
                "topics": [
                    {
                        "topic_id": "TOPIC-001",
                        "name": "string",
                        "description": "string",
                        "review_ids": ["review-id-from-valid-review-ids-only"],
                        "confidence": 0.0,
                        "uncertainty": "string",
                    }
                ]
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    return LLMRequest(
        system_prompt=REFERENCE_REPAIR_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        analysis_goal=analysis_goal,
    )


def load_processed_reviews(path: Path = DEFAULT_PROCESSED_REVIEWS_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    reviews = payload.get("reviews") if isinstance(payload, dict) else None
    if not isinstance(reviews, list) or not all(isinstance(review, dict) for review in reviews):
        raise ValueError(f"Processed reviews file is invalid: {path}")
    return list(reviews)


def save_topic_outputs(result: TopicDiscoveryResult, *, output_dir: Path = DEFAULT_ANALYSIS_DIR) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "topic_discovery_raw.json"
    topics_path = output_dir / "topics.json"
    validation_path = output_dir / "topic_validation.json"

    raw_payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": result.provider,
        "model": result.model,
        "analysis_goal": result.analysis_goal,
        "status": result.status,
        "raw_output": result.raw_output,
        "initial_raw_response": result.initial_raw_response if result.initial_raw_response is not None else result.raw_output,
        "initial_extracted_json": result.initial_extracted_json,
        "repair_raw_response": result.repair_raw_response,
        "repair_extracted_json": result.repair_extracted_json,
        "repair_method": "reference_review_id_repair" if result.repair_raw_response is not None else None,
        "extracted_json": result.extracted_json,
        "topics_extracted": _parse_extracted_json(result.extracted_json),
        "reference_integrity": result.reference_integrity or _default_reference_integrity(),
        "response_metadata": result.response_metadata or {},
        "repair_response_metadata": result.repair_response_metadata or {},
        "error": result.error,
    }
    raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    topics_path.write_text(
        json.dumps({"topics": [asdict(topic) for topic in result.topics]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    validation_path.write_text(
        json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths = {"raw": raw_path, "topics": topics_path, "validation": validation_path}
    result.saved_paths = {key: str(path) for key, path in paths.items()}
    return paths


def create_failure_result(
    status: str,
    analysis_goal: str,
    error: str,
    output_dir: Path,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> TopicDiscoveryResult:
    validation = TopicValidationResult(status="SKIPPED", passed=False, errors=[error])
    result = TopicDiscoveryResult(
        status=status,
        raw_output="",
        validation=validation,
        topics=[],
        provider=provider,
        model=model,
        analysis_goal=analysis_goal,
        saved_paths={},
        error=error,
        reference_integrity=_default_reference_integrity(),
    )
    save_topic_outputs(result, output_dir=output_dir)
    return result


def create_provider_failure_result(
    status: str,
    analysis_goal: str,
    error: str,
    output_dir: Path,
    provider: LLMProvider,
) -> TopicDiscoveryResult:
    return create_failure_result(
        status,
        analysis_goal,
        error,
        output_dir,
        provider=getattr(provider, "provider_name", None),
        model=getattr(provider, "model", None),
    )


def create_reference_repair_failure_result(
    status: str,
    analysis_goal: str,
    error: str,
    output_dir: Path,
    provider: LLMProvider,
    *,
    initial_response,
    initial_extracted_json: str,
    reference_integrity: dict[str, Any],
) -> TopicDiscoveryResult:
    reference_integrity = dict(reference_integrity)
    reference_integrity["repair_success"] = False
    validation = TopicValidationResult(status="SKIPPED", passed=False, errors=[error])
    result = TopicDiscoveryResult(
        status=status,
        raw_output=initial_response.raw_text,
        validation=validation,
        topics=[],
        provider=getattr(provider, "provider_name", getattr(initial_response, "provider", None)),
        model=getattr(provider, "model", getattr(initial_response, "model", None)),
        analysis_goal=analysis_goal,
        saved_paths={},
        error=error,
        extracted_json=initial_extracted_json,
        response_metadata=getattr(initial_response, "metadata", {}),
        initial_raw_response=initial_response.raw_text,
        initial_extracted_json=initial_extracted_json,
        reference_integrity=reference_integrity,
    )
    save_topic_outputs(result, output_dir=output_dir)
    return result


def _review_id(review: dict[str, Any]) -> str:
    value = review.get("id")
    return value.strip() if isinstance(value, str) else ""


def find_unknown_topic_review_ids(raw_json_text: str, valid_review_ids: set[str]) -> list[str]:
    try:
        payload = json.loads(raw_json_text)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    raw_topics = payload.get("topics")
    if not isinstance(raw_topics, list):
        return []
    unknown_ids: list[str] = []
    seen: set[str] = set()
    for raw_topic in raw_topics:
        if not isinstance(raw_topic, dict):
            continue
        review_ids = raw_topic.get("review_ids")
        if not isinstance(review_ids, list):
            continue
        for value in review_ids:
            review_id = value.strip() if isinstance(value, str) else ""
            if review_id and review_id not in valid_review_ids and review_id not in seen:
                seen.add(review_id)
                unknown_ids.append(review_id)
    return unknown_ids


def _parse_extracted_json(extracted_json: str | None) -> Any:
    if not extracted_json:
        return None
    try:
        return json.loads(extracted_json)
    except json.JSONDecodeError:
        return None


def _default_reference_integrity() -> dict[str, Any]:
    return {
        "initial_unknown_review_ids": [],
        "repair_attempted": False,
        "repair_reason": None,
        "repair_success": False,
        "final_unknown_review_ids": [],
    }


def extract_json_text(raw_text: str) -> str:
    result = parse_json_response(raw_text)
    return result.extracted_response if result.success else raw_text.strip()
