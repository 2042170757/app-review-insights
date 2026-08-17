import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.llm.base import LLMRequest, LLMResponse
from app.requirement_generation import STATUS_INVALID_JSON, generate_requirements


class RequirementJSONRecoveryTests(unittest.TestCase):
    def test_recovery_success_from_fenced_json(self) -> None:
        result = _generate(f"```json\n{_raw_requirements([_requirement()])}\n```")

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(result.json_recovery["method"], "fenced_json")
        self.assertTrue(result.json_recovery["attempted"])

    def test_recovery_success_from_leading_text(self) -> None:
        result = _generate("Here is the result:\n" + _raw_requirements([_requirement()]))

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(result.json_recovery["method"], "embedded_json_object")

    def test_recovery_failure_skips_validation(self) -> None:
        result = _generate("{not json")

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, STATUS_INVALID_JSON)
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertFalse(result.json_recovery["success"])

    def test_raw_response_preservation_and_metadata_saved(self) -> None:
        raw_output = "Here is the result:\n" + _raw_requirements([_requirement()])
        provider = _Provider(raw_output)
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

        self.assertEqual(raw["raw_response"], raw_output)
        self.assertEqual(raw["raw_output"], raw_output)
        self.assertEqual(raw["json_recovery"]["method"], "embedded_json_object")
        self.assertTrue(raw["json_recovery"]["success"])
        self.assertEqual(raw["recovery_method"], "embedded_json_object")
        self.assertEqual(raw["extracted_response"]["requirements"][0]["requirement_id"], "REQ-001")

    def test_validator_runs_after_recovery(self) -> None:
        requirement = _requirement(title="Recovered requirement")
        result = _generate("Result:\n" + _raw_requirements([requirement]))

        self.assertTrue(result.generation_passed)
        self.assertEqual(result.validation.status, "Success")
        self.assertEqual(result.requirements[0]["title"], "Recovered requirement")

    def test_unknown_finding_after_recovery_fails_validation(self) -> None:
        result = _generate("Result:\n" + _raw_requirements([_requirement(finding_ids=["FINDING-999"])]))

        self.assertTrue(result.generation_passed)
        self.assertFalse(result.validation.passed)
        self.assertEqual(result.validation.status, "Unknown Finding ID")

    def test_unknown_review_after_recovery_fails_traceability(self) -> None:
        result = _generate("Result:\n" + _raw_requirements([_requirement(source_review_ids=["missing-review"])]))

        self.assertTrue(result.generation_passed)
        self.assertFalse(result.validation.passed)
        self.assertEqual(result.validation.status, "Traceability Mismatch")

    def test_missing_field_after_recovery_fails_schema_validation(self) -> None:
        requirement = _requirement()
        del requirement["acceptance_criteria"]
        result = _generate("Result:\n" + _raw_requirements([requirement]))

        self.assertTrue(result.generation_passed)
        self.assertFalse(result.validation.passed)
        self.assertEqual(result.validation.status, "Schema Validation Failed")

    def test_multiple_json_objects_do_not_pick_one(self) -> None:
        result = _generate(_raw_requirements([_requirement()]) + "\n" + _raw_requirements([_requirement(requirement_id="REQ-002")]))

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(result.json_recovery["method"], "multiple_json_objects")


def _generate(raw_output: str):
    with TemporaryDirectory() as temp_dir:
        return generate_requirements(
            findings=_findings(),
            finding_validation=_finding_validation(),
            evidence_report=_evidence_report(),
            provider=_Provider(raw_output),
            analysis_goal="goal",
            output_dir=Path(temp_dir),
            is_mock=True,
        )


def _raw_requirements(requirements: list[dict]) -> str:
    return json.dumps({"requirements": requirements}, ensure_ascii=False)


def _requirement(**overrides) -> dict:
    requirement = {
        "requirement_id": "REQ-001",
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


class _Provider:
    provider_name = "mock"
    model = "mock-requirement-model"

    def __init__(self, raw_text: str) -> None:
        self.raw_text = raw_text
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(raw_text=self.raw_text, provider=self.provider_name, model=self.model)


if __name__ == "__main__":
    unittest.main()
