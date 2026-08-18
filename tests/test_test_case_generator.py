import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.llm.base import LLMRequest, LLMResponse, ModelRequestError, ModelTimeoutError
from app.test_case_generator import (
    DEFAULT_TEST_CASE_MAX_TOKENS,
    DEEPSEEK_TEST_CASE_MAX_TOKENS,
    build_default_mock_output,
    build_test_case_request,
    create_mock_provider,
    generate_test_cases,
    save_test_case_outputs,
)


class TestCaseGeneratorTests(unittest.TestCase):
    def test_default_mock_output_covers_all_acceptance_criteria(self) -> None:
        payload = json.loads(build_default_mock_output(_requirements()))

        self.assertEqual(len(payload["test_cases"]), 3)
        self.assertEqual(payload["test_cases"][0]["acceptance_criteria_ids"], ["REQ-001-AC-1"])
        self.assertEqual(payload["test_cases"][0]["source_review_ids"], ["review-001"])
        self.assertEqual(payload["test_cases"][2]["acceptance_criteria_ids"], ["REQ-002-AC-1"])
        self.assertEqual(payload["test_cases"][2]["source_review_ids"], ["review-002"])

    def test_generate_test_cases_with_mock_provider(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = generate_test_cases(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                prd_validation=_pass_validation(),
                prds=_prds(),
                roadmap=_roadmap(),
                findings=_findings(),
                reviews=_reviews(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(result.provider, "mock")
        self.assertEqual(len(result.test_cases), 3)
        self.assertEqual(result.test_cases[0]["source_review_ids"], ["review-001"])
        self.assertEqual(result.coverage.requirement_coverage, 100.0)
        self.assertEqual(result.coverage.acceptance_criteria_coverage, 100.0)

    def test_input_validation_failure_skips_generation(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = generate_test_cases(
                requirements=_requirements(),
                requirement_validation={"status": "Failed", "passed": False},
                prd_validation=_pass_validation(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Input Validation Failed")
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(provider.requests, [])

    def test_model_request_error_skips_validation(self) -> None:
        provider = _FailingProvider(ModelRequestError("Model Request Error: failed"))
        with TemporaryDirectory() as temp_dir:
            result = generate_test_cases(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                prd_validation=_pass_validation(),
                provider=provider,
                output_dir=Path(temp_dir),
                is_mock=False,
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Model Request Error")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_timeout_skips_validation(self) -> None:
        provider = _FailingProvider(ModelTimeoutError("Timeout"))
        with TemporaryDirectory() as temp_dir:
            result = generate_test_cases(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                prd_validation=_pass_validation(),
                provider=provider,
                output_dir=Path(temp_dir),
                is_mock=False,
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Timeout")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_analysis_goal_passed_to_provider(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            generate_test_cases(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                prd_validation=_pass_validation(),
                provider=provider,
                analysis_goal="custom test goal",
                output_dir=Path(temp_dir),
            )

        self.assertEqual(provider.requests[0].analysis_goal, "custom test goal")
        self.assertIn("custom test goal", provider.requests[0].user_prompt)

    def test_build_request_contains_prd_scope_and_acceptance_criteria(self) -> None:
        request = build_test_case_request(
            requirements=_requirements(),
            prds=_prds(),
            roadmap=_roadmap(),
            analysis_goal="goal",
        )
        payload = json.loads(request.user_prompt)

        self.assertEqual(payload["analysis_goal"], "goal")
        self.assertEqual(payload["validated_requirements"][0]["requirement_id"], "REQ-001")
        self.assertEqual(
            payload["validated_requirements"][0]["acceptance_criteria"][0]["acceptance_criteria_id"],
            "REQ-001-AC-1",
        )
        self.assertEqual(payload["validated_requirements"][0]["prd_scope"][0]["prd_id"], "PRD-V1")
        self.assertEqual(request.generation_options["task"], "test_case_generation")
        self.assertEqual(request.generation_options["max_tokens"], DEFAULT_TEST_CASE_MAX_TOKENS)

    def test_test_case_max_tokens_can_be_overridden_from_env(self) -> None:
        with patch.dict(os.environ, {DEEPSEEK_TEST_CASE_MAX_TOKENS: "4500"}):
            request = build_test_case_request(
                requirements=_requirements(),
                prds=_prds(),
                roadmap=_roadmap(),
                analysis_goal="goal",
            )

        self.assertEqual(request.generation_options["max_tokens"], 4500)

    def test_invalid_test_case_max_tokens_configuration_fails_generation(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))

        with patch.dict(os.environ, {DEEPSEEK_TEST_CASE_MAX_TOKENS: "0"}):
            with TemporaryDirectory() as temp_dir:
                result = generate_test_cases(
                    requirements=_requirements(),
                    requirement_validation=_pass_validation(),
                    prd_validation=_pass_validation(),
                    prds=_prds(),
                    roadmap=_roadmap(),
                    findings=_findings(),
                    reviews=_reviews(),
                    provider=provider,
                    output_dir=Path(temp_dir),
                )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Model Request Error")
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(provider.requests, [])

    def test_save_outputs_marks_mock(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = generate_test_cases(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                prd_validation=_pass_validation(),
                prds=_prds(),
                roadmap=_roadmap(),
                findings=_findings(),
                reviews=_reviews(),
                provider=provider,
                output_dir=Path(temp_dir),
            )
            paths = save_test_case_outputs(result, output_dir=Path(temp_dir))
            raw = json.loads(paths["raw"].read_text(encoding="utf-8"))
            test_cases = json.loads(paths["test_cases"].read_text(encoding="utf-8"))
            coverage = json.loads(paths["coverage"].read_text(encoding="utf-8"))

        self.assertTrue(raw["is_mock"])
        self.assertEqual(raw["provider"], "mock")
        self.assertEqual(len(test_cases["test_cases"]), 3)
        self.assertEqual(coverage["covered_acceptance_criteria"], 3)


def _pass_validation() -> dict:
    return {"status": "Success", "passed": True}


def _requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "acceptance_criteria": ["Free access is visible.", "Free access limits are explained."],
            "priority": "P1",
            "source_review_ids": ["review-001"],
        },
        {
            "requirement_id": "REQ-002",
            "finding_ids": ["FINDING-002"],
            "acceptance_criteria": ["Subscription value is explained."],
            "priority": "P2",
            "source_review_ids": ["review-002"],
        },
    ]


def _prds() -> list[dict]:
    return [
        {
            "prd_id": "PRD-V1",
            "version_id": "V1",
            "title": "Subscription PRD",
            "requirement_ids": ["REQ-001", "REQ-002"],
            "goals": ["Improve subscription clarity"],
            "non_goals": [],
            "open_questions": [],
        }
    ]


def _roadmap() -> dict:
    return {
        "versions": [
            {
                "version_id": "V1",
                "name": "Subscription",
                "goal": "Improve subscription clarity.",
                "requirement_ids": ["REQ-001", "REQ-002"],
            }
        ]
    }


def _findings() -> list[dict]:
    return [
        {"finding_id": "FINDING-001", "review_ids": ["review-001"]},
        {"finding_id": "FINDING-002", "review_ids": ["review-002"]},
    ]


def _reviews() -> list[dict]:
    return [{"id": "review-001"}, {"id": "review-002"}]


class _FailingProvider:
    provider_name = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise self.error


if __name__ == "__main__":
    unittest.main()
