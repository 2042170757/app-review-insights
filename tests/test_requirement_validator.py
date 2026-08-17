import json
import unittest

from app.requirement_validator import (
    STATUS_ACCEPTANCE_CRITERIA_INVALID,
    STATUS_FINDING_VALIDATION_FAILED,
    STATUS_INELIGIBLE_FINDING,
    STATUS_INVALID_JSON,
    STATUS_PRIORITY_INVALID,
    STATUS_PROHIBITED_IMPLEMENTATION_DETAIL,
    STATUS_SCHEMA_VALIDATION_FAILED,
    STATUS_SUCCESS,
    STATUS_TRACEABILITY_MISMATCH,
    STATUS_UNKNOWN_FINDING_ID,
    validate_requirement_output,
)


class RequirementValidatorTests(unittest.TestCase):
    def test_valid_requirement(self) -> None:
        result = _validate(_payload())

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(result.requirements[0].requirement_id, "REQ-001")

    def test_invalid_json(self) -> None:
        result = _validate_raw("{not json")

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INVALID_JSON)

    def test_unknown_finding(self) -> None:
        result = _validate(_payload(finding_ids=["FINDING-MISSING"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_FINDING_ID)

    def test_finding_validation_failed(self) -> None:
        result = _validate(_payload(), finding_validation_passed=False)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_FINDING_VALIDATION_FAILED)

    def test_positive_feedback_finding_is_rejected(self) -> None:
        result = _validate(_payload(finding_ids=["FINDING-POSITIVE"], source_review_ids=["r-positive"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INELIGIBLE_FINDING)

    def test_neutral_observation_finding_is_rejected(self) -> None:
        result = _validate(_payload(finding_ids=["FINDING-NEUTRAL"], source_review_ids=["r-neutral"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INELIGIBLE_FINDING)

    def test_empty_finding_ids(self) -> None:
        result = _validate(_payload(finding_ids=[]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_duplicate_requirement_id(self) -> None:
        requirement = _requirement()
        result = _validate({"requirements": [requirement, requirement]})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_empty_title(self) -> None:
        result = _validate(_payload(title=""))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_empty_description(self) -> None:
        result = _validate(_payload(description=""))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_empty_acceptance_criteria(self) -> None:
        result = _validate(_payload(acceptance_criteria=[]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_generic_acceptance_criteria(self) -> None:
        result = _validate(_payload(acceptance_criteria=["功能正常"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_ACCEPTANCE_CRITERIA_INVALID)

    def test_invalid_priority(self) -> None:
        result = _validate(_payload(priority="P4"))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_PRIORITY_INVALID)

    def test_missing_priority_rationale(self) -> None:
        requirement = _requirement()
        del requirement["priority_rationale"]
        result = _validate({"requirements": [requirement]})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_missing_uncertainty(self) -> None:
        requirement = _requirement()
        del requirement["uncertainty"]
        result = _validate({"requirements": [requirement]})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_source_review_ids_must_match_finding_evidence(self) -> None:
        result = _validate(_payload(source_review_ids=["r-outside"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_TRACEABILITY_MISMATCH)

    def test_valid_source_review_ids(self) -> None:
        result = _validate(_payload(source_review_ids=["r1"]))

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_multiple_findings_to_one_requirement(self) -> None:
        result = _validate(_payload(finding_ids=["FINDING-001", "FINDING-002"], source_review_ids=["r2"]))

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(result.requirements[0].finding_ids, ["FINDING-001", "FINDING-002"])

    def test_one_finding_to_multiple_requirements(self) -> None:
        first = _requirement(requirement_id="REQ-001")
        second = _requirement(
            requirement_id="REQ-002",
            title="Improve cancellation clarity",
            description="Users need cancellation expectations to be clear before subscription commitment.",
            acceptance_criteria=[
                "Users can identify how renewal and cancellation work before accepting subscription terms."
            ],
        )
        result = _validate({"requirements": [first, second]})

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(len(result.requirements), 2)

    def test_prohibited_implementation_detail(self) -> None:
        result = _validate(_payload(description="Build a React component for the subscription explanation."))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_PROHIBITED_IMPLEMENTATION_DETAIL)

    def test_prohibited_implementation_detail_in_risk(self) -> None:
        result = _validate(_payload(risks=["Requires PostgreSQL database schema changes."]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_PROHIBITED_IMPLEMENTATION_DETAIL)


def _validate(payload: dict, *, finding_validation_passed: bool = True):
    return _validate_raw(json.dumps(payload), finding_validation_passed=finding_validation_passed)


def _validate_raw(raw_text: str, *, finding_validation_passed: bool = True):
    return validate_requirement_output(
        raw_text,
        findings_by_id={
            "FINDING-001": {"finding_id": "FINDING-001", "review_ids": ["r1"]},
            "FINDING-002": {"finding_id": "FINDING-002", "review_ids": ["r2", "r3"]},
            "FINDING-POSITIVE": {"finding_id": "FINDING-POSITIVE", "review_ids": ["r-positive"]},
            "FINDING-NEUTRAL": {"finding_id": "FINDING-NEUTRAL", "review_ids": ["r-neutral"]},
        },
        finding_validation_passed=finding_validation_passed,
        eligible_finding_ids={"FINDING-001", "FINDING-002"},
    )


def _payload(**overrides) -> dict:
    return {"requirements": [_requirement(**overrides)]}


def _requirement(**overrides) -> dict:
    requirement = {
        "requirement_id": "REQ-001",
        "finding_ids": ["FINDING-001"],
        "title": "Clarify subscription terms",
        "description": "Users need subscription cost, renewal, and access limits explained before commitment.",
        "acceptance_criteria": [
            "Users can see trial length, renewal date, total price, and access limits before confirming."
        ],
        "priority": "P1",
        "priority_rationale": "The referenced finding is supported by direct billing and paywall evidence.",
        "risks": [],
        "success_metrics": ["Fewer future reviews mention unclear subscription terms."],
        "uncertainty": "Phase 4a validates priority shape only; final priority scoring is deferred.",
        "source_review_ids": ["r1"],
    }
    requirement.update(overrides)
    return requirement


if __name__ == "__main__":
    unittest.main()
