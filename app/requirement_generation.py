"""Requirement generation orchestration for mock and production LLM providers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.analysis_intent import (
    ANALYSIS_FOCUS_MIXED,
    ANALYSIS_FOCUS_POSITIVE_FEEDBACK,
    DEFAULT_ANALYSIS_FOCUS,
    focus_label,
    normalize_analysis_focus,
)
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
from app.llm.json_recovery import JSONRecoveryResult, parse_json_response
from app.priority_engine import PriorityDecision, assign_requirement_priorities
from app.requirement_validator import RequirementValidationResult, validate_requirement_output


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
18. Never use these prohibited words or substrings anywhere in a Requirement: function, functions, functionality, functional, API, endpoint, database, code, class, component, React, Vue.
19. Use product-behavior wording instead: write "working close button" instead of "functional close button", "exercise catalog" instead of "exercise database", and "product behavior" or "capability" instead of "functionality".
20. Success metrics must be observable and measurable. Do not use vague preservation metrics such as "remains high", "remains stable", or "maintain satisfaction" unless the input defines the measurement. Use an empty success_metrics list when reliable measurement is not supported.

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
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS
    error: str | None = None
    extracted_json: str | None = None
    normalized_json: str | None = None
    json_recovery: dict[str, Any] | None = None
    initial_raw_response: str | None = None
    retry_raw_response: str | None = None
    response_metadata: dict[str, Any] | None = None
    is_mock: bool = False


def generate_requirements(
    *,
    findings: list[dict[str, Any]],
    finding_validation: dict[str, Any],
    evidence_report: dict[str, Any],
    provider: LLMProvider,
    analysis_goal: str = DEFAULT_REQUIREMENT_GOAL,
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
    is_mock: bool = False,
) -> RequirementGenerationResult:
    analysis_focus = normalize_analysis_focus(analysis_focus)
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
            analysis_focus=analysis_focus,
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
            analysis_focus=analysis_focus,
        )

    request = build_requirement_request(
        findings=findings,
        evidence_report=evidence_report,
        analysis_goal=analysis_goal,
        analysis_focus=analysis_focus,
    )
    try:
        response = provider.generate(request)
    except MissingAPIKeyError as exc:
        return create_failure_result("Missing API Key", analysis_goal, str(exc), output_dir, provider, is_mock, len(findings_by_id), analysis_focus=analysis_focus)
    except ModelAuthenticationError as exc:
        return create_failure_result("Authentication Error", analysis_goal, str(exc), output_dir, provider, is_mock, len(findings_by_id), analysis_focus=analysis_focus)
    except ModelRateLimitError as exc:
        return create_failure_result("Rate Limit", analysis_goal, str(exc), output_dir, provider, is_mock, len(findings_by_id), analysis_focus=analysis_focus)
    except ModelTimeoutError as exc:
        return create_failure_result("Timeout", analysis_goal, str(exc), output_dir, provider, is_mock, len(findings_by_id), analysis_focus=analysis_focus)
    except ModelRequestError as exc:
        return create_failure_result("Model Request Error", analysis_goal, str(exc), output_dir, provider, is_mock, len(findings_by_id), analysis_focus=analysis_focus)

    initial_recovery = parse_json_response(response.raw_text)
    recovery = initial_recovery
    retry_response = None
    if not recovery.success:
        if response.raw_text.strip():
            retry_request = build_requirement_json_retry_request(
                original_request=request,
                invalid_response=response.raw_text,
            )
            try:
                retry_response = provider.generate(retry_request)
            except MissingAPIKeyError as exc:
                return create_retry_failure_result(
                    "Missing API Key",
                    analysis_goal,
                    str(exc),
                    output_dir,
                    provider,
                    is_mock,
                    len(findings_by_id),
                    initial_raw_response=response.raw_text,
                    initial_response_metadata=response.metadata,
                    initial_recovery=initial_recovery,
                    analysis_focus=analysis_focus,
                )
            except ModelAuthenticationError as exc:
                return create_retry_failure_result(
                    "Authentication Error",
                    analysis_goal,
                    str(exc),
                    output_dir,
                    provider,
                    is_mock,
                    len(findings_by_id),
                    initial_raw_response=response.raw_text,
                    initial_response_metadata=response.metadata,
                    initial_recovery=initial_recovery,
                    analysis_focus=analysis_focus,
                )
            except ModelRateLimitError as exc:
                return create_retry_failure_result(
                    "Rate Limit",
                    analysis_goal,
                    str(exc),
                    output_dir,
                    provider,
                    is_mock,
                    len(findings_by_id),
                    initial_raw_response=response.raw_text,
                    initial_response_metadata=response.metadata,
                    initial_recovery=initial_recovery,
                    analysis_focus=analysis_focus,
                )
            except ModelTimeoutError as exc:
                return create_retry_failure_result(
                    "Timeout",
                    analysis_goal,
                    str(exc),
                    output_dir,
                    provider,
                    is_mock,
                    len(findings_by_id),
                    initial_raw_response=response.raw_text,
                    initial_response_metadata=response.metadata,
                    initial_recovery=initial_recovery,
                    analysis_focus=analysis_focus,
                )
            except ModelRequestError as exc:
                return create_retry_failure_result(
                    "Model Request Error",
                    analysis_goal,
                    str(exc),
                    output_dir,
                    provider,
                    is_mock,
                    len(findings_by_id),
                    initial_raw_response=response.raw_text,
                    initial_response_metadata=response.metadata,
                    initial_recovery=initial_recovery,
                    analysis_focus=analysis_focus,
                )
            recovery = parse_json_response(retry_response.raw_text)
        if not recovery.success:
            result = create_invalid_json_result(
                analysis_goal=analysis_goal,
                output_dir=output_dir,
                provider=provider,
                is_mock=is_mock,
                input_finding_count=len(findings_by_id),
                raw_output=retry_response.raw_text if retry_response else response.raw_text,
                response_metadata=retry_response.metadata if retry_response else response.metadata,
                json_recovery=recovery,
                analysis_focus=analysis_focus,
                initial_raw_response=response.raw_text,
                retry_raw_response=retry_response.raw_text if retry_response else None,
                initial_recovery=initial_recovery,
            )
            save_requirement_outputs(result, output_dir=output_dir)
            return result

    extracted_json = recovery.extracted_response
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
        raw_output=retry_response.raw_text if retry_response else response.raw_text,
        validation=validation,
        requirements=requirements,
        priority_report=[decision.to_dict() for decision in priority_decisions],
        provider=retry_response.provider if retry_response else response.provider,
        model=retry_response.model if retry_response else response.model,
        analysis_goal=analysis_goal,
        input_finding_count=len(findings_by_id),
        saved_paths={},
        analysis_focus=analysis_focus,
        extracted_json=extracted_json,
        normalized_json=normalized_json,
        json_recovery=_json_recovery_metadata(
            initial_recovery=initial_recovery,
            final_recovery=recovery,
            retry_attempted=retry_response is not None,
            retry_success=retry_response is not None,
        ),
        initial_raw_response=response.raw_text,
        retry_raw_response=retry_response.raw_text if retry_response else None,
        response_metadata=retry_response.metadata if retry_response else response.metadata,
        is_mock=is_mock,
    )
    save_requirement_outputs(result, output_dir=output_dir)
    return result


def build_requirement_request(
    *,
    findings: list[dict[str, Any]],
    evidence_report: dict[str, Any],
    analysis_goal: str,
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS,
) -> LLMRequest:
    analysis_focus = normalize_analysis_focus(analysis_focus)
    evidence_reports_by_id = _evidence_reports_by_id(evidence_report)
    finding_payload = []
    for finding in findings:
        finding_id = finding.get("finding_id")
        if not isinstance(finding_id, str) or not finding_id:
            continue
        finding_payload.append(
            {
                "finding_id": finding_id,
                "finding_type": finding.get("finding_type") or "product_problem",
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
            "analysis_focus": analysis_focus,
            "analysis_focus_label": focus_label(analysis_focus),
            "validated_findings": finding_payload,
            "valid_finding_ids": sorted(item["finding_id"] for item in finding_payload),
            "required_output_schema": {
                "requirements": [
                    {
                        "requirement_id": "REQ-001",
                        "requirement_type": "problem",
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
            "allowed_requirement_types": ["problem", "positive_feedback", "mixed"],
            "requirement_type_rule": _requirement_type_rule(analysis_focus),
            "prohibited_word_rule": {
                "terms": [
                    "function",
                    "functions",
                    "functionality",
                    "functional",
                    "API",
                    "endpoint",
                    "database",
                    "code",
                    "class",
                    "component",
                    "React",
                    "Vue",
                ],
                "instruction": "Do not use these words or substrings anywhere in title, description, acceptance_criteria, priority_rationale, risks, success_metrics, or uncertainty. Use product-behavior alternatives such as working, capability, catalog, content set, experience, or product behavior.",
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    return LLMRequest(system_prompt=_system_prompt_for_focus(analysis_focus), user_prompt=user_prompt, analysis_goal=analysis_goal)


def build_requirement_json_retry_request(
    *,
    original_request: LLMRequest,
    invalid_response: str,
) -> LLMRequest:
    original_context = _compact_retry_business_context(original_request)
    retry_payload = {
        "instruction": (
            "Convert the previous response into strict JSON matching the required Requirement schema. "
            "Return only JSON. Do not use Markdown. Do not add explanation text. "
            "Do not change the semantic meaning of any Requirement content. "
            "Do not add Requirements. Do not delete Requirements. "
            "Do not modify finding_id, review_id, priority, requirement_type, or other business fields. "
            "If the previous response was truncated, finish only the JSON structure and incomplete requirement fields "
            "using the compact business context below; keep wording concise enough to fit in the response limit."
        ),
        "original_business_context": original_context,
        "previous_invalid_response": invalid_response,
    }
    return LLMRequest(
        system_prompt=(
            "You are repairing only the JSON format of a Requirement Generation response. "
            "Do not reinterpret the product analysis. Do not change business semantics. "
            "Use the previous response as the source of Requirement content. "
            "Return only strict JSON matching the requested Requirement schema."
        ),
        user_prompt=json.dumps(retry_payload, ensure_ascii=False, indent=2),
        analysis_goal=original_request.analysis_goal,
    )


def _compact_retry_business_context(original_request: LLMRequest) -> dict[str, Any]:
    context: dict[str, Any] = {
        "analysis_goal": original_request.analysis_goal,
        "system_rules": original_request.system_prompt,
    }
    try:
        payload = json.loads(original_request.user_prompt)
    except json.JSONDecodeError:
        context["user_prompt_excerpt"] = original_request.user_prompt[:2000]
        return context
    if not isinstance(payload, dict):
        context["user_prompt_excerpt"] = original_request.user_prompt[:2000]
        return context

    findings = payload.get("validated_findings")
    compact_findings: list[dict[str, Any]] = []
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            compact_findings.append(
                {
                    "finding_id": finding.get("finding_id"),
                    "finding_type": finding.get("finding_type"),
                    "review_ids": finding.get("review_ids"),
                    "support_count": finding.get("support_count"),
                    "confidence": finding.get("confidence"),
                }
            )

    for key in (
        "analysis_focus",
        "analysis_focus_label",
        "valid_finding_ids",
        "required_output_schema",
        "priority_note",
        "allowed_requirement_types",
        "requirement_type_rule",
        "prohibited_word_rule",
    ):
        if key in payload:
            context[key] = payload[key]
    context["validated_findings"] = compact_findings
    return context


def _system_prompt_for_focus(analysis_focus: str) -> str:
    focus = normalize_analysis_focus(analysis_focus)
    if focus == ANALYSIS_FOCUS_POSITIVE_FEEDBACK:
        return (
            SYSTEM_PROMPT
            + "\n\nPositive feedback focus:\n"
            "21. Generate only preservation Requirements for positive_feedback Findings when the evidence supports an actionable product behavior to preserve or strengthen.\n"
            "22. requirement_type must be positive_feedback for generated Requirements.\n"
            "23. Do not frame valued experiences as problems, defects, or unmet needs.\n"
            "24. Prefer success_metrics: [] for preservation Requirements unless the input evidence defines a measurable metric.\n"
            "25. If no actionable preservation Requirement is supported, return {\"requirements\": []}.\n"
        )
    if focus == ANALYSIS_FOCUS_MIXED:
        return (
            SYSTEM_PROMPT
            + "\n\nMixed focus:\n"
            "21. Generate problem Requirements for product_problem Findings and preservation Requirements for positive_feedback Findings.\n"
            "22. Set requirement_type to problem, positive_feedback, or mixed according to the referenced Findings.\n"
            "23. Do not convert positive feedback into fake problems or let problem evidence overwrite positive evidence.\n"
        )
    return SYSTEM_PROMPT + "\n\nProblem focus:\n21. requirement_type must be problem for generated Requirements.\n"


def _requirement_type_rule(analysis_focus: str) -> str:
    focus = normalize_analysis_focus(analysis_focus)
    if focus == ANALYSIS_FOCUS_POSITIVE_FEEDBACK:
        return "Use requirement_type=positive_feedback. Generate preservation requirements only; if findings are not actionable, return an empty requirements list. Use success_metrics: [] unless the evidence provides a concrete measurable metric definition."
    if focus == ANALYSIS_FOCUS_MIXED:
        return "Use requirement_type=problem for product_problem findings, positive_feedback for positive_feedback findings, and mixed only when a requirement explicitly references both types."
    return "Use requirement_type=problem. Positive feedback findings are outside the default problem-analysis scope."


def create_failure_result(
    status: str,
    analysis_goal: str,
    error: str,
    output_dir: Path,
    provider: LLMProvider,
    is_mock: bool,
    input_finding_count: int,
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS,
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
        analysis_focus=normalize_analysis_focus(analysis_focus),
        error=error,
        is_mock=is_mock,
    )
    save_requirement_outputs(result, output_dir=output_dir)
    return result


def create_retry_failure_result(
    status: str,
    analysis_goal: str,
    error: str,
    output_dir: Path,
    provider: LLMProvider,
    is_mock: bool,
    input_finding_count: int,
    *,
    initial_raw_response: str,
    initial_response_metadata: dict[str, Any] | None,
    initial_recovery: JSONRecoveryResult,
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS,
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
        analysis_focus=normalize_analysis_focus(analysis_focus),
        error=error,
        extracted_json=None,
        normalized_json=None,
        json_recovery=_json_recovery_metadata(
            initial_recovery=initial_recovery,
            final_recovery=initial_recovery,
            retry_attempted=True,
            retry_success=False,
            retry_error=error,
        ),
        initial_raw_response=initial_raw_response,
        retry_raw_response=None,
        response_metadata=initial_response_metadata,
        is_mock=is_mock,
    )
    save_requirement_outputs(result, output_dir=output_dir)
    return result


def create_invalid_json_result(
    *,
    analysis_goal: str,
    output_dir: Path,
    provider: LLMProvider,
    is_mock: bool,
    input_finding_count: int,
    raw_output: str,
    response_metadata: dict[str, Any] | None,
    json_recovery: JSONRecoveryResult,
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS,
    initial_raw_response: str | None = None,
    retry_raw_response: str | None = None,
    initial_recovery: JSONRecoveryResult | None = None,
) -> RequirementGenerationResult:
    error = json_recovery.error or "Invalid JSON"
    validation = RequirementValidationResult(status="SKIPPED", passed=False, errors=[error])
    retry_attempted = retry_raw_response is not None
    return RequirementGenerationResult(
        generation_status=STATUS_INVALID_JSON,
        generation_passed=False,
        raw_output=raw_output,
        validation=validation,
        requirements=[],
        priority_report=[],
        provider=getattr(provider, "provider_name", None),
        model=getattr(provider, "model", None),
        analysis_goal=analysis_goal,
        input_finding_count=input_finding_count,
        saved_paths={},
        analysis_focus=normalize_analysis_focus(analysis_focus),
        error=error,
        extracted_json=json_recovery.extracted_response or None,
        normalized_json=None,
        json_recovery=_json_recovery_metadata(
            initial_recovery=initial_recovery or json_recovery,
            final_recovery=json_recovery,
            retry_attempted=retry_attempted,
            retry_success=False,
        ),
        initial_raw_response=initial_raw_response or raw_output,
        retry_raw_response=retry_raw_response,
        response_metadata=response_metadata,
        is_mock=is_mock,
    )


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
                "analysis_focus": result.analysis_focus,
                "generation_status": result.generation_status,
                "raw_output": result.raw_output,
                "raw_response": result.raw_output,
                "initial_raw_response": result.initial_raw_response if result.initial_raw_response is not None else result.raw_output,
                "retry_raw_response": result.retry_raw_response,
                "extracted_json": result.extracted_json,
                "extracted_response": _raw_extracted_response(result),
                "recovery_method": (result.json_recovery or {}).get("method"),
                "normalized_json": result.normalized_json,
                "json_recovery": result.json_recovery or {"attempted": False, "method": None, "success": False},
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


def _json_recovery_metadata(
    *,
    initial_recovery: JSONRecoveryResult,
    final_recovery: JSONRecoveryResult,
    retry_attempted: bool,
    retry_success: bool,
    retry_error: str | None = None,
) -> dict[str, Any]:
    return {
        **final_recovery.metadata(),
        "initial_attempted": initial_recovery.attempted,
        "initial_method": initial_recovery.method,
        "initial_success": initial_recovery.success,
        "initial_error": initial_recovery.error,
        "retry_attempted": retry_attempted,
        "retry_reason": "invalid_json" if retry_attempted else None,
        "retry_success": retry_success,
        "retry_recovery_method": final_recovery.method if retry_attempted and final_recovery.success else None,
        "retry_error": retry_error or (final_recovery.error if retry_attempted and not final_recovery.success else None),
    }


def _raw_extracted_response(result: RequirementGenerationResult) -> Any:
    if not result.extracted_json:
        return None
    try:
        return json.loads(result.extracted_json)
    except json.JSONDecodeError:
        return result.extracted_json


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
