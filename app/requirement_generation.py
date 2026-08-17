"""Requirement generation orchestration for mock and production LLM providers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
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
from app.priority_engine import PriorityDecision, assign_requirement_priorities
from app.requirement_validator import RequirementValidationResult, validate_requirement_output
from app.topic_discovery import extract_json_text


DEFAULT_REQUIREMENT_GOAL = "分析低评分用户对订阅和价格的主要问题"
STATUS_SUCCESS = "Success"
STATUS_INVALID_JSON = "Invalid JSON"
STATUS_FINDING_VALIDATION_FAILED = "Finding Validation Failed"
STATUS_EMPTY_FINDINGS = "Empty Findings"


SYSTEM_PROMPT = """You are performing product Requirement Generation from validated Findings.

Rules:
1. The current task is to generate product Requirements from Validated Findings.
2. The Findings have already passed Evidence Validation.
3. Only use the input Findings and Evidence Reports.
4. Every Requirement must reference at least one finding_id.
5. Do not reference a Finding ID outside the input.
6. Do not invent unsupported problems.
7. Describe what product behavior needs to address, not how to implement it.
8. Do not describe technical implementation details.
9. Do not specify React, Vue, database, API, code files, or engineering implementation choices.
10. Do not generate Roadmaps.
11. Do not generate PRDs.
12. Do not generate Test Cases.
13. Do not generate a technical design.
14. Do not expand Finding scope beyond the current evidence.
15. If evidence is weak, reflect that in uncertainty.
16. One Finding can produce zero, one, or multiple Requirements.
17. If a Finding does not support a clear Requirement, omit it.

