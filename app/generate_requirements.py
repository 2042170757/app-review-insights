"""Mock Requirement generation CLI for Phase 4a."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.llm.base import LLMRequest
from app.llm.mock_provider import MockLLMProvider
from app.requirement_validator import RequirementValidationResult, validate_requirement_output


DEFAULT_FINDINGS_PATH = Path("artifacts/analysis/findings.json")
DEFAULT_FINDING_VALIDATION_PATH = Path("artifacts/analysis/finding_validation.json")
DEFAULT_EVIDENCE_REPORT_PATH = Path("artifacts/analysis/evidence_report.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock Requirement schema and validation.")
    parser.add_argument("--findings", type=Path, default=DEFAULT_FINDINGS_PATH)
    parser.add_argument("--finding-validation", type=Path, default=DEFAULT_FINDING_VALIDATION_PATH)
    parser.add_argument("--evidence-report", type=Path, default=DEFAULT_EVIDENCE_REPORT_PATH)
    parser.add_argument("--mock-output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    args = parser.parse_args()

    findings = load_findings(args.findings)
    finding_validation = load_finding_validation(args.finding_validation)
    load_evidence_report(args.evidence_report)
    raw_output = (
        args.mock_output.read_text(encoding="utf-8")
        if args.mock_output
        else build_default_mock_output(findings)
    )
    provider = MockLLMProvider(raw_output, model="mock-requirement-model")
    response = provider.generate(
        LLMRequest(
            system_prompt="Phase 4a mock Requirement validation. Do not call a production model.",
            user_prompt="Validate mock Requirements from validated Findings.",
            analysis_goal="mock_requirement_generation",
        )
    )
    findings_by_id = {finding["finding_id"]: finding for finding in findings}
    finding_validation_passed = finding_validation.get("status") == "Success" and finding_validation.get("passed") is True
    eligible_finding_ids = set(findings_by_id)
    validation = validate_requirement_output(
        response.raw_text,
        findings_by_id=findings_by_id,
        finding_validation_passed=finding_validation_passed,
        eligible_finding_ids=eligible_finding_ids,
    )
    requirements = [asdict(requirement) for requirement in validation.requirements] if validation.passed else []
    paths = save_outputs(
        raw_output=response.raw_text,
        validation=validation,
        requirements=requirements,
        output_dir=args.output_dir,
    )

    if validation.passed:
        print("Requirement Generation: PASS")
    else:
        print("Requirement Generation: FAIL")
        print(f"Failure Type: {validation.status}")
    print("Provider: mock")
    print(f"Requirement Count: {len(requirements)}")
    print(f"Validation: {'PASS' if validation.passed else 'FAIL'}")
    for error in validation.errors:
        print(f"- {error}")
    print("Output files:")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0 if validation.passed else 1


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
    validation: RequirementValidationResult,
    requirements: list[dict],
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "requirement_generation_raw.json"
    requirements_path = output_dir / "requirements.json"
    validation_path = output_dir / "requirement_validation.json"

    raw_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "provider": "mock",
                "is_mock": True,
                "raw_output": raw_output,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    requirements_path.write_text(
        json.dumps({"requirements": requirements}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    validation_path.write_text(json.dumps(validation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return {"raw": raw_path, "requirements": requirements_path, "validation": validation_path}


if __name__ == "__main__":
    raise SystemExit(main())
