"""Issue consolidation over validated topics and review evidence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.analysis_intent import DEFAULT_ANALYSIS_FOCUS, focus_label, normalize_analysis_focus
from app.issue_schema import Issue
from app.issue_validator import IssueValidationResult, validate_issue_output
from app.llm.base import (
    LLMProvider,
    LLMRequest,
    MissingAPIKeyError,
    ModelAuthenticationError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
)
from app.topic_discovery import extract_json_text


DEFAULT_PROCESSED_REVIEWS_PATH = Path("artifacts/processed/reviews.json")
DEFAULT_TOPICS_PATH = Path("artifacts/analysis/topics.json")
DEFAULT_ANALYSIS_DIR = Path("artifacts/analysis")
DEFAULT_MOCK_ISSUE_OUTPUT = json.dumps({"issues": [], "unmerged_topic_ids": []})
DEFAULT_ISSUE_GOAL = "分析低评分用户对订阅和价格的主要问题"


SYSTEM_PROMPT = """You are performing Issue Consolidation over already validated review Topics.

Rules:
1. The current task is Issue Consolidation.
2. The input Topics have already been validated.
3. The input Review Evidence has already been validated.
4. Decide which Topics describe the same underlying user problem.
5. Merge Topics only when multiple Topics represent the same underlying user problem.
6. When uncertain, do not force a merge.
7. Precision is more important than reducing the Issue count.
8. Single Topic to single Issue, multiple Topics to single Issue, and unmerged Topics are all allowed.
9. Do not invent new Reviews.
10. Do not reference Topic IDs that are not in the input.
11. Do not reference Review IDs that are not in the input.
12. Every Issue must include merge_rationale.
13. Do not generate Requirements.
14. Do not generate product solutions.
15. Do not generate Roadmaps.
16. Do not generate PRDs.
17. Consider underlying user problem, causal relationship, user intent, symptom similarity, and evidence overlap.
18. Do not merge only because Topics share keywords, app features, sentiment, or ratings.
19. Preserve traceability for every input Topic: every Topic must appear in at least one Issue topic_ids entry.
20. If a Topic is positive feedback, neutral observation, or otherwise not a product problem, still create a single-Topic Issue that preserves the Topic and its Review Evidence; deterministic classification and Finding Eligibility will decide whether it can proceed to Findings.
21. Use unmerged_topic_ids only when the input Topic cannot be represented with valid Review Evidence. Do not use unmerged_topic_ids for ordinary distinct Topics.

