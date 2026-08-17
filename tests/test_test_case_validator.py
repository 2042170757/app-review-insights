import json
import unittest

from app.test_case_validator import (
    STATUS_ACCEPTANCE_CRITERION_MISMATCH,
    STATUS_DUPLICATE_TEST_CASE_ID,
    STATUS_GENERIC_TEST_CASE,
    STATUS_COVERAGE_INCOMPLETE,
    STATUS_INPUT_VALIDATION_FAILED,
    STATUS_INVALID_PRIORITY,
    STATUS_INVALID_TEST_TYPE,
    STATUS_PRIORITY_MISMATCH,
    STATUS_SCHEMA_VALIDATION_FAILED,
    STATUS_SCOPE_OVERREACH,
    STATUS_SUCCESS,
    STATUS_TRACEABILITY_MISMATCH,
    STATUS_UNKNOWN_ACCEPTANCE_CRITERION_ID,
    STATUS_UNKNOWN_REQUIREMENT_ID,
    validate_test_case_output,
)


class TestCaseValidatorTests(unittest.TestCase):
    def test_valid_test_case(self) -> None:
        result = _validate(_payload())

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(result.coverage.covered_requirements, 1)

    def test_unknown_requirement(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["requirement_id"] = "REQ-999"
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_REQUIREMENT_ID)

    def test_unknown_acceptance_criterion(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["acceptance_criteria_ids"] = ["REQ-001-AC-99"]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_ACCEPTANCE_CRITERION_ID)

    def test_acceptance_criterion_belongs_to_other_requirement(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["acceptance_criteria_ids"] = ["REQ-002-AC-1"]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_ACCEPTANCE_CRITERION_MISMATCH)

    def test_duplicate_test_case_id(self) -> None:
        payload = _payload()
        payload["test_cases"].append(dict(payload["test_cases"][0]))
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_DUPLICATE_TEST_CASE_ID)

    def test_empty_steps(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["steps"] = []
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_empty_expected_result(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["expected_result"] = ""
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_generic_test_description(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["title"] = "测试功能是否正常"
        payload["test_cases"][0]["steps"] = ["测试功能是否正常"]
        payload["test_cases"][0]["expected_result"] = "测试功能是否正常"
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_GENERIC_TEST_CASE)

    def test_invalid_test_type(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["test_type"] = "manual"
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INVALID_TEST_TYPE)

    def test_invalid_priority(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["priority"] = "P9"
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INVALID_PRIORITY)

    def test_priority_mismatch(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["priority"] = "P2"
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_PRIORITY_MISMATCH)

    def test_scope_overreach(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["steps"] = ["Test refund handling after the subscription is cancelled."]
        payload["test_cases"][0]["expected_result"] = "A refund is issued automatically."
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCOPE_OVERREACH)

    def test_multiple_test_cases_cover_same_acceptance_criterion_once(self) -> None:
        payload = _payload()
        second = dict(payload["test_cases"][0])
        second["test_case_id"] = "TC-002"
        payload["test_cases"].append(second)
        result = _validate(payload)

        self.assertTrue(result.passed)
        self.assertEqual(result.coverage.covered_acceptance_criteria, 1)

    def test_one_test_case_covers_multiple_acceptance_criteria(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["acceptance_criteria_ids"] = ["REQ-001-AC-1", "REQ-001-AC-2"]
        result = _validate(payload)

        self.assertTrue(result.passed)
        self.assertEqual(result.coverage.covered_acceptance_criteria, 2)

    def test_mixed_positive_and_negative_test_scenario(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["title"] = "Validate free access is visible before subscription"
        payload["test_cases"][0]["steps"] = [
            "Open the free access decision point.",
            "Compare the visible free access information against the subscription prompt.",
        ]
        payload["test_cases"][0]["expected_result"] = "Free access remains visible and is not hidden by the subscription prompt."
        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_boundary_test_case(self) -> None:
        payload = _payload()
        payload["test_cases"][0]["title"] = "Validate free access limit boundary"
        payload["test_cases"][0]["steps"] = ["Review the exact free access limit shown at the decision point."]
        payload["test_cases"][0]["expected_result"] = "The displayed free access limit satisfies REQ-001-AC-1."
        payload["test_cases"][0]["test_type"] = "edge_case"
        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_requirement_without_test_coverage(self) -> None:
        result = _validate(_payload())

        self.assertEqual(result.coverage.uncovered_requirement_ids, ["REQ-002"])

    def test_acceptance_criterion_without_test_coverage(self) -> None:
        result = _validate(_payload())

        self.assertIn("REQ-001-AC-2", result.coverage.uncovered_acceptance_criteria_ids)

    def test_full_coverage_enforcement(self) -> None:
        result = validate_test_case_output(
            json.dumps(_payload()),
            requirements=_requirements(),
            requirement_validation_passed=True,
            prd_validation_passed=True,
            enforce_full_coverage=True,
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_COVERAGE_INCOMPLETE)

    def test_input_validation_failed(self) -> None:
        result = validate_test_case_output(
            json.dumps(_payload()),
            requirements=_requirements(),
            requirement_validation_passed=False,
            prd_validation_passed=True,
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INPUT_VALIDATION_FAILED)

    def test_traceability_mismatch(self) -> None:
        result = validate_test_case_output(
            json.dumps(_payload()),
            requirements=_requirements(),
            requirement_validation_passed=True,
            prd_validation_passed=True,
            findings_by_id={"FINDING-001": {"finding_id": "FINDING-001", "review_ids": ["missing-review"]}},
            valid_review_ids={"review-001"},
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_TRACEABILITY_MISMATCH)


def _validate(payload: dict):
    return validate_test_case_output(
        json.dumps(payload),
        requirements=_requirements(),
        requirement_validation_passed=True,
        prd_validation_passed=True,
        findings_by_id={"FINDING-001": {"finding_id": "FINDING-001", "review_ids": ["review-001"]}},
        valid_review_ids={"review-001"},
    )


def _payload() -> dict:
    return {
        "test_cases": [
            {
                "test_case_id": "TC-001",
                "requirement_id": "REQ-001",
                "acceptance_criteria_ids": ["REQ-001-AC-1"],
                "title": "Validate subscription wording",
                "preconditions": [],
                "steps": ["Open the subscription decision point.", "Review the displayed subscription wording."],
                "expected_result": "The subscription wording satisfies REQ-001-AC-1.",
                "test_type": "functional",
                "priority": "P1",
                "source_review_ids": ["review-001"],
            }
        ]
    }


def _requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "acceptance_criteria": ["Free access is visible.", "Free access limits are explained."],
            "priority": "P1",
        },
        {
            "requirement_id": "REQ-002",
            "finding_ids": ["FINDING-001"],
            "acceptance_criteria": ["Subscription value is explained."],
            "priority": "P2",
        },
    ]


if __name__ == "__main__":
    unittest.main()
