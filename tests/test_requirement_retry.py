import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.llm.base import (
    LLMRequest,
    LLMResponse,
    ModelAuthenticationError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from app.requirement_generation import (
    STATUS_INVALID_JSON,
    STATUS_SUCCESS,
    build_requirement_json_retry_request,
    generate_requirements,
)


class RequirementJSONRetryTests(unittest.TestCase):
    def test_first_response_valid_json_does_not_retry(self) -> None:
        provider = _SequenceProvider([_raw_requirements([_requirement()])])
        result = _generate(provider)

        self.assertTrue(result.generation_passed)
        self.assertEqual(result.generation_status, STATUS_SUCCESS)
        self.assertTrue(result.validation.passed)
        self.assertEqual(len(provider.requests), 1)
        self.assertFalse(result.json_recovery["retry_attempted"])

    def test_first_response_fenced_json_does_not_retry(self) -> None:
        provider = _SequenceProvider([f"```json\n{_raw_requirements([_requirement()])}\n```"])
        result = _generate(provider)

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(result.json_recovery["method"], "fenced_json")
        self.assertFalse(result.json_recovery["retry_attempted"])

    def test_malformed_json_retries_once_and_validates_success(self) -> None:
        provider = _SequenceProvider(["not json at all", _raw_requirements([_requirement()])])
        result = _generate(provider)

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(result.json_recovery["initial_method"], "invalid_json")
        self.assertFalse(result.json_recovery["initial_success"])
        self.assertTrue(result.json_recovery["retry_attempted"])
        self.assertTrue(result.json_recovery["retry_success"])
        self.assertEqual(result.json_recovery["retry_recovery_method"], "direct_json")

    def test_invalid_json_retry_invalid_json_fails_without_third_call(self) -> None:
        provider = _SequenceProvider(["not json at all", "still not json"], fallback="third response")
        result = _generate(provider)

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, STATUS_INVALID_JSON)
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(len(provider.requests), 2)
        self.assertTrue(result.json_recovery["retry_attempted"])
        self.assertFalse(result.json_recovery["retry_success"])

    def test_timeout_does_not_retry(self) -> None:
        provider = _SequenceProvider([ModelTimeoutError("timeout")])
        result = _generate(provider)

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Timeout")
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(len(provider.requests), 1)

    def test_auth_error_does_not_retry(self) -> None:
        provider = _SequenceProvider([ModelAuthenticationError("auth failed")])
        result = _generate(provider)

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Authentication Error")
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(len(provider.requests), 1)

    def test_rate_limit_does_not_retry(self) -> None:
        provider = _SequenceProvider([ModelRateLimitError("rate limited")])
        result = _generate(provider)

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Rate Limit")
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(len(provider.requests), 1)

    def test_schema_failure_after_valid_json_does_not_retry(self) -> None:
        requirement = _requirement()
        del requirement["title"]
        provider = _SequenceProvider([_raw_requirements([requirement])])
        result = _generate(provider)

        self.assertTrue(result.generation_passed)
        self.assertFalse(result.validation.passed)
        self.assertEqual(result.validation.status, "Schema Validation Failed")
        self.assertEqual(len(provider.requests), 1)
        self.assertFalse(result.json_recovery["retry_attempted"])

    def test_unknown_finding_after_valid_json_does_not_retry(self) -> None:
        provider = _SequenceProvider([_raw_requirements([_requirement(finding_ids=["FINDING-404"])])])
        result = _generate(provider)

        self.assertTrue(result.generation_passed)
        self.assertFalse(result.validation.passed)
        self.assertEqual(result.validation.status, "Unknown Finding ID")
        self.assertEqual(len(provider.requests), 1)
        self.assertFalse(result.json_recovery["retry_attempted"])

    def test_retry_preserves_initial_and_retry_raw_responses(self) -> None:
        initial_raw = "not json at all"
        retry_raw = _raw_requirements([_requirement()])
        provider = _SequenceProvider([initial_raw, retry_raw])

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

        self.assertEqual(raw["initial_raw_response"], initial_raw)
        self.assertEqual(raw["retry_raw_response"], retry_raw)
        self.assertEqual(raw["raw_response"], retry_raw)
        self.assertEqual(raw["extracted_response"]["requirements"][0]["requirement_id"], "REQ-001")
        self.assertTrue(raw["json_recovery"]["retry_attempted"])
        self.assertTrue(raw["json_recovery"]["retry_success"])

    def test_retry_uses_same_provider_and_model(self) -> None:
        provider = _SequenceProvider(["not json", _raw_requirements([_requirement()])], model="same-model")
        result = _generate(provider)

        self.assertEqual(result.provider, "mock")
        self.assertEqual(result.model, "same-model")
        self.assertEqual(len(provider.requests), 2)

    def test_retry_request_keeps_original_business_input(self) -> None:
        original_payload = {
            "analysis_focus": "problem_analysis",
            "valid_finding_ids": ["FINDING-001"],
            "validated_findings": [
                {
                    "finding_id": "FINDING-001",
                    "finding_type": "product_problem",
                    "review_ids": ["review-001"],
                    "statement": "Long statement excluded from compact retry context.",
                }
            ],
            "required_output_schema": {"requirements": []},
            "requirement_type_rule": "Use requirement_type=problem.",
        }
        original = LLMRequest(
            system_prompt="system business prompt",
            user_prompt=json.dumps(original_payload),
            analysis_goal="goal",
        )
        retry = build_requirement_json_retry_request(original_request=original, invalid_response="bad response")
        payload = json.loads(retry.user_prompt)
        context = payload["original_business_context"]

        self.assertEqual(context["analysis_goal"], original.analysis_goal)
        self.assertEqual(context["system_rules"], original.system_prompt)
        self.assertEqual(context["valid_finding_ids"], ["FINDING-001"])
        self.assertEqual(context["required_output_schema"], {"requirements": []})
        self.assertEqual(context["validated_findings"][0]["finding_id"], "FINDING-001")
        self.assertEqual(context["validated_findings"][0]["review_ids"], ["review-001"])
        self.assertNotIn("statement", context["validated_findings"][0])
        self.assertEqual(payload["previous_invalid_response"], "bad response")
        self.assertIn("Do not change business semantics", retry.system_prompt)
        self.assertIn("Do not add Requirements", payload["instruction"])


def _generate(provider: "_SequenceProvider"):
    with TemporaryDirectory() as temp_dir:
        return generate_requirements(
            findings=_findings(),
            finding_validation=_finding_validation(),
            evidence_report=_evidence_report(),
            provider=provider,
            analysis_goal="goal",
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
        "priority": "P2",
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
        }
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
            }
        ]
    }


class _SequenceProvider:
    provider_name = "mock"

    def __init__(self, outputs: list[str | Exception], *, fallback: str = "", model: str = "mock-requirement-model") -> None:
        self.outputs = list(outputs)
        self.fallback = fallback
        self.model = model
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        output = self.outputs.pop(0) if self.outputs else self.fallback
        if isinstance(output, Exception):
            raise output
        return LLMResponse(raw_text=output, provider=self.provider_name, model=self.model)


if __name__ == "__main__":
    unittest.main()