Return only JSON matching the required issue schema."""


@dataclass
class IssueConsolidationResult:
    status: str
    raw_output: str
    validation: IssueValidationResult
    issues: list[Issue]
    provider: str | None
    model: str | None
    unmerged_topic_ids: list[str]
    saved_paths: dict[str, str]
    analysis_goal: str
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS
    error: str | None = None
    extracted_json: str | None = None
    response_metadata: dict[str, Any] | None = None
    is_mock: bool = False

    @property
    def passed(self) -> bool:
        return self.validation.passed and self.status in {"Success", "Empty Issues"}


def consolidate_issues(
    reviews: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    *,
    provider: LLMProvider,
    analysis_goal: str = DEFAULT_ISSUE_GOAL,
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
    is_mock: bool = False,
) -> IssueConsolidationResult:
    analysis_focus = normalize_analysis_focus(analysis_focus)
    request = build_issue_request(reviews, topics, analysis_goal=analysis_goal, analysis_focus=analysis_focus)
    try:
        response = provider.generate(request)
    except MissingAPIKeyError as exc:
        return create_provider_failure_result("Missing API Key", analysis_goal, str(exc), output_dir, provider, is_mock, analysis_focus=analysis_focus)
    except ModelAuthenticationError as exc:
        return create_provider_failure_result("Authentication Error", analysis_goal, str(exc), output_dir, provider, is_mock, analysis_focus=analysis_focus)
    except ModelRateLimitError as exc:
        return create_provider_failure_result("Rate Limit", analysis_goal, str(exc), output_dir, provider, is_mock, analysis_focus=analysis_focus)
    except ModelTimeoutError as exc:
        return create_provider_failure_result("Timeout", analysis_goal, str(exc), output_dir, provider, is_mock, analysis_focus=analysis_focus)
    except ModelRequestError as exc:
        return create_provider_failure_result("Model Request Error", analysis_goal, str(exc), output_dir, provider, is_mock, analysis_focus=analysis_focus)

    topic_ids, review_ids, topic_review_ids = build_validation_context(reviews, topics)
    extracted_json = extract_json_text(response.raw_text)
    validation = validate_issue_output(
        extracted_json,
        valid_topic_ids=topic_ids,
        valid_review_ids=review_ids,
        topic_review_ids=topic_review_ids,
    )
    issues = validation.issues if validation.passed else []
    unmerged_topic_ids = validation.unmerged_topic_ids if validation.passed else []
    result = IssueConsolidationResult(
        status=validation.status,
        raw_output=response.raw_text,
        validation=validation,
        issues=issues,
        provider=response.provider,
        model=response.model,
        unmerged_topic_ids=unmerged_topic_ids,
        saved_paths={},
        analysis_goal=analysis_goal,
        analysis_focus=analysis_focus,
        extracted_json=extracted_json,
        response_metadata=response.metadata,
        is_mock=is_mock,
    )
    save_issue_outputs(result, output_dir=output_dir)
    return result


def build_issue_request(
    reviews: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    *,
    analysis_goal: str = DEFAULT_ISSUE_GOAL,
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS,
) -> LLMRequest:
    analysis_focus = normalize_analysis_focus(analysis_focus)
    reviews_by_id = {_text(review.get("id")): review for review in reviews if _text(review.get("id"))}
    topic_payload = [
        {
            "topic_id": topic.get("topic_id"),
            "name": topic.get("name"),
            "description": topic.get("description"),
            "confidence": topic.get("confidence"),
            "uncertainty": topic.get("uncertainty"),
            "review_ids": topic.get("review_ids"),
            "evidence_reviews": _topic_evidence_reviews(topic, reviews_by_id),
        }
        for topic in topics
    ]
    user_prompt = json.dumps(
        {
            "analysis_goal": analysis_goal,
            "analysis_focus": analysis_focus,
            "analysis_focus_label": focus_label(analysis_focus),
            "topics": topic_payload,
            "valid_topic_ids": [_text(topic.get("topic_id")) for topic in topics if _text(topic.get("topic_id"))],
            "valid_review_ids": sorted(reviews_by_id.keys()),
            "required_output_schema": {
                "issues": [
                    {
                        "issue_id": "ISSUE-001",
                        "name": "string",
                        "description": "string",
                        "topic_ids": ["TOPIC-001"],
                        "review_ids": ["review-id"],
                        "merge_rationale": "string",
                        "confidence": 0.0,
                        "uncertainty": "string",
                    }
                ],
                "unmerged_topic_ids": ["TOPIC-002"],
            },
            "traceability_rule": "Every valid_topic_id must appear in at least one issue.topic_ids entry. Use single-Topic Issues for distinct, positive, neutral, or non-problem Topics so later deterministic classification can preserve or filter them. Leave unmerged_topic_ids empty unless a Topic cannot be represented with valid Review Evidence.",
            "focus_rule": (
                "Consolidate only within the selected analysis_focus. In positive_feedback_analysis, preserve valued experiences as positive-feedback Issues without converting them into user problems. "
                "In mixed_analysis, preserve problem Issues and positive-feedback Issues as distinct Issue evidence when they describe different underlying user intent."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )
    return LLMRequest(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        analysis_goal=analysis_goal,
    )


def build_validation_context(
    reviews: list[dict[str, Any]],
    topics: list[dict[str, Any]],
) -> tuple[set[str], set[str], dict[str, set[str]]]:
    valid_review_ids = {_text(review.get("id")) for review in reviews if _text(review.get("id"))}
    topic_review_ids: dict[str, set[str]] = {}
    valid_topic_ids: set[str] = set()
    for topic in topics:
        topic_id = _text(topic.get("topic_id"))
        if not topic_id:
            continue
        valid_topic_ids.add(topic_id)
        raw_review_ids = topic.get("review_ids")
        if isinstance(raw_review_ids, list):
            topic_review_ids[topic_id] = {_text(item) for item in raw_review_ids if _text(item)}
        else:
            topic_review_ids[topic_id] = set()
    return valid_topic_ids, valid_review_ids, topic_review_ids


def _topic_evidence_reviews(topic: dict[str, Any], reviews_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    raw_review_ids = topic.get("review_ids")
    if not isinstance(raw_review_ids, list):
        return []
    evidence = []
    for review_id in raw_review_ids:
        normalized_review_id = _text(review_id)
        review = reviews_by_id.get(normalized_review_id)
        if not review:
            continue
        evidence.append(
            {
                "review_id": normalized_review_id,
                "rating": review.get("rating"),
                "title": review.get("clean_title") or review.get("title"),
                "body": review.get("clean_body") or review.get("body"),
                "language": review.get("language"),
                "created_at": review.get("created_at"),
            }
        )
    return evidence


def load_processed_reviews(path: Path = DEFAULT_PROCESSED_REVIEWS_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    reviews = payload.get("reviews") if isinstance(payload, dict) else None
    if not isinstance(reviews, list) or not all(isinstance(review, dict) for review in reviews):
        raise ValueError(f"Processed reviews file is invalid: {path}")
    return list(reviews)


def load_topics(path: Path = DEFAULT_TOPICS_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    topics = payload.get("topics") if isinstance(payload, dict) else None
    if not isinstance(topics, list) or not all(isinstance(topic, dict) for topic in topics):
        raise ValueError(f"Topics file is invalid: {path}")
    return list(topics)


def save_issue_outputs(
    result: IssueConsolidationResult,
    *,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "issue_consolidation_raw.json"
    issues_path = output_dir / "issues.json"
    validation_path = output_dir / "issue_validation.json"

    raw_payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "phase": "2.2b",
        "is_mock": result.is_mock,
        "provider": result.provider,
        "model": result.model,
        "analysis_goal": result.analysis_goal,
        "analysis_focus": result.analysis_focus,
        "status": result.status,
        "raw_output": result.raw_output,
        "extracted_json": result.extracted_json,
        "response_metadata": result.response_metadata or {},
        "error": result.error,
    }
    raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    issues_path.write_text(
        json.dumps(
            {
                "issues": [asdict(issue) for issue in result.issues],
                "unmerged_topic_ids": result.unmerged_topic_ids,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    validation_path.write_text(json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    paths = {"raw": raw_path, "issues": issues_path, "validation": validation_path}
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
    is_mock: bool = False,
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS,
) -> IssueConsolidationResult:
    validation = IssueValidationResult(status="SKIPPED", passed=False, errors=[error])
    result = IssueConsolidationResult(
        status=status,
        raw_output="",
        validation=validation,
        issues=[],
        provider=provider,
        model=model,
        unmerged_topic_ids=[],
        saved_paths={},
        analysis_goal=analysis_goal,
        analysis_focus=normalize_analysis_focus(analysis_focus),
        error=error,
        is_mock=is_mock,
    )
    save_issue_outputs(result, output_dir=output_dir)
    return result


def create_provider_failure_result(
    status: str,
    analysis_goal: str,
    error: str,
    output_dir: Path,
    provider: LLMProvider,
    is_mock: bool,
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS,
) -> IssueConsolidationResult:
    return create_failure_result(
        status,
        analysis_goal,
        error,
        output_dir,
        provider=getattr(provider, "provider_name", None),
        model=getattr(provider, "model", None),
        is_mock=is_mock,
        analysis_focus=analysis_focus,
    )


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
