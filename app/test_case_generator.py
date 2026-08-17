"""Test case generation orchestration for mock and production LLM providers."""

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
from app.llm.mock_provider import MockLLMProvider
from app.test_case_validator import (
    STATUS_INVALID_JSON,
    STATUS_SCHEMA_VALIDATION_FAILED,
    TestCaseValidationResult,
    enrich_test_case_source_review_ids,
    validate_test_case_output,
)
from app.test_coverage import TestCoverageReport, build_acceptance_criteria_index, calculate_test_coverage, make_acceptance_criteria_id
from app.topic_discovery import extract_json_text


STATUS_SUCCESS = "Success"
STATUS_INPUT_VALIDATION_FAILED = "Input Validation Failed"


SYSTEM_PROMPT = """You are generating executable Test Cases from validated Requirements and Acceptance Criteria.

Rules:
1. The current task is to generate Test Cases for existing Acceptance Criteria.
2. Do not modify Requirements.
3. Do not modify Acceptance Criteria.
4. Every Test Case must reference a real requirement_id from the input.
5. Every Test Case must reference at least one real acceptance_criteria_id from the input.
6. Test Case behavior must come only from the referenced Acceptance Criteria.
7. Do not invent product features.
8. Do not expand business scope.
9. Do not introduce unsupported new rules.
10. You may cover normal paths, boundary conditions, exception paths, and validation scenarios.
11. Not every Acceptance Criterion needs multiple Test Cases.
12. Prefer concise Test Cases that cover multiple Acceptance Criteria from the same Requirement when one executable scenario can verify them.
13. Test steps must be concrete and executable.
14. expected_result must be verifiable.
15. test_type must be one of functional, validation, edge_case, regression.
16. priority must equal the referenced Requirement priority.
17. Do not determine source_review_ids; the backend attaches them deterministically from Requirement -> Finding -> Review evidence.
18. Do not generate PRDs.
19. Do not generate Requirements.
20. Do not generate technical architecture.
21. Do not generate implementation code.

Return only JSON matching the existing Test Case schema."""


@dataclass
class TestCaseGenerationResult:
    generation_status: str
    generation_passed: bool
    raw_output: str
    validation: TestCaseValidationResult
    test_cases: list[dict[str, Any]]
    coverage: TestCoverageReport
    provider: str | None
    model: str | None
    analysis_goal: str
    saved_paths: dict[str, str]
    extracted_json: str | None = None
    error: str | None = None
    response_metadata: dict[str, Any] | None = None
    is_mock: bool = True


