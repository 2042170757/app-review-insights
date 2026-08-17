"""Mock test case generation orchestration for Phase 7a."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.llm.base import LLMProvider, LLMRequest
from app.llm.mock_provider import MockLLMProvider
from app.test_case_validator import (
    TestCaseValidationResult,
    validate_test_case_output,
)
from app.test_coverage import TestCoverageReport, build_acceptance_criteria_index, calculate_test_coverage, make_acceptance_criteria_id
from app.topic_discovery import extract_json_text


STATUS_SUCCESS = "Success"
STATUS_INPUT_VALIDATION_FAILED = "Input Validation Failed"


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
    saved_paths: dict[str, str]
    extracted_json: str | None = None
    error: str | None = None
    is_mock: bool = True


def generate_test_cases(
    *,
    requirements: list[dict[str, Any]],
    requirement_validation: dict[str, Any],
    prd_validation: dict[str, Any],
    provider: LLMProvider,
    findings: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
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
            output_dir,
            is_mock,
        )

    request = LLMRequest(
        system_prompt="Phase 7a mock test case generation. Do not call a production model.",
        user_prompt=json.dumps(
            {
                "validated_requirements": requirements,
                "acceptance_criteria_index": build_acceptance_criteria_index(requirements),
                "note": "Mock-only test case generation for schema, validator, and coverage validation.",
            },
            ensure_ascii=False,
        ),
        analysis_goal="mock_test_case_generation",
    )
    response = provider.generate(request)
    extracted_json = extract_json_text(response.raw_text)
    validation = validate_test_case_output(
        extracted_json,
        requirements=requirements,
        requirement_validation_passed=requirement_passed,
        prd_validation_passed=prd_passed,
        findings_by_id=_by_id(findings or [], "finding_id"),
        valid_review_ids=set(_by_id(reviews or [], "id")),
    )
    test_cases = [asdict(test_case) for test_case in validation.test_cases] if validation.passed else []
    coverage = validation.coverage or calculate_test_coverage(requirements=requirements, test_cases=test_cases)
    result = TestCaseGenerationResult(
        generation_status=STATUS_SUCCESS if validation.passed else validation.status,
        generation_passed=validation.passed,
        raw_output=response.raw_text,
        validation=validation,
        test_cases=test_cases,
        coverage=coverage,
        provider=response.provider,
        model=response.model,
        saved_paths={},
        extracted_json=extracted_json,
        is_mock=is_mock,
    )
    save_test_case_outputs(result, output_dir=output_dir)
    return result


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
                "generation_status": result.generation_status,
                "raw_output": result.raw_output,
                "extracted_json": result.extracted_json,
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


def _by_id(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {
        item[key]: item
        for item in items
        if isinstance(item, dict) and isinstance(item.get(key), str) and item.get(key)
    }
