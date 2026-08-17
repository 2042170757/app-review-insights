"""Mock roadmap generation CLI for Phase 5a."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.roadmap_planner import (
    DEFAULT_PRIORITY_REPORT_PATH,
    DEFAULT_REQUIREMENT_VALIDATION_PATH,
    DEFAULT_REQUIREMENTS_PATH,
    build_default_mock_output,
    create_mock_provider,
    plan_roadmap,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock roadmap and version planning.")
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS_PATH)
    parser.add_argument("--requirement-validation", type=Path, default=DEFAULT_REQUIREMENT_VALIDATION_PATH)
    parser.add_argument("--priority-report", type=Path, default=DEFAULT_PRIORITY_REPORT_PATH)
    parser.add_argument("--mock-output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    args = parser.parse_args()

    requirements = load_requirements(args.requirements)
    requirement_validation = load_requirement_validation(args.requirement_validation)
    priority_report = load_priority_report(args.priority_report)
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
        provider=provider,
        output_dir=args.output_dir,
        is_mock=True,
    )

    if result.generation_passed:
        print("Roadmap Generation: PASS")
    else:
        print("Roadmap Generation: FAIL")
        print(f"Failure Type: {result.generation_status}")
    print("Provider: mock")
    print(f"Version Count: {len(result.roadmap.get('versions', []))}")
    print(f"Roadmap Item Count: {len(result.roadmap.get('roadmap_items', []))}")
    print(f"Deferred Count: {len(result.validation.deferred_requirement_ids)}")
    print(f"Validation: {'PASS' if result.validation.passed else 'FAIL'}")
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


if __name__ == "__main__":
    raise SystemExit(main())