def generate_test_cases(
    *,
    requirements: list[dict[str, Any]],
    requirement_validation: dict[str, Any],
    prd_validation: dict[str, Any],
    provider: LLMProvider,
    prds: list[dict[str, Any]] | None = None,
    roadmap: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
    analysis_goal: str = "test_case_generation",
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
    is_mock: bool = True,
) -> TestCaseGenerationResult:
    requirement_passed = _validation_passed(requirement_validation)
    prd_passed = _validation_passed(prd_validation)
    if not (requirement_passed and prd_passed):
        return create_failure_result(
            STATUS_INPUT_VALIDATION_FAILED,
            "Requirement Validation and PRD Validation must both be PASS before Test Case generation.",
            requirements,
            provider,
            analysis_goal,
            output_dir,
            is_mock,
        )

    request = build_test_case_request(
        requirements=requirements,
        prds=prds or [],
        roadmap=roadmap or {},
        analysis_goal=analysis_goal,
    )
    try:
        response = provider.generate(request)
    except MissingAPIKeyError as exc:
        return create_failure_result("Missing API Key", str(exc), requirements, provider, analysis_goal, output_dir, is_mock)
    except ModelAuthenticationError as exc:
        return create_failure_result("Authentication Error", str(exc), requirements, provider, analysis_goal, output_dir, is_mock)
    except ModelRateLimitError as exc:
        return create_failure_result("Rate Limit", str(exc), requirements, provider, analysis_goal, output_dir, is_mock)
    except ModelTimeoutError as exc:
        return create_failure_result("Timeout", str(exc), requirements, provider, analysis_goal, output_dir, is_mock)
    except ModelRequestError as exc:
        return create_failure_result("Model Request Error", str(exc), requirements, provider, analysis_goal, output_dir, is_mock)
    extracted_json = extract_json_text(response.raw_text)
    findings_by_id = _by_id(findings or [], "finding_id")
    enriched_json = extracted_json
    try:
        enriched_payload = enrich_test_case_source_review_ids(
            json.loads(extracted_json),
            requirements=requirements,
            findings_by_id=findings_by_id,
        )
        enriched_json = json.dumps(enriched_payload, ensure_ascii=False)
    except json.JSONDecodeError:
        pass
    validation = validate_test_case_output(
        enriched_json,
        requirements=requirements,
        requirement_validation_passed=requirement_passed,
        prd_validation_passed=prd_passed,
        findings_by_id=findings_by_id,
        valid_review_ids=set(_by_id(reviews or [], "id")),
        enforce_full_coverage=True,
    )
    test_cases = [asdict(test_case) for test_case in validation.test_cases] if validation.passed else []
    coverage = validation.coverage or calculate_test_coverage(requirements=requirements, test_cases=test_cases)
    generation_passed = validation.status not in {STATUS_INVALID_JSON, STATUS_SCHEMA_VALIDATION_FAILED}
    result = TestCaseGenerationResult(
        generation_status=STATUS_SUCCESS if generation_passed else validation.status,
        generation_passed=generation_passed,
        raw_output=response.raw_text,
        validation=validation,
        test_cases=test_cases,
        coverage=coverage,
        provider=response.provider,
        model=response.model,
        analysis_goal=analysis_goal,
        saved_paths={},
        extracted_json=extracted_json,
        response_metadata=response.metadata,
        is_mock=is_mock,
    )
    save_test_case_outputs(result, output_dir=output_dir)
    return result


