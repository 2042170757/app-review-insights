"""Mock roadmap planning for Phase 5a."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.llm.base import LLMProvider, LLMRequest, LLMResponse
from app.llm.mock_provider import MockLLMProvider
from app.roadmap_validator import RoadmapValidationResult, validate_roadmap_output


DEFAULT_REQUIREMENTS_PATH = Path("artifacts/analysis/requirements.json")
DEFAULT_REQUIREMENT_VALIDATION_PATH = Path("artifacts/analysis/requirement_validation.json")
DEFAULT_PRIORITY_REPORT_PATH = Path("artifacts/analysis/priority_report.json")


@dataclass
class RoadmapPlanningResult:
    generation_status: str
    generation_passed: bool
    raw_output: str
    validation: RoadmapValidationResult
    roadmap: dict[str, Any]
    provider: str | None
    model: str | None
    saved_paths: dict[str, str]
    is_mock: bool = True


def plan_roadmap(
    *,
    requirements: list[dict[str, Any]],
    requirement_validation: dict[str, Any],
    priority_report: dict[str, Any],
    provider: LLMProvider,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
    is_mock: bool = True,
) -> RoadmapPlanningResult:
    request = LLMRequest(
        system_prompt="Phase 5a mock roadmap planning. Do not call a production model.",
        user_prompt="Generate mock roadmap and version planning from validated Requirements.",
        analysis_goal="mock_roadmap_planning",
    )
    response = provider.generate(request)
    requirements_by_id = {item["requirement_id"]: item for item in requirements if isinstance(item.get("requirement_id"), str)}
    validation_passed = requirement_validation.get("status") == "Success" and requirement_validation.get("passed") is True
    priority_by_requirement_id = _priority_by_requirement_id(priority_report, requirements_by_id)
    validation = validate_roadmap_output(
        response.raw_text,
        requirements_by_id=requirements_by_id,
        requirement_validation_passed=validation_passed,
        priority_by_requirement_id=priority_by_requirement_id,
    )
    roadmap = _roadmap_from_validation(validation) if validation.passed else {"versions": [], "roadmap_items": []}
    result = RoadmapPlanningResult(
        generation_status="Success" if validation.passed else validation.status,
        generation_passed=validation.passed,
        raw_output=response.raw_text,
        validation=validation,
        roadmap=roadmap,
        provider=response.provider,
        model=response.model,
        saved_paths={},
        is_mock=is_mock,
    )
    save_roadmap_outputs(result, output_dir=output_dir)
    return result


def build_default_mock_output(requirements: list[dict[str, Any]]) -> str:
    versions = [
        {
            "version_id": "V1",
            "name": "Highest priority product corrections",
            "goal": "Address the highest-priority validated product problems first.",
            "requirement_ids": [],
            "rationale": "V1 contains P1 requirements that can be delivered without roadmap dependency conflicts.",
            "risks": [],
            "success_metrics": [],
        },
        {
            "version_id": "V2",
            "name": "Experience follow-up improvements",
            "goal": "Address remaining validated product problems with lower roadmap urgency.",
            "requirement_ids": [],
            "rationale": "V2 contains remaining non-deferred requirements.",
            "risks": [],
            "success_metrics": [],
        },
        {
            "version_id": "V3",
            "name": "Reserved future planning",
            "goal": "Reserved for validated work that is not required in the first two versions.",
            "requirement_ids": [],
            "rationale": "No mock requirement currently requires V3.",
            "risks": [],
            "success_metrics": [],
        },
        {
            "version_id": "Deferred",
            "name": "Deferred",
            "goal": "Explicitly hold requirements that should not be scheduled now.",
            "requirement_ids": [],
            "rationale": "Deferred keeps every validated requirement explicitly assigned.",
            "risks": [],
            "success_metrics": [],
        },
    ]
    version_by_id = {version["version_id"]: version for version in versions}
    roadmap_items = []
    for requirement in requirements:
        requirement_id = requirement.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id:
            continue
        version_id = "V1" if requirement.get("priority") in {"P0", "P1"} else "V2"
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
    return json.dumps({"versions": versions, "roadmap_items": roadmap_items}, ensure_ascii=False)


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
                "generation_status": result.generation_status,
                "raw_output": result.raw_output,
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


def _roadmap_from_validation(validation: RoadmapValidationResult) -> dict[str, Any]:
    return {
        "versions": [version.__dict__ for version in validation.versions],
        "roadmap_items": validation.roadmap_items,
    }
