"""Finding generation orchestration for mock and production LLM providers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.finding_validator import FindingValidationResult, validate_finding_output
from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
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


DEFAULT_FINDING_GOAL = "分析低评分用户对订阅和价格的主要问题"
DEFAULT_REVIEWS_PATH = Path("artifacts/processed/reviews.json")
DEFAULT_ISSUES_PATH = Path("artifacts/analysis/issues.json")
DEFAULT_CLASSIFICATION_PATH = Path("artifacts/analysis/issue_classification.json")
DEFAULT_ELIGIBILITY_PATH = Path("artifacts/analysis/finding_eligibility.json")


SYSTEM_PROMPT = """You are performing Evidence-Grounded Finding Generation.

Rules:
1. The current task is Evidence-Grounded Finding Generation.
2. The input Issues have already passed Issue Validator.
3. The input Reviews come from the corresponding Issue evidence.
4. Only use the input Review Evidence to derive Findings.
5. Do not use external knowledge to add facts.
6. Do not reference Review IDs outside the input.
7. Do not expand conclusions beyond the provided evidence.
8. Do not use unsupported absolute phrases such as "all users", "most users", or "the majority of users".
9. Explicitly state that conclusions are based on the current review sample.
10. Always explain uncertainty.
11. If evidence is limited, lower confidence and explain the limitation.
12. If conflicting evidence exists, preserve it.
13. Do not delete counter-evidence.
14. Do not generate Requirements.
15. Do not generate product solutions.
16. Do not generate Roadmaps.
17. Do not generate PRDs.
18. Do not generate Test Cases.

