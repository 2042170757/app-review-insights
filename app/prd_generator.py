"""PRD generation orchestration for mock and production LLM providers."""

from __future__ import annotations

import json
import re
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
from app.llm.mock_provider import MockLLMProvider
from app.prd_validator import (
    PRDValidationResult,
    STATUS_INVALID_JSON,
    STATUS_SCHEMA_VALIDATION_FAILED,
    _is_measurable_metric,
    validate_prd_output,
)
from app.topic_discovery import extract_json_text


DEFAULT_PRD_GOAL = "分析低评分用户对订阅和价格的主要问题"
STATUS_SUCCESS = "Success"
STATUS_INPUT_VALIDATION_FAILED = "Input Validation Failed"


SYSTEM_PROMPT = """You are generating Product Requirements Documents from validated Roadmap Versions.

Rules:
1. The current task is PRD Generation.
2. Use only the input Versions, Requirements, Findings, and Evidence.
3. Do not create new Requirements.
4. Do not create new Findings.
5. Do not create new Issues.
6. Do not change Requirement priority.
7. Do not change Version requirement_ids.
8. Do not change the Roadmap.
9. Each PRD must align with its Version goal.
10. Each PRD must include Non-Goals.
11. Each PRD must preserve the Evidence Scope.
12. Product parameters not directly decided by Evidence must be placed in open_questions.
13. Do not present assumptions as evidence-backed facts.
14. Do not add unsupported product capabilities.
15. Do not generate technical architecture.
16. Do not specify React, Vue, database, API, endpoint, code files, or implementation structure.
17. Do not generate Test Cases.
18. Do not generate a new Roadmap.
19. Success Metrics must be measurable but must not invent numeric targets unless provided in the input.
20. evidence_summary must cite related requirement_id or finding_id values.
21. If a Version includes required_open_questions, every listed product decision must be represented in that PRD's open_questions.
22. Analysis Goal is overall context only; it must not override any Version goal.
23. For each PRD, the first item in goals must exactly match that Version's required_prd_goal.
24. Every PRD must include at least one open question about evidence uncertainty, scope, metrics, or a product decision.
25. Every success metric must be observable and measurable: phrase it with rate, count, number, score, rating, survey, user-reported signal, time, percentage, retention, conversion, decrease, increase, reduction, complaints, reports, incidents, reviews, or a numeric unit. Prefer "user-reported X rate/count/score/rating" over vague "user satisfaction" or "user feedback on X" wording. Do not use vague wording such as "improved user experience", "better satisfaction", "user feedback on clarity", "user satisfaction with support improves", or "increase engagement" as a standalone metric.
26. If the input Evidence, Requirement, and Version do not support a reliable success metric, return success_metrics as an empty list and add an open question asking what measurable success metric or target should be defined.
27. If a metric concept is reasonable but the target value is a product decision, put that target definition in open_questions instead of inventing a number.
28. For positive_feedback Requirements, do not use vague preservation metrics such as "remains high", "remains stable", or "maintain satisfaction" unless the input defines the measurement and target; otherwise leave success_metrics empty and put the metric definition in open_questions.
29. Do not copy input Requirement or Version success_metrics blindly. Re-include only metrics that satisfy Rules 25-28; move unsupported metric definitions or targets to open_questions.
30. The input marks validated_success_metric_candidates and unsupported_success_metric_candidates. You may include only validated_success_metric_candidates in success_metrics.
31. Never include any metric listed in unsupported_success_metric_candidates in success_metrics. Convert it into an open question asking how the metric should be measured.
32. A phrase shaped like "User satisfaction with <topic>" is not a valid success metric unless it explicitly says user-reported rate, count, score, rating, survey result, or another observable measurement.

Return only JSON matching the existing PRD schema."""


@dataclass
class PRDGenerationResult:
    generation_status: str
    generation_passed: bool
    raw_output: str
    validation: PRDValidationResult
    prds: list[dict[str, Any]]
    provider: str | None
    model: str | None
    analysis_goal: str
    saved_paths: dict[str, str]
    extracted_json: str | None = None
    error: str | None = None
    response_metadata: dict[str, Any] | None = None
    is_mock: bool = True


