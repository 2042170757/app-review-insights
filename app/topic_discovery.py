"""Runtime LLM topic discovery over processed reviews."""

from __future__ import annotations

import json
import re
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
from app.topic_schema import Topic
from app.topic_validator import TopicValidationResult, validate_topic_output


DEFAULT_PROCESSED_REVIEWS_PATH = Path("artifacts/processed/reviews.json")
DEFAULT_ANALYSIS_DIR = Path("artifacts/analysis")


SYSTEM_PROMPT = """You are performing dynamic topic discovery over app store reviews.

Rules:
1. Only use the input Reviews provided in this request.
2. Do not use external knowledge to infer user feedback.
3. Every Topic must have Review Evidence.
4. Every review_id must be a real review_id from the input.
5. When uncertain, lower confidence and explain uncertainty.
6. Do not invent weak topics just to increase topic count.
7. Do not generate Requirements.
8. Do not generate product solutions.
9. The current task is only Topic discovery.
10. Topics must be dynamically induced from the current data, not from a predefined taxonomy.
11. Do not use a predefined Topic list.
12. Do not choose fixed Topics from app name or app id.

Return only JSON matching the required schema."""


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
    extracted_json = extract_json_text(response.raw_text)
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
        "extracted_json": result.extracted_json,
        "response_metadata": result.response_metadata or {},
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


def _review_id(review: dict[str, Any]) -> str:
    value = review.get("id")
    return value.strip() if isinstance(value, str) else ""


def extract_json_text(raw_text: str) -> str:
    candidates = [raw_text.strip()]
    fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", raw_text, flags=re.IGNORECASE | re.DOTALL)
    candidates.extend(block.strip() for block in fenced_blocks)
    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidates.append(raw_text[first_brace : last_brace + 1].strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return candidate
    return raw_text.strip()