Return only JSON matching the required Finding schema."""


@dataclass
class FindingGenerationResult:
    generation_status: str
    generation_passed: bool
    raw_output: str
    validation: FindingValidationResult
    findings: list[dict[str, Any]]
    evidence_reports: list[dict[str, Any]]
    provider: str | None
    model: str | None
    analysis_goal: str
    eligible_issue_count: int
    saved_paths: dict[str, str]
    error: str | None = None
    extracted_json: str | None = None
    response_metadata: dict[str, Any] | None = None
    is_mock: bool = False


def generate_findings(
    *,
    reviews: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
    eligibility: list[dict[str, Any]],
    provider: LLMProvider,
    analysis_goal: str = DEFAULT_FINDING_GOAL,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
    is_mock: bool = False,
) -> FindingGenerationResult:
    eligible_issue_ids = {
        item["issue_id"] for item in eligibility if item.get("eligible_for_finding") is True
    }
    request = build_finding_request(
        reviews=reviews,
        issues=issues,
        classifications=classifications,
        eligibility=eligibility,
        analysis_goal=analysis_goal,
    )
    try:
        response = provider.generate(request)
    except MissingAPIKeyError as exc:
        return create_failure_result("Missing API Key", analysis_goal, str(exc), output_dir, provider, is_mock, len(eligible_issue_ids))
    except ModelAuthenticationError as exc:
        return create_failure_result("Authentication Error", analysis_goal, str(exc), output_dir, provider, is_mock, len(eligible_issue_ids))
    except ModelRateLimitError as exc:
        return create_failure_result("Rate Limit", analysis_goal, str(exc), output_dir, provider, is_mock, len(eligible_issue_ids))
    except ModelTimeoutError as exc:
        return create_failure_result("Timeout", analysis_goal, str(exc), output_dir, provider, is_mock, len(eligible_issue_ids))
    except ModelRequestError as exc:
        return create_failure_result("Model Request Error", analysis_goal, str(exc), output_dir, provider, is_mock, len(eligible_issue_ids))

    extracted_json = extract_json_text(response.raw_text)
    issues_by_id = {issue["issue_id"]: issue for issue in issues if isinstance(issue.get("issue_id"), str)}
    valid_review_ids = {review["id"] for review in reviews if isinstance(review.get("id"), str)}
    validation = validate_finding_output(
        extracted_json,
        issues_by_id=issues_by_id,
        valid_review_ids=valid_review_ids,
        eligible_issue_ids=eligible_issue_ids,
    )
    findings = [asdict(finding) for finding in validation.findings] if validation.passed else []
    evidence_reports = [report.to_dict() for report in validation.evidence_reports] if validation.passed else []
    generation_passed = validation.status != "Invalid JSON"
    result = FindingGenerationResult(
        generation_status="Success" if generation_passed else "Invalid JSON",
        generation_passed=generation_passed,
        raw_output=response.raw_text,
        validation=validation,
        findings=findings,
        evidence_reports=evidence_reports,
        provider=response.provider,
        model=response.model,
        analysis_goal=analysis_goal,
        eligible_issue_count=len(eligible_issue_ids),
        saved_paths={},
        extracted_json=extracted_json,
        response_metadata=response.metadata,
        is_mock=is_mock,
    )
    save_finding_outputs(result, output_dir=output_dir)
    return result


def build_finding_request(
    *,
    reviews: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
    eligibility: list[dict[str, Any]],
    analysis_goal: str,
) -> LLMRequest:
    reviews_by_id = {review["id"]: review for review in reviews if isinstance(review.get("id"), str)}
    classifications_by_id = {item["issue_id"]: item for item in classifications if isinstance(item.get("issue_id"), str)}
    eligible_issue_ids = {
        item["issue_id"] for item in eligibility if item.get("eligible_for_finding") is True
    }
    eligible_issues = []
    for issue in issues:
        issue_id = issue.get("issue_id")
        if issue_id not in eligible_issue_ids:
            continue
        evidence_reviews = []
        for review_id in issue.get("review_ids", []):
            review = reviews_by_id.get(review_id)
            if not review:
                continue
            evidence_reviews.append(
                {
                    "review_id": review_id,
                    "rating": review.get("rating"),
                    "title": review.get("clean_title") or review.get("title"),
                    "body": review.get("clean_body") or review.get("body"),
                    "language": review.get("language"),
                    "created_at": review.get("created_at"),
                }
            )
        eligible_issues.append(
            {
                "issue_id": issue_id,
                "issue_type": classifications_by_id.get(issue_id, {}).get("issue_type"),
                "name": issue.get("name"),
                "description": issue.get("description"),
                "review_ids": issue.get("review_ids"),
                "merge_rationale": issue.get("merge_rationale"),
                "confidence": issue.get("confidence"),
                "uncertainty": issue.get("uncertainty"),
                "evidence_reviews": evidence_reviews,
            }
        )

    user_prompt = json.dumps(
        {
            "analysis_goal": analysis_goal,
            "eligible_issues": eligible_issues,
            "valid_issue_ids": sorted(eligible_issue_ids),
            "required_output_schema": {
                "findings": [
                    {
                        "finding_id": "FINDING-001",
                        "issue_ids": ["ISSUE-001"],
                        "review_ids": ["review-id"],
                        "title": "string",
                        "statement": "string",
                        "evidence_summary": "string",
                        "support_count": 1,
                        "confidence": 0.0,
                        "uncertainty": "string",
                        "conflicting_review_ids": [],
                    }
                ]
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    return LLMRequest(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt, analysis_goal=analysis_goal)


def create_failure_result(
    status: str,
    analysis_goal: str,
    error: str,
    output_dir: Path,
    provider: LLMProvider,
    is_mock: bool,
    eligible_issue_count: int,
) -> FindingGenerationResult:
    validation = FindingValidationResult(status="SKIPPED", passed=False, errors=[error])
    result = FindingGenerationResult(
        generation_status=status,
        generation_passed=False,
        raw_output="",
        validation=validation,
        findings=[],
        evidence_reports=[],
        provider=getattr(provider, "provider_name", None),
        model=getattr(provider, "model", None),
        analysis_goal=analysis_goal,
        eligible_issue_count=eligible_issue_count,
        saved_paths={},
        error=error,
        is_mock=is_mock,
    )
    save_finding_outputs(result, output_dir=output_dir)
    return result


def save_finding_outputs(
    result: FindingGenerationResult,
    *,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "finding_generation_raw.json"
    findings_path = output_dir / "findings.json"
    validation_path = output_dir / "finding_validation.json"
    evidence_path = output_dir / "evidence_report.json"
    raw_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "provider": result.provider,
                "model": result.model,
                "is_mock": result.is_mock,
                "analysis_goal": result.analysis_goal,
                "generation_status": result.generation_status,
                "raw_output": result.raw_output,
                "extracted_json": result.extracted_json,
                "response_metadata": result.response_metadata or {},
                "error": result.error,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    findings_path.write_text(json.dumps({"findings": result.findings}, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    evidence_path.write_text(
        json.dumps({"evidence_reports": result.evidence_reports}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths = {"raw": raw_path, "findings": findings_path, "validation": validation_path, "evidence": evidence_path}
    result.saved_paths = {key: str(path) for key, path in paths.items()}
    return paths
