import json
import unittest

from app.finding_validator import (
    STATUS_CONFLICTING_EVIDENCE_INVALID,
    STATUS_EMPTY_FINDINGS,
    STATUS_EVIDENCE_MISMATCH,
    STATUS_INELIGIBLE_ISSUE,
    STATUS_INVALID_JSON,
    STATUS_SCHEMA_VALIDATION_FAILED,
    STATUS_SCOPE_OVERCLAIM,
    STATUS_SUCCESS,
    STATUS_SUPPORT_COUNT_MISMATCH,
    STATUS_UNKNOWN_ISSUE_ID,
    STATUS_UNKNOWN_REVIEW_ID,
    validate_finding_output,
)


class FindingValidatorTests(unittest.TestCase):
    def test_valid_finding(self) -> None:
        result = _validate(_payload())

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(result.evidence_reports[0].evidence_strength, "Medium")

    def test_invalid_json(self) -> None:
        result = _validate_raw("{not json")

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INVALID_JSON)

    def test_duplicate_finding_id(self) -> None:
        finding = _finding()
        result = _validate({"findings": [finding, finding]})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_unknown_issue_id(self) -> None:
        result = _validate(_payload(issue_ids=["ISSUE-MISSING"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_ISSUE_ID)

    def test_unknown_review_id(self) -> None:
        result = _validate(_payload(review_ids=["missing-review"], support_count=1))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_REVIEW_ID)

    def test_positive_feedback_issue_is_rejected(self) -> None:
        result = _validate(_payload(issue_ids=["ISSUE-007"], review_ids=["r7"], support_count=1))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INELIGIBLE_ISSUE)

    def test_neutral_observation_issue_is_rejected(self) -> None:
        result = _validate(_payload(issue_ids=["ISSUE-008"], review_ids=["r8"], support_count=1))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INELIGIBLE_ISSUE)

    def test_mixed_issue_is_allowed(self) -> None:
        result = _validate(_payload(issue_ids=["ISSUE-004"], review_ids=["r4"], support_count=1))

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_evidence_mismatch(self) -> None:
        result = _validate(_payload(issue_ids=["ISSUE-001"], review_ids=["r4"], support_count=1))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_EVIDENCE_MISMATCH)

    def test_support_count_mismatch(self) -> None:
        result = _validate(_payload(support_count=99))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUPPORT_COUNT_MISMATCH)

    def test_confidence_out_of_range(self) -> None:
        result = _validate(_payload(confidence=1.2))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_invalid_conflicting_review(self) -> None:
        result = _validate(_payload(conflicting_review_ids=["missing-review"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_CONFLICTING_EVIDENCE_INVALID)

    def test_conflicting_review_cannot_overlap_support(self) -> None:
        result = _validate(_payload(conflicting_review_ids=["r1"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_CONFLICTING_EVIDENCE_INVALID)

    def test_empty_findings(self) -> None:
        result = _validate({"findings": []})

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_EMPTY_FINDINGS)

    def test_scope_overclaim(self) -> None:
        result = _validate(_payload(statement="Most users report paywall friction."))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCOPE_OVERCLAIM)


def _validate(payload: dict):
    return _validate_raw(json.dumps(payload))


def _validate_raw(raw_text: str):
    return validate_finding_output(
        raw_text,
        issues_by_id={
            "ISSUE-001": {"issue_id": "ISSUE-001", "review_ids": ["r1", "r2"]},
            "ISSUE-004": {"issue_id": "ISSUE-004", "review_ids": ["r4"]},
            "ISSUE-007": {"issue_id": "ISSUE-007", "review_ids": ["r7"]},
            "ISSUE-008": {"issue_id": "ISSUE-008", "review_ids": ["r8"]},
        },
        valid_review_ids={"r1", "r2", "r3", "r4", "r7", "r8"},
        eligible_issue_ids={"ISSUE-001", "ISSUE-004"},
    )


def _payload(**overrides) -> dict:
    return {"findings": [_finding(**overrides)]}


def _finding(**overrides) -> dict:
    finding = {
        "finding_id": "FINDING-001",
        "issue_ids": ["ISSUE-001"],
        "review_ids": ["r1", "r2"],
        "title": "Paywall friction",
        "statement": "Users report paywall friction.",
        "evidence_summary": "Two reviews support this finding.",
        "support_count": 2,
        "confidence": 0.82,
        "uncertainty": "Small sample.",
        "conflicting_review_ids": [],
    }
    finding.update(overrides)
    return finding


if __name__ == "__main__":
    unittest.main()