Return only JSON matching the required Requirement schema."""


@dataclass
class RequirementGenerationResult:
    generation_status: str
    generation_passed: bool
    raw_output: str
    validation: RequirementValidationResult
    requirements: list[dict[str, Any]]
    priority_report: list[dict[str, Any]]
    provider: str | None
    model: str | None
    analysis_goal: str
    input_finding_count: int
    saved_paths: dict[str, str]
    error: str | None = None
    extracted_json: str | None = None
    normalized_json: str | None = None
    response_metadata: dict[str, Any] | None = None
    is_mock: bool = False


def generate_requirements(
    *,
    findings: list[dict[str, Any]],
    finding_validation: dict[str, Any],
    evidence_report: dict[str, Any],
    provider: LLMProvider,
    analysis_goal: str = DEFAULT_REQUIREMENT_GOAL,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
    is_mock: bool = False,
) -> RequirementGenerationResult:
    finding_validation_passed = _finding_validation_passed(finding_validation)
    findings_by_id = _findings_by_id(findings)
    eligible_finding_ids = set(findings_by_id)
    if not finding_validation_passed:
        return create_failure_result(
            STATUS_FINDING_VALIDATION_FAILED,
            analysis_goal,
            "Finding validation is not PASS; Requirement generation skipped.",
            output_dir,
            provider,
            is_mock,
            len(findings_by_id),
        )
    if not findings_by_id:
        return create_failure_result(
            STATUS_EMPTY_FINDINGS,
            analysis_goal,
            "No validated Findings are available for Requirement generation.",
            output_dir,
            provider,
            is_mock,
            0,
        )

    request = build_requirement_request(
        findings=findings,
        evidence_report=evidence_report,
        analysis_goal=analysis_goal,
    )
    try:
        response = provider.generate(request)
    except MissingAPIKeyError as exc:
        return create_failure_result("Missing API Key", analysis_goal, str(exc), output_dir, provider, is_mock, len(findings_by_id))
    except ModelAuthenticationError as exc:
        return create_failure_result("Authentication Error", analysis_goal, str(exc), output_dir, provider, is_mock, len(findings_by_id))
    except ModelRateLimitError as exc:
        return create_failure_result("Rate Limit", analysis_goal, str(exc), output_dir, provider, is_mock, len(findings_by_id))
    except ModelTimeoutError as exc:
        return create_failure_result("Timeout", analysis_goal, str(exc), output_dir, provider, is_mock, len(findings_by_id))
    except ModelRequestError as exc:
        return create_failure_result("Model Request Error", analysis_goal, str(exc), output_dir, provider, is_mock, len(findings_by_id))

    extracted_json = extract_json_text(response.raw_text)
    evidence_reports_by_id = _evidence_reports_by_id(evidence_report)
    normalized_json, priority_decisions = _apply_priority_engine(
        extracted_json,
        findings_by_id=findings_by_id,
        evidence_reports_by_id=evidence_reports_by_id,
    )
    validation = validate_requirement_output(
        normalized_json,
        findings_by_id=findings_by_id,
        finding_validation_passed=finding_validation_passed,
        eligible_finding_ids=eligible_finding_ids,
    )
    requirements = [asdict(requirement) for requirement in validation.requirements] if validation.passed else []
    generation_passed = validation.status != STATUS_INVALID_JSON
    result = RequirementGenerationResult(
        generation_status=STATUS_SUCCESS if generation_passed else STATUS_INVALID_JSON,
        generation_passed=generation_passed,
        raw_output=response.raw_text,
        validation=validation,
        requirements=requirements,
        priority_report=[decision.to_dict() for decision in priority_decisions],
        provider=response.provider,
        model=response.model,
        analysis_goal=analysis_goal,
        input_finding_count=len(findings_by_id),
        saved_paths={},
        extracted_json=extracted_json,
        normalized_json=normalized_json,
        response_metadata=response.metadata,
        is_mock=is_mock,
    )
    save_requirement_outputs(result, output_dir=output_dir)
    return result


def build_requirement_request(
    *,
    findings: list[dict[str, Any]],
    evidence_report: dict[str, Any],
    analysis_goal: str,
) -> LLMRequest:
    evidence_reports_by_id = _evidence_reports_by_id(evidence_report)
    finding_payload = []
    for finding in findings:
        finding_id = finding.get("finding_id")
        if not isinstance(finding_id, str) or not finding_id:
            continue
        finding_payload.append(
            {
                "finding_id": finding_id,
                "issue_ids": finding.get("issue_ids"),
                "review_ids": finding.get("review_ids"),
                "title": finding.get("title"),
                "statement": finding.get("statement"),
                "evidence_summary": finding.get("evidence_summary"),
                "support_count": finding.get("support_count"),
                "confidence": finding.get("confidence"),
                "uncertainty": finding.get("uncertainty"),
                "conflicting_review_ids": finding.get("conflicting_review_ids"),
                "evidence_report": evidence_reports_by_id.get(finding_id),
            }
        )
    user_prompt = json.dumps(
        {
            "analysis_goal": analysis_goal,
            "validated_findings": finding_payload,
            "valid_finding_ids": sorted(item["finding_id"] for item in finding_payload),
            "required_output_schema": {
                "requirements": [
                    {
                        "requirement_id": "REQ-001",
                        "finding_ids": ["FINDING-001"],
                        "title": "string",
                        "description": "string",
                        "acceptance_criteria": ["verifiable criterion"],
                        "priority": "P1",
                        "priority_rationale": "string",
                        "risks": [],
                        "success_metrics": [],
                        "uncertainty": "string",
                        "source_review_ids": ["optional-review-id"],
                    }
                ]
            },
            "priority_note": "Model priority is advisory only; deterministic priority engine will assign final priority.",
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
    input_finding_count: int,
) -> RequirementGenerationResult:
    validation = RequirementValidationResult(status="SKIPPED", passed=False, errors=[error])
    result = RequirementGenerationResult(
        generation_status=status,
        generation_passed=False,
        raw_output="",
        validation=validation,
        requirements=[],
        priority_report=[],
        provider=getattr(provider, "provider_name", None),
        model=getattr(provider, "model", None),
        analysis_goal=analysis_goal,
        input_finding_count=input_finding_count,
        saved_paths={},
        error=error,
        is_mock=is_mock,
    )
    save_requirement_outputs(result, output_dir=output_dir)
    return result


def save_requirement_outputs(
    result: RequirementGenerationResult,
    *,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "requirement_generation_raw.json"
    requirements_path = output_dir / "requirements.json"
    validation_path = output_dir / "requirement_validation.json"
    priority_path = output_dir / "priority_report.json"
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
                "normalized_json": result.normalized_json,
                "response_metadata": result.response_metadata or {},
                "error": result.error,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    requirements_path.write_text(json.dumps({"requirements": result.requirements}, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    priority_path.write_text(
        json.dumps({"priority_report": result.priority_report}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths = {"raw": raw_path, "requirements": requirements_path, "validation": validation_path, "priority": priority_path}
    result.saved_paths = {key: str(path) for key, path in paths.items()}
    return paths


def _apply_priority_engine(
    extracted_json: str,
    *,
    findings_by_id: dict[str, dict[str, Any]],
    evidence_reports_by_id: dict[str, dict[str, Any]],
) -> tuple[str, list[PriorityDecision]]:
    try:
        payload = json.loads(extracted_json)
    except json.JSONDecodeError:
        return extracted_json, []
    if not isinstance(payload, dict):
        return extracted_json, []
    normalized_payload, decisions = assign_requirement_priorities(
        payload,
        findings_by_id=findings_by_id,
        evidence_reports_by_id=evidence_reports_by_id,
    )
    return json.dumps(normalized_payload, ensure_ascii=False), decisions


def _finding_validation_passed(finding_validation: dict[str, Any]) -> bool:
    return finding_validation.get("status") == "Success" and finding_validation.get("passed") is True


def _findings_by_id(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {finding["finding_id"]: finding for finding in findings if isinstance(finding.get("finding_id"), str)}


def _evidence_reports_by_id(evidence_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    reports = evidence_report.get("evidence_reports") if isinstance(evidence_report, dict) else None
    if not isinstance(reports, list):
        return {}
    return {report["finding_id"]: report for report in reports if isinstance(report, dict) and isinstance(report.get("finding_id"), str)}