def generate_prds(
    *,
    requirements: list[dict[str, Any]],
    requirement_validation: dict[str, Any],
    roadmap: dict[str, Any],
    roadmap_validation: dict[str, Any],
    findings: list[dict[str, Any]],
    finding_validation: dict[str, Any],
    issues: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    provider: LLMProvider,
    evidence_report: dict[str, Any] | None = None,
    analysis_goal: str = DEFAULT_PRD_GOAL,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
    is_mock: bool = True,
) -> PRDGenerationResult:
    requirement_passed = _validation_passed(requirement_validation)
    roadmap_passed = _validation_passed(roadmap_validation)
    finding_passed = _validation_passed(finding_validation)
    if not (requirement_passed and roadmap_passed and finding_passed):
        return create_failure_result(
            STATUS_INPUT_VALIDATION_FAILED,
            "Requirement, Roadmap, and Finding validation must all be PASS before PRD generation.",
            provider,
            analysis_goal,
            output_dir,
            is_mock,
        )

    request = build_prd_request(
        requirements=requirements,
        roadmap=roadmap,
        findings=findings,
        evidence_report=evidence_report or {},
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
    validation = validate_prd_output(
        extracted_json,
        requirements_by_id=_by_id(requirements, "requirement_id"),
        versions_by_id=_by_id(roadmap.get("versions", []), "version_id"),
        findings_by_id=_by_id(findings, "finding_id"),
        issues_by_id=_by_id(issues, "issue_id"),
        topics_by_id=_by_id(topics, "topic_id"),
        valid_review_ids=set(_by_id(reviews, "id")),
        requirement_validation_passed=requirement_passed,
        roadmap_validation_passed=roadmap_passed,
        finding_validation_passed=finding_passed,
    )
    prds = [asdict(prd) for prd in validation.prds] if validation.passed else []
    generation_passed = validation.status not in {
        STATUS_INVALID_JSON,
        STATUS_SCHEMA_VALIDATION_FAILED,
    }
    result = PRDGenerationResult(
        generation_status=STATUS_SUCCESS if generation_passed else validation.status,
        generation_passed=generation_passed,
        raw_output=response.raw_text,
        validation=validation,
        prds=prds,
        provider=response.provider,
        model=response.model,
        analysis_goal=analysis_goal,
        saved_paths={},
        extracted_json=extracted_json,
        response_metadata=response.metadata,
        is_mock=is_mock,
    )
    save_prd_outputs(result, output_dir=output_dir)
    return result


def build_prd_request(
    *,
    requirements: list[dict[str, Any]],
    roadmap: dict[str, Any],
    findings: list[dict[str, Any]],
    evidence_report: dict[str, Any],
    analysis_goal: str,
) -> LLMRequest:
    requirements_by_id = _by_id(requirements, "requirement_id")
    findings_by_id = _by_id(findings, "finding_id")
    evidence_reports_by_id = _evidence_reports_by_id(evidence_report)
    version_payload = []
    for version in roadmap.get("versions", []):
        version_id = version.get("version_id")
        if not isinstance(version_id, str) or version_id == "Deferred":
            continue
        requirement_ids = [
            requirement_id
            for requirement_id in version.get("requirement_ids", [])
            if isinstance(requirement_id, str) and requirement_id in requirements_by_id
        ]
        version_requirements = []
        for requirement_id in requirement_ids:
            requirement = requirements_by_id[requirement_id]
            finding_ids = [
                finding_id
                for finding_id in requirement.get("finding_ids", [])
                if isinstance(finding_id, str)
            ]
            metric_candidates = _split_success_metric_candidates(requirement.get("success_metrics"))
            version_requirements.append(
                {
                    "requirement_id": requirement_id,
                    "requirement_type": requirement.get("requirement_type") or "problem",
                    "title": requirement.get("title"),
                    "description": requirement.get("description"),
                    "acceptance_criteria": requirement.get("acceptance_criteria"),
                    "priority": requirement.get("priority"),
                    "risks": requirement.get("risks"),
                    "success_metrics": requirement.get("success_metrics"),
                    "validated_success_metric_candidates": metric_candidates["validated"],
                    "unsupported_success_metric_candidates": metric_candidates["unsupported"],
                    "uncertainty": requirement.get("uncertainty"),
                    "source_review_ids": requirement.get("source_review_ids"),
                    "findings": [
                        {
                            **findings_by_id[finding_id],
                            "evidence_report": evidence_reports_by_id.get(finding_id),
                        }
                        for finding_id in finding_ids
                        if finding_id in findings_by_id
                    ],
                }
            )
        version_metric_candidates = _split_success_metric_candidates(version.get("success_metrics"))
        version_payload.append(
            {
                "version_id": version_id,
                "name": version.get("name"),
                "goal": version.get("goal"),
                "required_prd_goal": version.get("goal"),
                "requirement_ids": requirement_ids,
                "rationale": version.get("rationale"),
                "risks": version.get("risks"),
                "success_metrics": version.get("success_metrics"),
                "validated_success_metric_candidates": version_metric_candidates["validated"],
                "unsupported_success_metric_candidates": version_metric_candidates["unsupported"],
                "required_open_questions": _required_open_questions_for_requirements(version_requirements),
                "requirements": version_requirements,
            }
        )
    user_prompt = json.dumps(
        {
            "analysis_goal": analysis_goal,
            "validated_versions": version_payload,
            "valid_version_ids": [version["version_id"] for version in version_payload],
            "requirement_type_rule": "If a PRD contains positive_feedback Requirements, frame the context as a value or strength to preserve. Do not describe valued experiences as defects. The existing problem_statement field may contain a value/strength statement when the version is positive-feedback focused. For positive_feedback Requirements, use success_metrics only when the input provides a measurable metric definition; otherwise return success_metrics as [] and ask how to measure preservation in open_questions.",
            "required_output_schema": {
                "prds": [
                    {
                        "prd_id": "PRD-V1",
                        "version_id": "V1",
                        "title": "string",
                        "overview": "string",
                        "problem_statement": "string",
                        "evidence_summary": "must cite REQ/FINDING ids",
                        "goals": ["string"],
                        "non_goals": ["string"],
                        "requirement_ids": ["must exactly match Version requirement_ids"],
                        "risks": [],
                        "success_metrics": ["observable metric without invented numeric target, or [] if no reliable metric is supported"],
                        "open_questions": ["questions for unsupported product decisions, including metric definition or target when success_metrics is []"],
                    }
                ]
            },
            "open_question_guidance": {
                "all_prds": "Every PRD must include at least one open question. If no specific requirement question is listed, include a product-scope, evidence-uncertainty, or metric definition question. If success_metrics is empty, open_questions must ask what measurable success metric or target should be defined.",
                "context_rule": "Required open questions are derived from the current Requirement title, description, acceptance criteria, risks, and metrics. Requirement IDs have no built-in product meaning.",
            },
            "goal_alignment_rule": "For each PRD, goals[0] must exactly equal the matching validated_versions[].required_prd_goal. Additional goals may expand that Version goal but must not replace it.",
            "success_metric_rule": "Every success metric must be phrased as an observable metric using rate, count, number, score, rating, survey, user-reported signal, time, percentage, retention, conversion, decrease, increase, reduction, complaints, reports, incidents, reviews, or a numeric unit. A score-based metric is valid only when it names what score or rating is being observed, such as user satisfaction score with workout content. For satisfaction or feedback concepts, prefer user-reported satisfaction/feedback rate/count/score/rating instead of vague satisfaction wording or standalone phrases like user feedback on clarity. Avoid vague standalone metrics such as remains high, remains stable, maintain satisfaction, improved trust, improved user experience, better satisfaction, user feedback on clarity, user satisfaction with support improves, or increase engagement. If the only supported concept is satisfaction or feedback but no score/rating/rate/count/survey/user-reported measurement is defined, do not include it in success_metrics; put the measurement definition in open_questions. Do not copy input success_metrics unless they satisfy this rule. Do not invent target numbers such as 10%, 20%, 30%, or 50% unless those numbers exist in the input. If no reliable metric is supported, return success_metrics: [] and add an open question for metric definition or target.",
            "unsupported_metric_rule": "Metrics listed in unsupported_success_metric_candidates are known non-measurable or underdefined inputs. Do not include those exact strings in PRD success_metrics. Keep their measurement uncertainty in open_questions instead. Example: 'User satisfaction with workout relevance' must not be a success metric unless rewritten as an explicit user-reported satisfaction score/rating/rate or survey measure supported by the input.",
        },
        ensure_ascii=False,
        indent=2,
    )
    return LLMRequest(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt, analysis_goal=analysis_goal)


def build_default_mock_output(
    *,
    roadmap: dict[str, Any],
    requirements: list[dict[str, Any]],
) -> str:
    requirements_by_id = _by_id(requirements, "requirement_id")
    prds: list[dict[str, Any]] = []
    for version in roadmap.get("versions", []):
        version_id = version.get("version_id")
        if not isinstance(version_id, str) or version_id == "Deferred":
            continue
        requirement_ids = [
            requirement_id
            for requirement_id in version.get("requirement_ids", [])
            if isinstance(requirement_id, str) and requirement_id in requirements_by_id
        ]
        if not requirement_ids:
            continue
        finding_ids = sorted(
            {
                finding_id
                for requirement_id in requirement_ids
                for finding_id in requirements_by_id[requirement_id].get("finding_ids", [])
                if isinstance(finding_id, str)
            }
        )
        goals = [_text(version.get("goal"))]
        evidence_refs = requirement_ids[:2] + finding_ids[:2]
        success_metrics = _metrics_for_version(version)
        version_requirements = [requirements_by_id[requirement_id] for requirement_id in requirement_ids]
        prds.append(
            {
                "prd_id": f"PRD-{version_id}",
                "version_id": version_id,
                "title": f"{_text(version.get('name'))} PRD",
                "overview": f"Define the product scope for {version_id}: {_text(version.get('name'))}.",
                "problem_statement": f"This PRD addresses validated user problems assigned to {version_id}.",
                "evidence_summary": "Evidence is traceable through "
                + ", ".join(evidence_refs)
                + ".",
                "goals": goals,
                "non_goals": ["Do not expand scope beyond the validated requirements in this version."],
                "requirement_ids": requirement_ids,
                "risks": list(version.get("risks", [])),
                "success_metrics": success_metrics,
                "open_questions": _open_questions_for_prd(version_requirements, success_metrics),
            }
        )
    return json.dumps({"prds": prds}, ensure_ascii=False)


def create_mock_provider(raw_output: str) -> MockLLMProvider:
    return MockLLMProvider(raw_output, model="mock-prd-model")


def create_failure_result(
    status: str,
    error: str,
    provider: LLMProvider,
    analysis_goal: str,
    output_dir: Path,
    is_mock: bool,
) -> PRDGenerationResult:
    validation = PRDValidationResult(status="SKIPPED", passed=False, errors=[error])
    result = PRDGenerationResult(
        generation_status=status,
        generation_passed=False,
        raw_output="",
        validation=validation,
        prds=[],
        provider=getattr(provider, "provider_name", None),
        model=getattr(provider, "model", None),
        analysis_goal=analysis_goal,
        saved_paths={},
        error=error,
        is_mock=is_mock,
    )
    save_prd_outputs(result, output_dir=output_dir)
    return result


def save_prd_outputs(
    result: PRDGenerationResult,
    *,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "prd_generation_raw.json"
    prds_path = output_dir / "prds.json"
    validation_path = output_dir / "prd_validation.json"
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
    prds_path.write_text(json.dumps({"prds": result.prds}, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    paths = {"raw": raw_path, "prds": prds_path, "validation": validation_path}
    result.saved_paths = {key: str(path) for key, path in paths.items()}
    return paths


def _metrics_for_version(version: dict[str, Any]) -> list[str]:
    metrics = [_text(item) for item in version.get("success_metrics", []) if _text(item)]
    if metrics:
        return metrics
    return []


def _split_success_metric_candidates(value: Any) -> dict[str, list[str]]:
    metrics = [_text(item) for item in value if _text(item)] if isinstance(value, list) else []
    return {
        "validated": [metric for metric in metrics if _is_measurable_metric(metric)],
        "unsupported": [metric for metric in metrics if not _is_measurable_metric(metric)],
    }


def _open_questions_for_requirements(requirements: list[dict[str, Any]]) -> list[str]:
    questions = [decision["question"] for requirement in requirements for decision in _required_open_question_decisions(requirement)]
    if not questions:
        questions.append("Confirm the final product scope and success metric definitions before delivery.")
    return questions


def _open_questions_for_prd(requirements: list[dict[str, Any]], success_metrics: list[str]) -> list[str]:
    questions = _open_questions_for_requirements(requirements)
    if not success_metrics and not any("success metric" in question.lower() or "measurable" in question.lower() for question in questions):
        questions.append("What measurable success metric and target should define success for this PRD?")
    return questions


def _required_open_questions_for_requirements(requirements: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "requirement_id": decision["requirement_id"],
            "decision": decision["question"],
        }
        for requirement in requirements
        for decision in _required_open_question_decisions(requirement)
    ]


def _required_open_question_decisions(requirement: dict[str, Any]) -> list[dict[str, str]]:
    requirement_id = _text(requirement.get("requirement_id"))
    text = " ".join(
        [
            _text(requirement.get("title")),
            _text(requirement.get("description")),
            " ".join(_list_text(requirement.get("acceptance_criteria"))),
            " ".join(_list_text(requirement.get("risks"))),
            " ".join(_list_text(requirement.get("success_metrics"))),
            _text(requirement.get("uncertainty")),
        ]
    ).lower()
    decisions: list[dict[str, str]] = []
    if "free" in text and ("threshold" in text or "proportion" in text or "library" in text or "access" in text):
        decisions.append(
            {
                "requirement_id": requirement_id,
                "question": "What free access threshold, proportion, or scope should be defined before delivery?",
            }
        )
    if _contains_any_term(text, ["refresh", "cadence", "frequency", "monthly", "update cadence", "content update"]):
        decisions.append(
            {
                "requirement_id": requirement_id,
                "question": "What content refresh cadence, frequency, or timing should be defined before delivery?",
            }
        )
    if _contains_any_term(text, ["support"]) and _contains_any_term(text, ["channel", "channels", "email", "chat", "contact"]):
        decisions.append(
            {
                "requirement_id": requirement_id,
                "question": "Which support channel or contact path should be defined before delivery?",
            }
        )
    if _contains_any_term(text, ["large file", "large files"]) and _contains_any_term(text, ["crash", "crashes", "opening", "open"]):
        decisions.append(
            {
                "requirement_id": requirement_id,
                "question": "What large file size or crash-free opening threshold should define success?",
            }
        )
    if "export" in text and "format" in text:
        decisions.append(
            {
                "requirement_id": requirement_id,
                "question": "Which export format or formats should be supported?",
            }
        )
    if _contains_any_term(text, ["notification", "notifications", "reminder", "reminders"]) and _contains_any_term(
        text, ["late", "duplicate", "on time", "timing", "delivery"]
    ):
        decisions.append(
            {
                "requirement_id": requirement_id,
                "question": "What reminder or notification timing and duplication threshold should define success?",
            }
        )
    return decisions


def _contains_any_term(text: str, terms: list[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _validation_passed(payload: dict[str, Any]) -> bool:
    return payload.get("status") == "Success" and payload.get("passed") is True


def _by_id(items: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    return {
        item[key]: item
        for item in items
        if isinstance(item, dict) and isinstance(item.get(key), str) and item.get(key)
    }


def _evidence_reports_by_id(evidence_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    reports = evidence_report.get("evidence_reports") if isinstance(evidence_report, dict) else None
    if not isinstance(reports, list):
        return {}
    return {
        report["finding_id"]: report
        for report in reports
        if isinstance(report, dict) and isinstance(report.get("finding_id"), str)
    }


def _list_text(value: Any) -> list[str]:
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