def build_test_case_request(
    *,
    requirements: list[dict[str, Any]],
    prds: list[dict[str, Any]],
    roadmap: dict[str, Any],
    analysis_goal: str,
) -> LLMRequest:
    acceptance_criteria_index = build_acceptance_criteria_index(requirements)
    prds_by_requirement_id = _prds_by_requirement_id(prds)
    requirement_payload = []
    for requirement in requirements:
        requirement_id = requirement.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id:
            continue
        criteria = [
            {
                "acceptance_criteria_id": acceptance_criteria_id,
                "text": item["text"],
            }
            for acceptance_criteria_id, item in acceptance_criteria_index.items()
            if item["requirement_id"] == requirement_id
        ]
        requirement_payload.append(
            {
                "requirement_id": requirement_id,
                "requirement_type": requirement.get("requirement_type") or "problem",
                "title": requirement.get("title"),
                "description": requirement.get("description"),
                "priority": requirement.get("priority"),
                "acceptance_criteria": criteria,
                "prd_scope": prds_by_requirement_id.get(requirement_id, []),
            }
        )
    user_prompt = json.dumps(
        {
            "analysis_goal": analysis_goal,
            "validated_requirements": requirement_payload,
            "acceptance_criteria_index": acceptance_criteria_index,
            "roadmap_versions": roadmap.get("versions", []) if isinstance(roadmap, dict) else [],
            "coverage_requirement": "Cover every input requirement_id and every input acceptance_criteria_id at least once.",
            "requirement_type_rule": "For positive_feedback Requirements, verify preservation of the valued experience. Do not write tests as if the positive feedback were a defect complaint.",
            "recommended_output_size": "Prefer one concise Test Case per Requirement covering all of that Requirement's Acceptance Criteria when executable.",
            "required_output_schema": {
                "test_cases": [
                    {
                        "test_case_id": "TC-001",
                        "requirement_id": "REQ-001",
                        "acceptance_criteria_ids": ["REQ-001-AC-1"],
                        "title": "string",
                        "preconditions": [],
                        "steps": ["concrete executable step"],
                        "expected_result": "verifiable expected result",
                        "test_type": "functional",
                        "priority": "must equal Requirement priority",
                        "source_review_ids": [],
                    }
                ]
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    return LLMRequest(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt, analysis_goal=analysis_goal)


def build_default_mock_output(requirements: list[dict[str, Any]]) -> str:
    test_cases: list[dict[str, Any]] = []
    counter = 1
    for requirement in requirements:
        requirement_id = requirement.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id:
            continue
        acceptance_criteria = requirement.get("acceptance_criteria")
        if not isinstance(acceptance_criteria, list):
            continue
        for offset, criterion in enumerate(acceptance_criteria, start=1):
            if not isinstance(criterion, str) or not criterion.strip():
                continue
            acceptance_criteria_id = make_acceptance_criteria_id(requirement_id, offset)
            test_cases.append(
                {
                    "test_case_id": f"TC-{counter:03d}",
                    "requirement_id": requirement_id,
                    "acceptance_criteria_ids": [acceptance_criteria_id],
                    "title": f"Validate {acceptance_criteria_id}",
                    "preconditions": ["Validated requirement and PRD artifacts are available."],
                    "steps": [
                        f"Review the product behavior for {requirement_id}.",
                        f"Exercise the scenario described by {acceptance_criteria_id}: {criterion.strip()}",
                    ],
                    "expected_result": f"The product behavior satisfies {acceptance_criteria_id}: {criterion.strip()}",
                    "test_type": "functional",
                    "priority": _priority_for_requirement(requirement),
                    "source_review_ids": _list_text(requirement.get("source_review_ids")),
                }
            )
            counter += 1
    return json.dumps({"test_cases": test_cases}, ensure_ascii=False)


def create_mock_provider(raw_output: str) -> MockLLMProvider:
    return MockLLMProvider(raw_output, model="mock-test-case-model")


def create_failure_result(
    status: str,
    error: str,
    requirements: list[dict[str, Any]],
    provider: LLMProvider,
    analysis_goal: str,
    output_dir: Path,
    is_mock: bool,
) -> TestCaseGenerationResult:
    coverage = calculate_test_coverage(requirements=requirements, test_cases=[])
    validation = TestCaseValidationResult(status="SKIPPED", passed=False, errors=[error], coverage=coverage)
    result = TestCaseGenerationResult(
        generation_status=status,
        generation_passed=False,
        raw_output="",
        validation=validation,
        test_cases=[],
        coverage=coverage,
        provider=getattr(provider, "provider_name", None),
        model=getattr(provider, "model", None),
        analysis_goal=analysis_goal,
        saved_paths={},
        error=error,
        is_mock=is_mock,
    )
    save_test_case_outputs(result, output_dir=output_dir)
    return result


def save_test_case_outputs(
    result: TestCaseGenerationResult,
    *,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "test_case_generation_raw.json"
    test_cases_path = output_dir / "test_cases.json"
    validation_path = output_dir / "test_case_validation.json"
    coverage_path = output_dir / "test_coverage.json"
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
    test_cases_path.write_text(json.dumps({"test_cases": result.test_cases}, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(result.validation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    coverage_path.write_text(json.dumps(result.coverage.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    paths = {
        "raw": raw_path,
        "test_cases": test_cases_path,
        "validation": validation_path,
        "coverage": coverage_path,
    }
    result.saved_paths = {key: str(path) for key, path in paths.items()}
    return paths


def _priority_for_requirement(requirement: dict[str, Any]) -> str:
    priority = requirement.get("priority")
    return priority if isinstance(priority, str) and priority in {"P0", "P1", "P2", "P3"} else "P2"


def _validation_passed(payload: dict[str, Any]) -> bool:
    return payload.get("status") == "Success" and payload.get("passed") is True


def _prds_by_requirement_id(prds: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for prd in prds:
        if not isinstance(prd, dict):
            continue
        scope = {
            "prd_id": prd.get("prd_id"),
            "version_id": prd.get("version_id"),
            "title": prd.get("title"),
            "goals": prd.get("goals"),
            "non_goals": prd.get("non_goals"),
            "open_questions": prd.get("open_questions"),
        }
        for requirement_id in prd.get("requirement_ids", []):
            if isinstance(requirement_id, str) and requirement_id:
                result.setdefault(requirement_id, []).append(scope)
    return result


def _by_id(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {
        item[key]: item
        for item in items
        if isinstance(item, dict) and isinstance(item.get(key), str) and item.get(key)
    }


def _list_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
