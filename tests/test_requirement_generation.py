import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.llm.base import (
    LLMRequest,
    LLMResponse,
    MissingAPIKeyError,
    ModelRequestError,
    ModelTimeoutError,
)
from app.requirement_generation import (
    DEFAULT_REQUIREMENT_MAX_TOKENS,
    DEEPSEEK_REQUIREMENT_MAX_TOKENS,
    STATUS_EMPTY_FINDINGS,
    STATUS_FINDING_VALIDATION_FAILED,
    STATUS_INVALID_JSON,
    STATUS_SUCCESS,
    build_requirement_request,
    calculate_requirement_input_scale,
    generate_requirements,
)


class RequirementGenerationTests(unittest.TestCase):
    def test_valid_requirement_generation(self) -> None:
        result = _generate(_raw_requirements([_requirement()]))

        self.assertTrue(result.generation_passed)
        self.assertEqual(result.generation_status, STATUS_SUCCESS)
        self.assertTrue(result.validation.passed)
        self.assertEqual(len(result.requirements), 1)
        self.assertEqual(result.provider, "mock")
        self.assertEqual(result.priority_report[0]["requirement_id"], "REQ-001")

    def test_analysis_goal_is_passed_to_provider(self) -> None:
        provider = _Provider(_raw_requirements([_requirement()]))
        with TemporaryDirectory() as temp_dir:
            generate_requirements(
                findings=_findings(),
                finding_validation=_finding_validation(),
                evidence_report=_evidence_report(),
                provider=provider,
                analysis_goal="custom analysis goal",
                output_dir=Path(temp_dir),
                is_mock=True,
            )

        self.assertEqual(provider.requests[0].analysis_goal, "custom analysis goal")
        self.assertIn("custom analysis goal", provider.requests[0].user_prompt)

    def test_requirement_request_uses_task_specific_default_max_tokens(self) -> None:
        request = build_requirement_request(
            findings=_findings(),
            evidence_report=_evidence_report(),
            analysis_goal="goal",
        )

        self.assertEqual(request.generation_options["task"], "requirement_generation")
        self.assertEqual(request.generation_options["max_tokens"], DEFAULT_REQUIREMENT_MAX_TOKENS)

    def test_requirement_max_tokens_can_be_overridden_from_env(self) -> None:
        with patch.dict(os.environ, {DEEPSEEK_REQUIREMENT_MAX_TOKENS: "4000"}):
            request = build_requirement_request(
                findings=_findings(),
                evidence_report=_evidence_report(),
                analysis_goal="goal",
            )

        self.assertEqual(request.generation_options["max_tokens"], 4000)

    def test_invalid_requirement_max_tokens_configuration_fails_generation(self) -> None:
        with patch.dict(os.environ, {DEEPSEEK_REQUIREMENT_MAX_TOKENS: "0"}):
            result = _generate(_raw_requirements([_requirement()]))

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Model Request Error")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_requirement_request_carries_prohibited_word_rule(self) -> None:
        request = build_requirement_request(
            findings=_findings(),
            evidence_report=_evidence_report(),
            analysis_goal="goal",
        )
        payload = json.loads(request.user_prompt)

        self.assertIn("prohibited_word_rule", payload)
        self.assertIn("functional", payload["prohibited_word_rule"]["terms"])
        self.assertIn("database", payload["prohibited_word_rule"]["terms"])
        self.assertIn("working", payload["prohibited_word_rule"]["instruction"])
        self.assertIn("Never use these prohibited words", request.system_prompt)

    def test_unknown_finding(self) -> None:
        result = _generate(_raw_requirements([_requirement(finding_ids=["FINDING-MISSING"])]))

        self.assertTrue(result.generation_passed)
        self.assertFalse(result.validation.passed)
        self.assertEqual(result.validation.status, "Unknown Finding ID")

    def test_finding_validation_failed_skips_provider(self) -> None:
        provider = _Provider(_raw_requirements([_requirement()]))
        with TemporaryDirectory() as temp_dir:
            result = generate_requirements(
                findings=_findings(),
                finding_validation={"status": "Schema Validation Failed", "passed": False},
                evidence_report=_evidence_report(),
                provider=provider,
                analysis_goal="goal",
                output_dir=Path(temp_dir),
                is_mock=True,
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, STATUS_FINDING_VALIDATION_FAILED)
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(provider.requests, [])

    def test_empty_findings_skips_provider(self) -> None:
        provider = _Provider(_raw_requirements([_requirement()]))
        with TemporaryDirectory() as temp_dir:
            result = generate_requirements(
                findings=[],
                finding_validation=_finding_validation(),
                evidence_report=_evidence_report(),
                provider=provider,
                analysis_goal="goal",
                output_dir=Path(temp_dir),
                is_mock=True,
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, STATUS_EMPTY_FINDINGS)
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(provider.requests, [])

    def test_multiple_findings_to_one_requirement(self) -> None:
        requirement = _requirement(finding_ids=["FINDING-001", "FINDING-002"], source_review_ids=["r2"])
        result = _generate(_raw_requirements([requirement]))

        self.assertTrue(result.validation.passed)
        self.assertEqual(result.requirements[0]["finding_ids"], ["FINDING-001", "FINDING-002"])

    def test_one_finding_to_multiple_requirements(self) -> None:
        result = _generate(
            _raw_requirements(
                [
                    _requirement(requirement_id="REQ-001"),
                    _requirement(
                        requirement_id="REQ-002",
                        title="Clarify cancellation expectations",
                        acceptance_criteria=[
                            "Users can identify cancellation conditions before accepting subscription terms."
                        ],
                    ),
                ]
            )
        )

        self.assertTrue(result.validation.passed)
        self.assertEqual(len(result.requirements), 2)

    def test_empty_acceptance_criteria(self) -> None:
        result = _generate(_raw_requirements([_requirement(acceptance_criteria=[])]))

        self.assertTrue(result.generation_passed)
        self.assertEqual(result.validation.status, "Schema Validation Failed")

    def test_generic_acceptance_criteria(self) -> None:
        result = _generate(_raw_requirements([_requirement(acceptance_criteria=["works"])]))

        self.assertTrue(result.generation_passed)
        self.assertEqual(result.validation.status, "Acceptance Criteria Invalid")

    def test_implementation_detail_leakage(self) -> None:
        result = _generate(_raw_requirements([_requirement(description="Create a React component for this flow.")]))

        self.assertTrue(result.generation_passed)
        self.assertEqual(result.validation.status, "Prohibited Implementation Detail")

    def test_invalid_priority_is_overwritten_by_priority_engine(self) -> None:
        result = _generate(_raw_requirements([_requirement(priority="P9", priority_rationale="Bad model priority.")]))

        self.assertTrue(result.validation.passed)
        self.assertIn(result.requirements[0]["priority"], {"P1", "P2", "P3"})

    def test_priority_rationale_is_generated_by_priority_engine(self) -> None:
        requirement = _requirement()
        del requirement["priority_rationale"]
        result = _generate(_raw_requirements([requirement]))

        self.assertTrue(result.validation.passed)
        self.assertIn("Deterministic priority", result.requirements[0]["priority_rationale"])

    def test_source_review_ids_mismatch(self) -> None:
        result = _generate(_raw_requirements([_requirement(source_review_ids=["r-outside"])]))

        self.assertTrue(result.generation_passed)
        self.assertEqual(result.validation.status, "Traceability Mismatch")

    def test_duplicate_requirement_id(self) -> None:
        requirement = _requirement()
        result = _generate(_raw_requirements([requirement, requirement]))

        self.assertTrue(result.generation_passed)
        self.assertEqual(result.validation.status, "Schema Validation Failed")

    def test_requirement_not_needed_empty_output(self) -> None:
        result = _generate(json.dumps({"requirements": []}))

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(result.requirements, [])

    def test_invalid_json(self) -> None:
        result = _generate("{not json")

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, STATUS_INVALID_JSON)
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_timeout_skips_validation(self) -> None:
        result = _generate_with_provider(_Provider("", error=ModelTimeoutError("Timeout")))

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Timeout")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_missing_api_key_skips_validation(self) -> None:
        result = _generate_with_provider(_Provider("", error=MissingAPIKeyError("Missing API Key")))

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Missing API Key")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_model_request_error_skips_validation(self) -> None:
        result = _generate_with_provider(_Provider("", error=ModelRequestError("Model Request Error")))

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Model Request Error")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_outputs_are_saved(self) -> None:
        provider = _Provider(_raw_requirements([_requirement()]))
        with TemporaryDirectory() as temp_dir:
            result = generate_requirements(
                findings=_findings(),
                finding_validation=_finding_validation(),
                evidence_report=_evidence_report(),
                provider=provider,
                analysis_goal="goal",
                output_dir=Path(temp_dir),
                is_mock=True,
            )
            raw = json.loads(Path(result.saved_paths["raw"]).read_text(encoding="utf-8"))
            requirements = json.loads(Path(result.saved_paths["requirements"]).read_text(encoding="utf-8"))
            validation = json.loads(Path(result.saved_paths["validation"]).read_text(encoding="utf-8"))
            priority = json.loads(Path(result.saved_paths["priority"]).read_text(encoding="utf-8"))

        self.assertEqual(raw["provider"], "mock")
        self.assertTrue(raw["is_mock"])
        self.assertEqual(raw["input_scale"]["finding_count"], 2)
        self.assertEqual(raw["input_scale"]["problem_finding_count"], 2)
        self.assertIn("input_chars", raw["input_scale"])
        self.assertEqual(raw["json_recovery"]["method"], "direct_json")
        self.assertFalse(raw["json_recovery"]["attempted"])
        self.assertEqual(len(requirements["requirements"]), 1)
        self.assertEqual(validation["status"], "Success")
        self.assertEqual(len(priority["priority_report"]), 1)

    def test_build_request_contains_findings_and_evidence(self) -> None:
        request = build_requirement_request(
            findings=_findings(),
            evidence_report=_evidence_report(),
            analysis_goal="goal",
        )
        payload = json.loads(request.user_prompt)

        self.assertEqual(payload["analysis_goal"], "goal")
        self.assertEqual(payload["validated_findings"][0]["finding_id"], "FINDING-001")
        self.assertEqual(payload["validated_findings"][0]["evidence_report"]["evidence_strength"], "High")
        self.assertEqual(payload["input_scale"]["finding_count"], 2)
        self.assertIn("Do not repeat Finding statements", payload["compact_output_rule"]["field_size"])
        self.assertIn("near-duplicate", payload["compact_output_rule"]["deduplication"])

    def test_input_scale_counts_problem_and_positive_findings(self) -> None:
        findings = [
            {**_findings()[0], "finding_type": "product_problem"},
            {**_findings()[1], "finding_type": "positive_feedback"},
        ]

        scale = calculate_requirement_input_scale(findings, _evidence_report())

        self.assertEqual(scale["finding_count"], 2)
        self.assertEqual(scale["problem_finding_count"], 1)
        self.assertEqual(scale["positive_finding_count"], 1)
        self.assertGreater(scale["input_chars"], 0)

    def test_positive_requirement_request_uses_preservation_framing(self) -> None:
        request = build_requirement_request(
            findings=[
                {
                    **_findings()[0],
                    "finding_type": "positive_feedback",
                    "title": "Short workouts are valued",
                }
            ],
            evidence_report=_evidence_report(),
            analysis_goal="positive goal",
            analysis_focus="positive_feedback_analysis",
        )
        payload = json.loads(request.user_prompt)

        self.assertEqual(payload["analysis_focus"], "positive_feedback_analysis")
        self.assertIn("preservation requirements", payload["requirement_type_rule"])
        self.assertIn("Do not frame valued experiences as problems", request.system_prompt)

    def test_positive_requirement_generation(self) -> None:
        requirement = _requirement(
            requirement_type="positive_feedback",
            title="Preserve short workout access",
            description="Preserve the valued short workout experience reflected in the review sample.",
            acceptance_criteria=["Users can still identify short workouts before starting a session."],
        )
        result = _generate(
            _raw_requirements([requirement]),
            findings=[
                {
                    **_findings()[0],
                    "finding_type": "positive_feedback",
                    "title": "Short workouts are valued",
                }
            ],
            analysis_focus="positive_feedback_analysis",
        )

        self.assertTrue(result.validation.passed)
        self.assertEqual(result.requirements[0]["requirement_type"], "positive_feedback")


