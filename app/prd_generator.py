"""Mock PRD generation orchestration for Phase 6a."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.llm.base import LLMProvider, LLMRequest
from app.llm.mock_provider import MockLLMProvider
from app.prd_validator import (
    PRDValidationResult,
    STATUS_INVALID_JSON,
    STATUS_SCHEMA_VALIDATION_FAILED,
    validate_prd_output,
)
from app.topic_discovery import extract_json_text


DEFAULT_PRD_GOAL = "分析低评分用户对订阅和价格的主要问题"
STATUS_SUCCESS = "Success"
STATUS_INPUT_VALIDATION_FAILED = "Input Validation Failed"


@dataclass
class PRDGenerationResult:
    generation_status: str
    generation_passed: bool
    raw_output: str
    validation: PRDValidationResult
    prds: list[dict[str, Any]]
    provider: str | None
    model: str | None
    analysis_goal: str
    saved_paths: dict[str, str]
    extracted_json: str | None = None
    error: str | None = None
    is_mock: bool = True


def generate_prds(
    *,
    requirements: list[dict[str, Any]],
    requirement_validation: dict[str, Any],
    roadmap: dict[str, Any],
    roadmap_validation: dict[str, Any],
    findings: list[dict[str, Any]],
    finding_validation: dict[str, Any],
    issues: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    provider: LLMProvider,
    analysis_goal: str = DEFAULT_PRD_GOAL,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
    is_mock: bool = True,
) -> PRDGenerationResult:
    requirement_passed = _validation_passed(requirement_validation)
    roadmap_passed = _validation_passed(roadmap_validation)
    finding_passed = _validation_passed(finding_validation)
    if not (requirement_passed and roadmap_passed and finding_passed):
        return create_failure_result(
            STATUS_INPUT_VALIDATION_FAILED,
            "Requirement, Roadmap, and Finding validation must all be PASS before PRD generation.",
            provider,
            analysis_goal,
            output_dir,
            is_mock,
        )

    request = LLMRequest(
        system_prompt="Phase 6a mock PRD generation. Do not call a production model.",
        user_prompt=json.dumps(
            {
                "analysis_goal": analysis_goal,
                "validated_versions": roadmap.get("versions", []),
                "validated_requirements": requirements,
                "note": "Mock-only PRD generation for schema and validator coverage.",
            },
            ensure_ascii=False,
        ),
        analysis_goal=analysis_goal,
    )
    response = provider.generate(request)
    extracted_json = extract_json_text(response.raw_text)
    validation = validate_prd_output(
        extracted_json,
        requirements_by_id=_by_id(requirements, "requirement_id"),
        versions_by_id=_by_id(roadmap.get("versions", []), "version_id"),
        findings_by_id=_by_id(findings, "finding_id"),
        issues_by_id=_by_id(issues, "issue_id"),
        topics_by_id=_by_id(topics, "topic_id"),
        valid_review_ids=set(_by_id(reviews, "id")),
        requirement_validation_passed=requirement_passed,
        roadmap_validation_passed=roadmap_passed,
        finding_validation_passed=finding_passed,
    )
    prds = [asdict(prd) for prd in validation.prds] if validation.passed else []
    generation_passed = validation.status not in {
        STATUS_INVALID_JSON,
        STATUS_SCHEMA_VALIDATION_FAILED,
    }
    result = PRDGenerationResult(
        generation_status=STATUS_SUCCESS if generation_passed else validation.status,
        generation_passed=generation_passed,
        raw_output=response.raw_text,
        validation=validation,
        prds=prds,
        provider=response.provider,
        model=response.model,
        analysis_goal=analysis_goal,
        saved_paths={},
        extracted_json=extracted_json,
        is_mock=is_mock,
    )
    save_prd_outputs(result, output_dir=output_dir)
    return result


def build_default_mock_output(
    *,
    roadmap: dict[str, Any],
    requirements: list[dict[str, Any]],
) -> str:
    requirements_by_id = _by_id(requirements, "requirement_id")
    prds: list[dict[str, Any]] = []
    for version in roadmap.get("versions", []):
        version_id = version.get("version_id")
        if not isinstance(version_id, str) or version_id == "Deferred":
            continue
        requirement_ids = [
            requirement_id
            for requirement_id in version.get("requirement_ids", [])
            if isinstance(requirement_id, str) and requirement_id in requirements_by_id
        ]
        if not requirement_ids:
            continue
        finding_ids = sorted(
            {
                finding_id
                for requirement_id in requirement_ids
                for finding_id in requirements_by_id[requirement_id].get("finding_ids", [])
                if isinstance(finding_id, str)
            }
        )
        goals = [_text(version.get("goal"))]
        evidence_refs = requirement_ids[:2] + finding_ids[:2]
        prds.append(
            {
                "prd_id": f"PRD-{version_id}",
                "version_id": version_id,
                "title": f"{_text(version.get('name'))} PRD",
                "overview": f"Define the product scope for {version_id}: {_text(version.get('name'))}.",
                "problem_statement": f"This PRD addresses validated user problems assigned to {version_id}.",
                "evidence_summary": "Evidence is traceable through "
                + ", ".join(evidence_refs)
                + ".",
                "goals": goals,
                "non_goals": ["Do not expand scope beyond the validated requirements in this version."],
                "requirement_ids": requirement_ids,
                "risks": list(version.get("risks", [])),
                "success_metrics": _metrics_for_version(version),
                "open_questions": _open_questions_for_requirements(requirement_ids),
            }
        )
    return json.dumps({"prds": prds}, ensure_ascii=False)


def create_mock_provider(raw_output: str) -> MockLLMProvider:
    return MockLLMProvider(raw_output, model="mock-prd-model")


def create_failure_result(
    status: str,
    error: str,
    provider: LLMProvider,
    analysis_goal: str,
    output_dir: Path,
    is_mock: bool,
) -> PRDGenerationResult:
    validation = PRDValidationResult(status="SKIPPED", passed=False, errors=[error])
    result = PRDGenerationResult(
        generation_status=status,
        generation_passed=False,
        raw_output="",
        validation=validation,
        prds=[],
        provider=getattr(provider, "provider_name", None),
        model=getattr(provider, "model", None),
        analysis_goal=analysis_goal,
        saved_paths={},
        error=error,
        is_mock=is_mock,
    )
    save_prd_outputs(result, output_dir=output_dir)
    return result


def save_prd_outputs(
    result: PRDGenerationResult,
    *,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "prd_generation_raw.json"
    prds_path = output_dir / "prds.json"
    validation_path = output_dir / "prd_validation.json"
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
                "error": result.error,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    prds_path.write_text(json.dumps({"prds": result.prds}, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    paths = {"raw": raw_path, "prds": prds_path, "validation": validation_path}
    result.saved_paths = {key: str(path) for key, path in paths.items()}
    return paths


def _metrics_for_version(version: dict[str, Any]) -> list[str]:
    metrics = [_text(item) for item in version.get("success_metrics", []) if _text(item)]
    if metrics:
        return metrics
    return ["Decrease in future negative reviews linked to this version's requirements."]


def _open_questions_for_requirements(requirement_ids: list[str]) -> list[str]:
    questions = []
    if "REQ-001" in requirement_ids:
        questions.append("Confirm the product scope for any free access threshold before delivery.")
    if "REQ-007" in requirement_ids:
        questions.append("Confirm the content refresh cadence with the product team.")
    if "REQ-008" in requirement_ids:
        questions.append("Confirm which support channels are appropriate for users.")
    return questions


def _validation_passed(payload: dict[str, Any]) -> bool:
    return payload.get("status") == "Success" and payload.get("passed") is True


def _by_id(items: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    return {
        item[key]: item
        for item in items
        if isinstance(item, dict) and isinstance(item.get(key), str) and item.get(key)
    }


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
