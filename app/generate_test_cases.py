"""Test case generation CLI for mock and DeepSeek providers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.cli_i18n import line, stage_result
from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.llm.base import MissingAPIKeyError, ModelRequestError
from app.llm.deepseek_provider import DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL
from app.llm.provider import build_production_provider
from app.test_case_generator import (
    build_default_mock_output,
    create_failure_result,
    create_mock_provider,
    generate_test_cases,
)


DEFAULT_REQUIREMENTS_PATH = Path("artifacts/analysis/requirements.json")
DEFAULT_REQUIREMENT_VALIDATION_PATH = Path("artifacts/analysis/requirement_validation.json")
DEFAULT_PRDS_PATH = Path("artifacts/analysis/prds.json")
DEFAULT_PRD_VALIDATION_PATH = Path("artifacts/analysis/prd_validation.json")
DEFAULT_ROADMAP_PATH = Path("artifacts/analysis/roadmap.json")
DEFAULT_ROADMAP_VALIDATION_PATH = Path("artifacts/analysis/roadmap_validation.json")
DEFAULT_FINDINGS_PATH = Path("artifacts/analysis/findings.json")
DEFAULT_REVIEWS_PATH = Path("artifacts/processed/reviews.json")
DEFAULT_TEST_CASE_GOAL = "为已验证需求和验收标准生成可执行测试用例"


def main() -> int:
    parser = argparse.ArgumentParser(description="Test case generation from validated Requirements and PRDs.")
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS_PATH)
    parser.add_argument("--requirement-validation", type=Path, default=DEFAULT_REQUIREMENT_VALIDATION_PATH)
    parser.add_argument("--prds", type=Path, default=DEFAULT_PRDS_PATH)
    parser.add_argument("--prd-validation", type=Path, default=DEFAULT_PRD_VALIDATION_PATH)
    parser.add_argument("--roadmap", type=Path, default=DEFAULT_ROADMAP_PATH)
    parser.add_argument("--roadmap-validation", type=Path, default=DEFAULT_ROADMAP_VALIDATION_PATH)
    parser.add_argument("--findings", type=Path, default=DEFAULT_FINDINGS_PATH)
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS_PATH)
    parser.add_argument("--provider", choices=["mock", "deepseek"], default="mock")
    parser.add_argument("--goal", default=DEFAULT_TEST_CASE_GOAL)
    parser.add_argument("--mock-output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    args = parser.parse_args()

    load_dotenv(override=False)
    requirements = load_requirements(args.requirements)
    requirement_validation = load_object(args.requirement_validation, "Requirement validation")
    prds = load_prds(args.prds)
    prd_validation = load_object(args.prd_validation, "PRD validation")
    roadmap = load_object(args.roadmap, "Roadmap")
    load_object(args.roadmap_validation, "Roadmap validation")
    findings = load_optional_findings(args.findings)
    reviews = load_optional_reviews(args.reviews)
    if args.provider == "mock":
        raw_output = (
            args.mock_output.read_text(encoding="utf-8")
            if args.mock_output
            else build_default_mock_output(requirements)
        )
        provider = create_mock_provider(raw_output)
        result = generate_test_cases(
            requirements=requirements,
            requirement_validation=requirement_validation,
            prd_validation=prd_validation,
            prds=prds,
            roadmap=roadmap,
            findings=findings,
            reviews=reviews,
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
                requirements,
                provider_info,
                args.goal,
                args.output_dir,
                False,
            )
        else:
            result = generate_test_cases(
                requirements=requirements,
                requirement_validation=requirement_validation,
                prd_validation=prd_validation,
                prds=prds,
                roadmap=roadmap,
                findings=findings,
                reviews=reviews,
                provider=provider,
                analysis_goal=args.goal,
                output_dir=args.output_dir,
                is_mock=False,
            )

    print(stage_result("Test Case Generation", "PASS" if result.generation_passed else "FAIL"))
    if not result.generation_passed:
        print(line("Failure Type", result.generation_status))
    print(line("Provider", result.provider))
    print(line("Model", result.model))
    print(line("Test Case Count", len(result.test_cases)))
    print(line("Total Requirements", result.coverage.total_requirements))
    print(line("Covered Requirements", result.coverage.covered_requirements))
    print(line("Requirement Coverage", f"{result.coverage.requirement_coverage:.1f}%"))
    print(line("Total Acceptance Criteria", result.coverage.total_acceptance_criteria))
    print(line("Covered Acceptance Criteria", result.coverage.covered_acceptance_criteria))
    print(line("Acceptance Criteria Coverage", f"{result.coverage.acceptance_criteria_coverage:.1f}%"))
    print(line("Validation", "PASS" if result.validation.passed else "FAIL"))
    if not result.validation.passed:
        print(line("Validation Status", result.validation.status))
    for error in result.validation.errors:
        print(f"- {error}")
    print("输出文件：")
    for label, path in result.saved_paths.items():
        print(f"{label}: {path}")
    return 0 if result.generation_passed and result.validation.passed else 1


def load_requirements(path: Path = DEFAULT_REQUIREMENTS_PATH) -> list[dict]:
    payload = load_object(path, "Requirements")
    requirements = payload.get("requirements")
    if not isinstance(requirements, list) or not all(isinstance(item, dict) for item in requirements):
        raise ValueError(f"Requirements file is invalid: {path}")
    return list(requirements)


def load_prds(path: Path = DEFAULT_PRDS_PATH) -> list[dict]:
    payload = load_object(path, "PRDs")
    prds = payload.get("prds")
    if not isinstance(prds, list) or not all(isinstance(item, dict) for item in prds):
        raise ValueError(f"PRDs file is invalid: {path}")
    return list(prds)


def load_optional_findings(path: Path = DEFAULT_FINDINGS_PATH) -> list[dict]:
    if not path.exists():
        return []
    payload = load_object(path, "Findings")
    findings = payload.get("findings")
    if not isinstance(findings, list) or not all(isinstance(item, dict) for item in findings):
        raise ValueError(f"Findings file is invalid: {path}")
    return list(findings)


def load_optional_reviews(path: Path = DEFAULT_REVIEWS_PATH) -> list[dict]:
    if not path.exists():
        return []
    payload = load_object(path, "Reviews")
    reviews = payload.get("reviews")
    if not isinstance(reviews, list) or not all(isinstance(item, dict) for item in reviews):
        raise ValueError(f"Reviews file is invalid: {path}")
    return list(reviews)


def load_object(path: Path, label: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} file is invalid: {path}")
    return payload


class _ProviderInfo:
    def __init__(self, *, provider_name: str, model: str) -> None:
        self.provider_name = provider_name
        self.model = model

    def generate(self, request):
        raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
