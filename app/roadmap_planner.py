"""Roadmap planning for mock and production LLM providers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from app.llm.mock_provider import MockLLMProvider
from app.roadmap_validator import (
    STATUS_INVALID_JSON,
    STATUS_SCHEMA_VALIDATION_FAILED,
    RoadmapValidationResult,
    validate_roadmap_output,
)
from app.topic_discovery import extract_json_text


DEFAULT_REQUIREMENTS_PATH = Path("artifacts/analysis/requirements.json")
DEFAULT_REQUIREMENT_VALIDATION_PATH = Path("artifacts/analysis/requirement_validation.json")
DEFAULT_PRIORITY_REPORT_PATH = Path("artifacts/analysis/priority_report.json")
DEFAULT_EVIDENCE_REPORT_PATH = Path("artifacts/analysis/evidence_report.json")
DEFAULT_ROADMAP_VALIDATION_PATH = Path("artifacts/analysis/roadmap_validation.json")
DEFAULT_ROADMAP_GOAL = "分析低评分用户对订阅和价格的主要问题"


SYSTEM_PROMPT = """You are performing product-oriented Roadmap Planning from validated Requirements.

Rules:
1. The input Requirements have already passed validation.
2. Do not create new Requirements.
3. Do not delete Requirements; if a Requirement should not be scheduled, put it in deferred_requirement_ids.
4. Do not modify Requirement priority.
5. Do not modify Requirement content.
6. Do not invent new user problems.
7. Do not invent new Evidence.
8. Do not change existing dependencies.
9. Organize the roadmap by product goals and user value, not by simple priority buckets.
10. Requirements in the same Version should have a strong product theme or goal.
11. A Version may contain mixed priorities if the product goal is coherent.
12. A Requirement may be deferred.
13. Do not create empty Versions.
14. Each Version must have name, goal, and rationale.
15. Version goals must summarize the internal Requirements.
16. Version rationale must explain why those Requirements belong together.
17. Do not generate PRDs.
18. Do not generate technical implementation plans.
19. Do not generate Test Cases.