def _generate(
    raw_output: str,
    *,
    findings: list[dict] | None = None,
    analysis_focus: str = "problem_analysis",
):
    return _generate_with_provider(_Provider(raw_output), findings=findings, analysis_focus=analysis_focus)


def _generate_with_provider(
    provider: "_Provider",
    *,
    findings: list[dict] | None = None,
    analysis_focus: str = "problem_analysis",
):
    with TemporaryDirectory() as temp_dir:
        return generate_requirements(
            findings=findings or _findings(),
            finding_validation=_finding_validation(),
            evidence_report=_evidence_report(),
            provider=provider,
            analysis_goal="goal",
            analysis_focus=analysis_focus,
            output_dir=Path(temp_dir),
            is_mock=True,
        )


def _raw_requirements(requirements: list[dict]) -> str:
    return json.dumps({"requirements": requirements})


def _requirement(**overrides) -> dict:
    requirement = {
        "requirement_id": "REQ-001",
        "requirement_type": "problem",
        "finding_ids": ["FINDING-001"],
        "title": "Clarify subscription terms",
        "description": "Users need subscription cost, renewal, and access limits explained before commitment.",
        "acceptance_criteria": [
            "Users can see trial length, renewal date, total price, and access limits before confirming."
        ],
        "priority": "P0",
        "priority_rationale": "Model suggested priority.",
        "risks": [],
        "success_metrics": ["Fewer future reviews mention unclear subscription terms."],
        "uncertainty": "Small sample.",
        "source_review_ids": ["r1"],
    }
    requirement.update(overrides)
    return requirement


