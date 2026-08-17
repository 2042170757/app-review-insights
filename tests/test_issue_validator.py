import json
import unittest

from app.issue_validator import (
    STATUS_EMPTY_ISSUES,
    STATUS_EVIDENCE_MISMATCH,
    STATUS_INVALID_JSON,
    STATUS_SCHEMA_VALIDATION_FAILED,
    STATUS_SUCCESS,
    STATUS_UNKNOWN_REVIEW_ID,
    STATUS_UNKNOWN_TOPIC_ID,
    validate_issue_output,
)


class IssueValidatorTests(unittest.TestCase):
    def test_valid_issue_output(self) -> None:
        result = _validate(_payload())

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(result.issues[0].issue_id, "ISSUE-001")
        self.assertEqual(result.unmerged_topic_ids, [])

    def test_invalid_json(self) -> None:
        result = _validate_raw("{not json")

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INVALID_JSON)

    def test_unknown_topic_id(self) -> None:
        payload = _payload(topic_ids=["TOPIC-MISSING"])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_TOPIC_ID)

    def test_unknown_review_id(self) -> None:
        payload = _payload(review_ids=["missing-review"])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_REVIEW_ID)

    def test_duplicate_issue_id(self) -> None:
        issue = _issue()
        result = _validate({"issues": [issue, issue], "unmerged_topic_ids": []})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_confidence_out_of_range(self) -> None:
        result = _validate(_payload(confidence=1.2))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_missing_merge_rationale(self) -> None:
        issue = _issue()
        del issue["merge_rationale"]

        result = _validate({"issues": [issue], "unmerged_topic_ids": []})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_empty_issues(self) -> None:
        result = _validate({"issues": [], "unmerged_topic_ids": ["TOPIC-002"]})

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_EMPTY_ISSUES)
        self.assertEqual(result.warnings, ["empty_issues"])
        self.assertEqual(result.unmerged_topic_ids, ["TOPIC-002"])

    def test_unknown_unmerged_topic_id(self) -> None:
        result = _validate({"issues": [], "unmerged_topic_ids": ["TOPIC-MISSING"]})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_TOPIC_ID)

    def test_evidence_mismatch_is_fail(self) -> None:
        payload = _payload(topic_ids=["TOPIC-002"], review_ids=["r1"])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_EVIDENCE_MISMATCH)

    def test_missing_required_id_lists(self) -> None:
        result = _validate(_payload(topic_ids=[], review_ids=[]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)


def _validate(payload: dict):
    return _validate_raw(json.dumps(payload))


def _validate_raw(raw_text: str):
    return validate_issue_output(
        raw_text,
        valid_topic_ids={"TOPIC-001", "TOPIC-002"},
        valid_review_ids={"r1", "r2", "r3"},
        topic_review_ids={
            "TOPIC-001": {"r1", "r2"},
            "TOPIC-002": {"r3"},
        },
    )


def _payload(**overrides) -> dict:
    issue = _issue(**overrides)
    return {"issues": [issue], "unmerged_topic_ids": []}


def _issue(**overrides) -> dict:
    issue = {
        "issue_id": "ISSUE-001",
        "name": "Subscription transparency",
        "description": "Users describe subscription terms as unclear.",
        "topic_ids": ["TOPIC-001"],
        "review_ids": ["r1", "r2"],
        "merge_rationale": "Both reviews support the same subscription transparency problem.",
        "confidence": 0.86,
        "uncertainty": "Limited to provided topic evidence.",
    }
    issue.update(overrides)
    return issue


if __name__ == "__main__":
    unittest.main()
