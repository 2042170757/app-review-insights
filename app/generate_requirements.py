"""Requirement generation CLI for mock and DeepSeek providers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.analysis_intent import DEFAULT_ANALYSIS_FOCUS, normalize_analysis_focus
from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.llm.base import MissingAPIKeyError, ModelRequestError
from app.llm.deepseek_provider import DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL
from app.llm.mock_provider import MockLLMProvider
from app.llm.provider import build_production_provider
from app.requirement_generation import (
    DEFAULT_REQUIREMENT_GOAL,
    RequirementGenerationResult,
    create_failure_result,
    generate_requirements,
    save_requirement_outputs,
)


DEFAULT_FINDINGS_PATH = Path("artifacts/analysis/findings.json")
DEFAULT_FINDING_VALIDATION_PATH = Path("artifacts/analysis/finding_validation.json")
DEFAULT_EVIDENCE_REPORT_PATH = Path("artifacts/analysis/evidence_report.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Requirement generation from validated Findings.")
    parser.add_argument("--findings", type=Path, default=DEFAULT_FINDINGS_PATH)
    parser.add_argument("--finding-validation", type=Path, default=DEFAULT_FINDING_VALIDATION_PATH)
    parser.add_argument("--evidence-report", type=Path, default=DEFAULT_EVIDENCE_REPORT_PATH)
    parser.add_argument("--provider", choices=["mock", "deepseek"], default="mock")
    parser.add_argument("--goal", default=DEFAULT_REQUIREMENT_GOAL)
    parser.add_argument("--analysis-focus", default=DEFAULT_ANALYSIS_FOCUS)
    parser.add_argument("--mock-output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    args = parser.parse_args()

    load_dotenv(override=False)
    try:
        analysis_focus = normalize_analysis_focus(args.analysis_focus)
    except ValueError as exc:
        print("Requirement Generation: FAIL")
        print("Failure Type: Invalid Analysis Focus")
        print(f"Message: {exc}")
        return 1
    findings = load_findings(args.findings)
    finding_validation = load_finding_validation(args.finding_validation)
    evidence_report = load_evidence_report(args.evidence_report)

    if args.provider == "mock":
        raw_output = (
            args.mock_output.read_text(encoding="utf-8")
            if args.mock_output
            else build_default_mock_output(findings)
        )
        provider = MockLLMProvider(raw_output, model="mock-requirement-model")
        result = generate_requirements(
            findings=findings,
            finding_validation=finding_validation,
            evidence_report=evidence_report,
            provider=provider,
            analysis_goal=args.goal,
            analysis_focus=analysis_focus,
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
                args.goal,
                str(exc),
                args.output_dir,
                provider_info,
                False,
                len(findings),
                analysis_focus=analysis_focus,
            )
        else:
            result = generate_requirements(
                findings=findings,
                finding_validation=finding_validation,
                evidence_report=evidence_report,
                provider=provider,
                analysis_goal=args.goal,
                analysis_focus=analysis_focus,
                output_dir=args.output_dir,
                is_mock=False,
            )

    if result.generation_passed:
        print("Requirement Generation: PASS")
    else:
        print("Requirement Generation: FAIL")
        print(f"Failure Type: {result.generation_status}")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")
    print(f"Analysis Focus: {result.analysis_focus}")
    print(f"Requirement Count: {len(result.requirements)}")
    print(f"Input Findings: {result.input_finding_count}")
    print(f"Validation: {'PASS' if result.validation.passed else result.validation.status}")
    for requirement in result.requirements:
        print(f"requirement_id: {requirement['requirement_id']}")
        print(f"requirement_type: {requirement.get('requirement_type', 'problem')}")
        print(f"title: {requirement['title']}")
        print(f"finding_count: {len(requirement['finding_ids'])}")
        print(f"priority: {requirement['priority']}")
        print(f"priority_rationale: {requirement['priority_rationale']}")
        print(f"acceptance_criteria_count: {len(requirement['acceptance_criteria'])}")
        print(f"uncertainty: {requirement['uncertainty']}")
    for error in result.validation.errors:
        print(f"- {error}")
    print("Output files:")
    for label, path in result.saved_paths.items():
        print(f"{label}: {path}")
    return 0 if result.generation_passed and result.validation.passed else 1


def load_findings(path: Path = DEFAULT_FINDINGS_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    findings = payload.get("findings") if isinstance(payload, dict) else None
    if not isinstance(findings, list) or not all(isinstance(finding, dict) for finding in findings):
        raise ValueError(f"Findings file is invalid: {path}")
    return list(findings)


def load_finding_validation(path: Path = DEFAULT_FINDING_VALIDATION_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Finding validation file is invalid: {path}")
    return payload


def load_evidence_report(path: Path = DEFAULT_EVIDENCE_REPORT_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Evidence report file is invalid: {path}")
    return payload


def build_default_mock_output(findings: list[dict]) -> str:
    finding = findings[0] if findings else None
    if not finding:
        return json.dumps({"requirements": []})
    requirement = {
        "requirement_id": "REQ-001",
        "requirement_type": "positive_feedback" if finding.get("finding_type") == "positive_feedback" else "problem",
        "finding_ids": [finding["finding_id"]],
        "title": f"Address {finding.get('title', 'validated finding')}",
        "description": f"Define a product behavior that addresses the validated finding: {finding.get('statement', '')}",
        "acceptance_criteria": [
            "Before a user commits to the relevant flow, the experience clearly communicates the condition, cost, or limitation described by the finding.",
            "Users can complete the relevant decision point without relying on hidden or ambiguous wording.",
        ],
        "priority": "P1",
        "priority_rationale": "Priority is included for schema validation only; final priority calculation is deferred.",
        "risks": ["Requirement may need refinement after product scoping."],
        "success_metrics": ["Reduction in future reviews matching the referenced finding."],
        "uncertainty": "Mock requirement generated for schema and validator coverage only.",
        "source_review_ids": finding.get("review_ids", []),
    }
    return json.dumps({"requirements": [requirement]}, ensure_ascii=False)


def save_outputs(
    *,
    raw_output: str,
    validation,
    requirements: list[dict],
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    result = RequirementGenerationResult(
        generation_status="Success" if validation.passed else validation.status,
        generation_passed=validation.passed,
        raw_output=raw_output,
        validation=validation,
        requirements=requirements,
        priority_report=[],
        provider="mock",
        model="mock-requirement-model",
        analysis_goal="mock_requirement_generation",
        input_finding_count=0,
        saved_paths={},
        is_mock=True,
    )
    return save_requirement_outputs(result, output_dir=output_dir)


class _ProviderInfo:
    def __init__(self, *, provider_name: str, model: str) -> None:
        self.provider_name = provider_name
        self.model = model

    def generate(self, request):
        raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