Return only JSON matching the required Roadmap schema."""


@dataclass
class RoadmapPlanningResult:
    generation_status: str
    generation_passed: bool
    raw_output: str
    validation: RoadmapValidationResult
    roadmap: dict[str, Any]
    provider: str | None
    model: str | None
    analysis_goal: str
    saved_paths: dict[str, str]
    error: str | None = None
    extracted_json: str | None = None
    response_metadata: dict[str, Any] | None = None
    is_mock: bool = True


def plan_roadmap(
    *,
    requirements: list[dict[str, Any]],
    requirement_validation: dict[str, Any],
    priority_report: dict[str, Any],
    evidence_report: dict[str, Any] | None = None,
    existing_roadmap_validation: dict[str, Any] | None = None,
    provider: LLMProvider,
    analysis_goal: str = DEFAULT_ROADMAP_GOAL,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
    is_mock: bool = True,
) -> RoadmapPlanningResult:
    requirements_by_id = {item["requirement_id"]: item for item in requirements if isinstance(item.get("requirement_id"), str)}
    validation_passed = requirement_validation.get("status") == "Success" and requirement_validation.get("passed") is True
    priority_by_requirement_id = _priority_by_requirement_id(priority_report, requirements_by_id)
    existing_dependencies = _existing_dependencies(existing_roadmap_validation)
    if not validation_passed:
        return create_failure_result(
            "Requirement Validation Failed",
            "Requirement validation is not PASS; Roadmap generation skipped.",
            provider,
            analysis_goal,
            output_dir,
            is_mock,
        )
    request = build_roadmap_request(
        requirements=requirements,
        priority_report=priority_report,
        evidence_report=evidence_report or {},
        existing_dependencies_by_requirement_id=existing_dependencies,
        analysis_goal=analysis_goal,
    )
    try:
        response = provider.generate(request)
    except MissingAPIKeyError as exc:
        return create_failure_result("Missing API Key", str(exc), provider, analysis_goal, output_dir, is_mock)
    except ModelAuthenticationError as exc:
        return create_failure_result("Authentication Error", str(exc), provider, analysis_goal, output_dir, is_mock)
    except ModelRateLimitError as exc:
        return create_failure_result("Rate Limit", str(exc), provider, analysis_goal, output_dir, is_mock)
    except ModelTimeoutError as exc:
        return create_failure_result("Timeout", str(exc), provider, analysis_goal, output_dir, is_mock)
    except ModelRequestError as exc:
        return create_failure_result("Model Request Error", str(exc), provider, analysis_goal, output_dir, is_mock)

    extracted_json = extract_json_text(response.raw_text)
    validation = validate_roadmap_output(
        extracted_json,
        requirements_by_id=requirements_by_id,
        requirement_validation_passed=validation_passed,
        priority_by_requirement_id=priority_by_requirement_id,
        existing_dependencies_by_requirement_id=existing_dependencies,
    )
    roadmap = _roadmap_from_validation(validation) if validation.passed else {"versions": [], "roadmap_items": []}
    generation_passed = validation.status not in {
        STATUS_INVALID_JSON,
        STATUS_SCHEMA_VALIDATION_FAILED,
    }
    result = RoadmapPlanningResult(
        generation_status="Success" if generation_passed else validation.status,
        generation_passed=generation_passed,
        raw_output=response.raw_text,
        validation=validation,
        roadmap=roadmap,
        provider=response.provider,
        model=response.model,
        analysis_goal=analysis_goal,
        saved_paths={},
        extracted_json=extracted_json,
        response_metadata=response.metadata,
        is_mock=is_mock,
    )
    save_roadmap_outputs(result, output_dir=output_dir)
    return result


def build_roadmap_request(
    *,
    requirements: list[dict[str, Any]],
    priority_report: dict[str, Any],
    evidence_report: dict[str, Any],
    existing_dependencies_by_requirement_id: dict[str, list[str]],
    analysis_goal: str,
) -> LLMRequest:
    priority_by_id = {
        item["requirement_id"]: item
        for item in priority_report.get("priority_report", [])
        if isinstance(item, dict) and isinstance(item.get("requirement_id"), str)
    }
    evidence_by_finding = {
        item["finding_id"]: item
        for item in evidence_report.get("evidence_reports", [])
        if isinstance(item, dict) and isinstance(item.get("finding_id"), str)
    }
    requirement_payload = []
    for requirement in requirements:
        requirement_id = requirement.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id:
            continue
        finding_ids = requirement.get("finding_ids") if isinstance(requirement.get("finding_ids"), list) else []
        requirement_payload.append(
            {
                "requirement_id": requirement_id,
                "title": requirement.get("title"),
                "description": requirement.get("description"),
                "finding_ids": finding_ids,
                "priority": requirement.get("priority"),
                "priority_report": priority_by_id.get(requirement_id),
                "acceptance_criteria": requirement.get("acceptance_criteria"),
                "risks": requirement.get("risks"),
                "success_metrics": requirement.get("success_metrics"),
                "uncertainty": requirement.get("uncertainty"),
                "evidence_reports": [evidence_by_finding[finding_id] for finding_id in finding_ids if finding_id in evidence_by_finding],
                "existing_dependencies": existing_dependencies_by_requirement_id.get(requirement_id, []),
            }
        )
    user_prompt = json.dumps(
        {
            "analysis_goal": analysis_goal,
            "validated_requirements": requirement_payload,
            "valid_requirement_ids": sorted(item["requirement_id"] for item in requirement_payload),
            "existing_dependencies_by_requirement_id": existing_dependencies_by_requirement_id,
            "required_output_schema": {
                "versions": [
                    {
                        "version_id": "V1",
                        "name": "string",
                        "goal": "string",
                        "requirement_ids": ["REQ-001"],
                        "rationale": "string",
                        "risks": [],
                        "success_metrics": [],
                    }
                ],
                "roadmap_items": [
                    {
                        "requirement_id": "REQ-001",
                        "version_id": "V1",
                        "priority": "P1",
                        "rationale": "string",
                        "dependencies": [],
                    }
                ],
                "deferred_requirement_ids": [],
                "deferred_rationale": {},
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    return LLMRequest(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt, analysis_goal=analysis_goal)


def build_default_mock_output(requirements: list[dict[str, Any]]) -> str:
    versions = [
        _version("V1", "Subscription and billing clarity", "Improve subscription access, value communication, billing transparency, and cancellation trust."),
        _version("V2", "Workout content experience", "Improve workout content quality, realism, customization, and freshness."),
        _version("V3", "Operational friction reduction", "Reduce support and advertising interruptions that block successful app use."),
    ]
    version_by_id = {version["version_id"]: version for version in versions}
    roadmap_items = []
    for requirement in requirements:
        requirement_id = requirement.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id:
            continue
        version_id = _mock_version_for_requirement(requirement)
        version_by_id[version_id]["requirement_ids"].append(requirement_id)
        roadmap_items.append(
            {
                "requirement_id": requirement_id,
                "version_id": version_id,
                "priority": requirement.get("priority"),
                "rationale": "Mock roadmap assignment preserves validated priority and schedules all validated requirements.",
                "dependencies": [],
            }
        )
    versions = [version for version in versions if version["requirement_ids"]]
    return json.dumps(
        {
            "versions": versions,
            "roadmap_items": roadmap_items,
            "deferred_requirement_ids": [],
            "deferred_rationale": {},
        },
        ensure_ascii=False,
    )


def create_failure_result(
    status: str,
    error: str,
    provider: LLMProvider,
    analysis_goal: str,
    output_dir: Path,
    is_mock: bool,
) -> RoadmapPlanningResult:
    validation = RoadmapValidationResult(status="SKIPPED", passed=False, errors=[error])
    result = RoadmapPlanningResult(
        generation_status=status,
        generation_passed=False,
        raw_output="",
        validation=validation,
        roadmap={"versions": [], "roadmap_items": []},
        provider=getattr(provider, "provider_name", None),
        model=getattr(provider, "model", None),
        analysis_goal=analysis_goal,
        saved_paths={},
        error=error,
        is_mock=is_mock,
    )
    save_roadmap_outputs(result, output_dir=output_dir)
    return result


def save_roadmap_outputs(
    result: RoadmapPlanningResult,
    *,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "roadmap_generation_raw.json"
    roadmap_path = output_dir / "roadmap.json"
    validation_path = output_dir / "roadmap_validation.json"
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
    roadmap_path.write_text(json.dumps(result.roadmap, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    paths = {"raw": raw_path, "roadmap": roadmap_path, "validation": validation_path}
    result.saved_paths = {key: str(path) for key, path in paths.items()}
    return paths


def create_mock_provider(raw_output: str) -> MockLLMProvider:
    return MockLLMProvider(raw_output, model="mock-roadmap-model")


def _version(version_id: str, name: str, goal: str) -> dict[str, Any]:
    return {
        "version_id": version_id,
        "name": name,
        "goal": goal,
        "requirement_ids": [],
        "rationale": f"{name} groups Requirements by product goal rather than priority alone.",
        "risks": [],
        "success_metrics": [],
    }


def _mock_version_for_requirement(requirement: dict[str, Any]) -> str:
    text = f"{requirement.get('title', '')} {requirement.get('description', '')}".lower()
    if any(term in text for term in ["free", "subscription", "billing", "cancellation", "paywall"]):
        return "V1"
    if any(term in text for term in ["workout", "imagery", "content", "customization"]):
        return "V2"
    if requirement.get("priority") in {"P0", "P1"}:
        return "V1"
    if requirement.get("priority") == "P2":
        return "V2"
    return "V3"


def _priority_by_requirement_id(
    priority_report: dict[str, Any],
    requirements_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    reports = priority_report.get("priority_report") if isinstance(priority_report, dict) else None
    result = {
        item["requirement_id"]: item["final_priority"]
        for item in reports or []
        if isinstance(item, dict) and isinstance(item.get("requirement_id"), str) and isinstance(item.get("final_priority"), str)
    }
    for requirement_id, requirement in requirements_by_id.items():
        result.setdefault(requirement_id, requirement.get("priority", ""))
    return result


def _existing_dependencies(roadmap_validation: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(roadmap_validation, dict):
        return {}
    items = roadmap_validation.get("roadmap_items")
    if not isinstance(items, list):
        return {}
    return {
        item["requirement_id"]: list(item.get("dependencies", []))
        for item in items
        if isinstance(item, dict) and isinstance(item.get("requirement_id"), str) and isinstance(item.get("dependencies"), list)
    }


def _roadmap_from_validation(validation: RoadmapValidationResult) -> dict[str, Any]:
    return {
        "versions": [version.__dict__ for version in validation.versions],
        "roadmap_items": validation.roadmap_items,
        "deferred_requirement_ids": validation.deferred_requirement_ids,
        "deferred_rationale": validation.deferred_rationale,
    }
