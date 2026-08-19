"""PRD generation CLI for mock and DeepSeek providers."""

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
from app.prd_generator import (
    DEFAULT_PRD_GOAL,
    build_default_mock_output,
    create_failure_result,
    create_mock_provider,
    generate_prds,
)


DEFAULT_REQUIREMENTS_PATH = Path("artifacts/analysis/requirements.json")
DEFAULT_REQUIREMENT_VALIDATION_PATH = Path("artifacts/analysis/requirement_validation.json")
DEFAULT_ROADMAP_PATH = Path("artifacts/analysis/roadmap.json")
DEFAULT_ROADMAP_VALIDATION_PATH = Path("artifacts/analysis/roadmap_validation.json")
DEFAULT_FINDINGS_PATH = Path("artifacts/analysis/findings.json")
DEFAULT_FINDING_VALIDATION_PATH = Path("artifacts/analysis/finding_validation.json")
DEFAULT_EVIDENCE_REPORT_PATH = Path("artifacts/analysis/evidence_report.json")
DEFAULT_ISSUES_PATH = Path("artifacts/analysis/issues.json")
DEFAULT_TOPICS_PATH = Path("artifacts/analysis/topics.json")
DEFAULT_REVIEWS_PATH = Path("artifacts/processed/reviews.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="PRD generation from validated Roadmap Versions.")
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS_PATH)
    parser.add_argument("--requirement-validation", type=Path, default=DEFAULT_REQUIREMENT_VALIDATION_PATH)
    parser.add_argument("--roadmap", type=Path, default=DEFAULT_ROADMAP_PATH)
    parser.add_argument("--roadmap-validation", type=Path, default=DEFAULT_ROADMAP_VALIDATION_PATH)
    parser.add_argument("--findings", type=Path, default=DEFAULT_FINDINGS_PATH)
    parser.add_argument("--finding-validation", type=Path, default=DEFAULT_FINDING_VALIDATION_PATH)
    parser.add_argument("--evidence-report", type=Path, default=DEFAULT_EVIDENCE_REPORT_PATH)
    parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES_PATH)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS_PATH)
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS_PATH)
    parser.add_argument("--provider", choices=["mock", "deepseek"], default="mock")
    parser.add_argument("--goal", default=DEFAULT_PRD_GOAL)
    parser.add_argument("--mock-output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    args = parser.parse_args()

    load_dotenv(override=False)
    requirements = load_requirements(args.requirements)
    requirement_validation = load_validation(args.requirement_validation, "Requirement validation")
    roadmap = load_object(args.roadmap, "Roadmap")
    roadmap_validation = load_validation(args.roadmap_validation, "Roadmap validation")
    findings = load_findings(args.findings)
    finding_validation = load_validation(args.finding_validation, "Finding validation")
    evidence_report = load_validation(args.evidence_report, "Evidence report")
    issues = load_issues(args.issues)
    topics = load_topics(args.topics)
    reviews = load_reviews(args.reviews)
    if args.provider == "mock":
        raw_output = (
            args.mock_output.read_text(encoding="utf-8")
            if args.mock_output
            else build_default_mock_output(roadmap=roadmap, requirements=requirements)
        )
        provider = create_mock_provider(raw_output)
        result = generate_prds(
            requirements=requirements,
            requirement_validation=requirement_validation,
            roadmap=roadmap,
            roadmap_validation=roadmap_validation,
            findings=findings,
            finding_validation=finding_validation,
            evidence_report=evidence_report,
            issues=issues,
            topics=topics,
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
                provider_info,
                args.goal,
                args.output_dir,
                False,
            )
        else:
            result = generate_prds(
                requirements=requirements,
                requirement_validation=requirement_validation,
                roadmap=roadmap,
                roadmap_validation=roadmap_validation,
                findings=findings,
                finding_validation=finding_validation,
                evidence_report=evidence_report,
                issues=issues,
                topics=topics,
                reviews=reviews,
                provider=provider,
                analysis_goal=args.goal,
                output_dir=args.output_dir,
                is_mock=False,
            )

    if result.generation_passed:
        print(stage_result("PRD Generation", "PASS"))
    else:
        print(stage_result("PRD Generation", "FAIL"))
        print(line("Failure Type", result.generation_status))
    print(line("Provider", result.provider))
    print(line("Model", result.model))
    print(line("PRD Count", len(result.prds)))
    print(line("Validation", "PASS" if result.validation.passed else "FAIL"))
    if not result.validation.passed:
        print(line("Validation Status", result.validation.status))
    for prd in result.prds:
        print(f"prd_id: {prd['prd_id']}")
        print(f"version_id: {prd['version_id']}")
        print(f"title: {prd['title']}")
        print(f"requirement_count: {len(prd['requirement_ids'])}")
        print(f"goal_count: {len(prd['goals'])}")
        print(f"non_goal_count: {len(prd['non_goals'])}")
        print(f"open_question_count: {len(prd['open_questions'])}")
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


def load_findings(path: Path = DEFAULT_FINDINGS_PATH) -> list[dict]:
    payload = load_object(path, "Findings")
    findings = payload.get("findings")
    if not isinstance(findings, list) or not all(isinstance(item, dict) for item in findings):
        raise ValueError(f"Findings file is invalid: {path}")
    return list(findings)


def load_issues(path: Path = DEFAULT_ISSUES_PATH) -> list[dict]:
    payload = load_object(path, "Issues")
    issues = payload.get("issues")
    if not isinstance(issues, list) or not all(isinstance(item, dict) for item in issues):
        raise ValueError(f"Issues file is invalid: {path}")
    return list(issues)


def load_topics(path: Path = DEFAULT_TOPICS_PATH) -> list[dict]:
    payload = load_object(path, "Topics")
    topics = payload.get("topics")
    if not isinstance(topics, list) or not all(isinstance(item, dict) for item in topics):
        raise ValueError(f"Topics file is invalid: {path}")
    return list(topics)


def load_reviews(path: Path = DEFAULT_REVIEWS_PATH) -> list[dict]:
    payload = load_object(path, "Reviews")
    reviews = payload.get("reviews")
    if not isinstance(reviews, list) or not all(isinstance(item, dict) for item in reviews):
        raise ValueError(f"Reviews file is invalid: {path}")
    return list(reviews)


def load_validation(path: Path, label: str) -> dict:
    return load_object(path, label)


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