def _findings() -> list[dict]:
    return [
        {
            "finding_id": "FINDING-001",
            "issue_ids": ["ISSUE-001"],
            "review_ids": ["r1", "r2"],
            "title": "Paywall friction",
            "statement": "Users report unclear subscription and paywall expectations.",
            "evidence_summary": "Two reviews support subscription clarity concerns.",
            "support_count": 12,
            "confidence": 0.92,
            "uncertainty": "Small sample.",
            "conflicting_review_ids": [],
        },
        {
            "finding_id": "FINDING-002",
            "issue_ids": ["ISSUE-002"],
            "review_ids": ["r2", "r3"],
            "title": "Billing confusion",
            "statement": "Users report unexpected renewal charges.",
            "evidence_summary": "Two reviews support billing clarity concerns.",
            "support_count": 4,
            "confidence": 0.8,
            "uncertainty": "Limited sample.",
            "conflicting_review_ids": [],
        },
    ]


def _finding_validation() -> dict:
    return {"status": "Success", "passed": True}


def _evidence_report() -> dict:
    return {
        "evidence_reports": [
            {
                "finding_id": "FINDING-001",
                "support_count": 12,
                "unique_support_count": 12,
                "conflicting_count": 0,
                "evidence_strength": "High",
                "evidence_limitations": [],
            },
            {
                "finding_id": "FINDING-002",
                "support_count": 4,
                "unique_support_count": 4,
                "conflicting_count": 0,
                "evidence_strength": "High",
                "evidence_limitations": [],
            },
        ]
    }


class _Provider:
    provider_name = "mock"
    model = "mock-requirement-model"

    def __init__(self, raw_text: str, *, error: Exception | None = None) -> None:
        self.raw_text = raw_text
        self.error = error
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self.error:
            raise self.error
        return LLMResponse(raw_text=self.raw_text, provider=self.provider_name, model=self.model)


if __name__ == "__main__":
    unittest.main()
