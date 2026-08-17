"""Roadmap generation CLI for mock and DeepSeek providers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.llm.base import MissingAPIKeyError, ModelRequestError
from app.llm.deepseek_provider import DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL
from app.llm.provider import build_production_provider
from app.roadmap_planner import (
    DEFAULT_EVIDENCE_REPORT_PATH,
    DEFAULT_PRIORITY_REPORT_PATH,
    DEFAULT_ROADMAP_GOAL,
    DEFAULT_ROADMAP_VALIDATION_PATH,
    DEFAULT_REQUIREMENT_VALIDATION_PATH,
    DEFAULT_REQUIREMENTS_PATH,
    build_default_mock_output,
    create_failure_result,
    create_mock_provider,
    plan_roadmap,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Roadmap and version planning.")
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS_PATH)
    parser.add_argument("--requirement-validation", type=Path, default=DEFAULT_REQUIREMENT_VALIDATION_PATH)
    parser.add_argument("--priority-report", type=Path, default=DEFAULT_PRIORITY_REPORT_PATH)
    parser.add_argument("--evidence-report", type=Path, default=DEFAULT_EVIDENCE_REPORT_PATH)
    parser.add_argument("--existing-roadmap-validation", type=Path, default=DEFAULT_ROADMAP_VALIDATION_PATH)
    parser.add_argument("--provider", choices=["mock", "deepseek"], default="mock")
    parser.add_argument("--goal", default=DEFAULT_ROADMAP_GOAL)
    parser.add_argument("--mock-output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    args = parser.parse_args()

    load_dotenv(override=False)
    requirements = load_requirements(args.requirements)
    requirement_validation = load_requirement_validation(args.requirement_validation)
    priority_report = load_priority_report(args.priority_report)
    evidence_report = load_evidence_report(args.evidence_report)
    existing_roadmap_validation = load_existing_roadmap_validation(args.existing_roadmap_validation)
    if args.provider == "mock":
        raw_output = (
            args.mock_output.read_text(encoding="utf-8")
            if args.mock_output
            else build_default_mock_output(requirements)
        )
        provider = create_mock_provider(raw_output)
        result = plan_roadmap(
            requirements=requirements,
            requirement_validation=requirement_validation,
            priority_report=priority_report,
            evidence_report=evidence_report,
            existing_roadmap_validation=existing_roadmap_validation,
            provider=provider,
            analysis_goal=args.goal,
            output_dir=args.output_dir,
            is_mock=True,
        )
    else:
        try:
            provider = build_production_provider()
        except (MissingAPIKeyError, ModelRequestError) as exc:
            provider_info = _ProviderInfo(
                provider_name="deepseek",
                model=os.environ.get(DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL),
            )
            result = create_failure_result(
                "Missing API Key" if isinstance(exc, MissingAPIKeyError) else "Model Request Error",
                str(exc),
                provider_info,
                args.goal,
                args.output_dir,
                False,
            )
        else:
            result = plan_roadmap(
                requirements=requirements,
                requirement_validation=requirement_validation,
                priority_report=priority_report,
                evidence_report=evidence_report,
                existing_roadmap_validation=existing_roadmap_validation,
                provider=provider,
                analysis_goal=args.goal,
                output_dir=args.output_dir,
                is_mock=False,
            )

    if result.generation_passed:
        print("Roadmap Generation: PASS")
    else:
        print("Roadmap Generation: FAIL")
        print(f"Failure Type: {result.generation_status}")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")
    print(f"Version Count: {len(result.roadmap.get('versions', []))}")
    print(f"Roadmap Item Count: {len(result.roadmap.get('roadmap_items', []))}")
    print(f"Deferred Count: {len(result.validation.deferred_requirement_ids)}")
    print(f"Validation: {'PASS' if result.validation.passed else result.validation.status}")
    for version in result.roadmap.get("versions", []):
        print(f"version_id: {version['version_id']}")
        print(f"name: {version['name']}")
        print(f"goal: {version['goal']}")
        print(f"requirement_ids: {version['requirement_ids']}")
        print(f"rationale: {version['rationale']}")
    for item in result.roadmap.get("roadmap_items", []):
        print(f"roadmap_item: {item['requirement_id']} {item['version_id']} {item['priority']}")
    for error in result.validation.errors:
        print(f"- {error}")
    print("Output files:")
    for label, path in result.saved_paths.items():
        print(f"{label}: {path}")
    return 0 if result.generation_passed and result.validation.passed else 1


def load_requirements(path: Path = DEFAULT_REQUIREMENTS_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    requirements = payload.get("requirements") if isinstance(payload, dict) else None
    if not isinstance(requirements, list) or not all(isinstance(requirement, dict) for requirement in requirements):
        raise ValueError(f"Requirements file is invalid: {path}")
    return list(requirements)


def load_requirement_validation(path: Path = DEFAULT_REQUIREMENT_VALIDATION_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Requirement validation file is invalid: {path}")
    return payload


def load_priority_report(path: Path = DEFAULT_PRIORITY_REPORT_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Priority report file is invalid: {path}")
    return payload


def load_evidence_report(path: Path = DEFAULT_EVIDENCE_REPORT_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Evidence report file is invalid: {path}")
    return payload


def load_existing_roadmap_validation(path: Path = DEFAULT_ROADMAP_VALIDATION_PATH) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Roadmap validation file is invalid: {path}")
    return payload


class _ProviderInfo:
    def __init__(self, *, provider_name: str, model: str) -> None:
        self.provider_name = provider_name
        self.model = model

    def generate(self, request):
        raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
