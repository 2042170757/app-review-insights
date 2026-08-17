import json
import unittest

from app.test_case_validator import (
    STATUS_SUCCESS,
    STATUS_TRACEABILITY_MISMATCH,
    enrich_test_case_source_review_ids,
    source_review_ids_for_requirement,
    validate_test_case_output,
)
from app.traceability import STATUS_FAIL, STATUS_PASS, TraceabilityArtifacts, TraceabilityGraph


class TestCaseSourceReviewsTests(unittest.TestCase):
    def test_valid_source_review_ids(self) -> None:
        result = _validate(_payload(["review-1"]))

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(result.test_cases[0].source_review_ids, ["review-1"])

    def test_unknown_review_fails(self) -> None:
        result = _validate(_payload(["review-missing"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_TRACEABILITY_MISMATCH)
        self.assertIn("unknown review_id review-missing", "\n".join(result.traceability_errors))

    def test_wrong_finding_review_fails(self) -> None:
        result = _validate(_payload(["review-2"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_TRACEABILITY_MISMATCH)
        self.assertIn("outside requirement finding evidence", "\n".join(result.traceability_errors))

    def test_empty_source_review_ids_fail_when_finding_has_evidence(self) -> None:
        result = _validate(_payload([]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_TRACEABILITY_MISMATCH)
        self.assertIn("must include review evidence", "\n".join(result.traceability_errors))

    def test_requirement_with_multiple_findings_enriches_all_source_reviews(self) -> None:
        requirement = _requirements()[1]
        findings = _findings_by_id()

        self.assertEqual(source_review_ids_for_requirement(requirement, findings), ["review-1", "review-2"])

        payload = _payload([])
        payload["test_cases"][0]["requirement_id"] = "REQ-002"
        payload["test_cases"][0]["acceptance_criteria_ids"] = ["REQ-002-AC-1"]
        enriched = enrich_test_case_source_review_ids(payload, requirements=_requirements(), findings_by_id=findings)

        self.assertEqual(enriched["test_cases"][0]["source_review_ids"], ["review-1", "review-2"])

    def test_multiple_source_reviews_validate(self) -> None:
        payload = _payload(["review-1", "review-2"])
        payload["test_cases"][0]["requirement_id"] = "REQ-002"
        payload["test_cases"][0]["acceptance_criteria_ids"] = ["REQ-002-AC-1"]
        result = _validate(payload)

        self.assertTrue(result.passed)
        self.assertEqual(result.test_cases[0].source_review_ids, ["review-1", "review-2"])

    def test_duplicate_source_review_ids_are_deduplicated(self) -> None:
        result = _validate(_payload(["review-1", "review-1"]))

        self.assertTrue(result.passed)
        self.assertEqual(result.duplicate_source_review_ids, ["review-1"])
        self.assertEqual(result.test_cases[0].source_review_ids, ["review-1"])

    def test_backward_traceability_uses_explicit_source_reviews(self) -> None:
        result = TraceabilityGraph(_artifacts()).validate()

        self.assertEqual(result.backward_traceability, STATUS_PASS)
        self.assertEqual(result.explicit_test_case_review_link, STATUS_PASS)
        self.assertEqual(result.test_case_paths[0].review_ids, ["review-1"])

    def test_backward_traceability_fails_unrelated_source_review(self) -> None:
        artifacts = _artifacts()
        artifacts.test_cases[0]["source_review_ids"] = ["review-2"]

        result = TraceabilityGraph(artifacts).validate()

        self.assertEqual(result.explicit_test_case_review_link, STATUS_FAIL)
        self.assertIn("outside requirement finding evidence", "\n".join(result.errors))


def _validate(payload: dict):
    return validate_test_case_output(
        json.dumps(payload),
        requirements=_requirements(),
        requirement_validation_passed=True,
        prd_validation_passed=True,
        findings_by_id=_findings_by_id(),
        valid_review_ids={"review-1", "review-2"},
    )


def _payload(source_review_ids: list[str]) -> dict:
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
                "source_review_ids": source_review_ids,
            }
        ]
    }


def _requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "acceptance_criteria": ["Subscription terms are visible."],
            "priority": "P1",
        },
        {
            "requirement_id": "REQ-002",
            "finding_ids": ["FINDING-001", "FINDING-002"],
            "acceptance_criteria": ["Subscription support evidence is visible."],
            "priority": "P1",
        },
    ]


def _findings_by_id() -> dict[str, dict]:
    return {
        "FINDING-001": {"finding_id": "FINDING-001", "issue_ids": ["ISSUE-001"], "review_ids": ["review-1"]},
        "FINDING-002": {"finding_id": "FINDING-002", "issue_ids": ["ISSUE-001"], "review_ids": ["review-2"]},
    }


def _artifacts() -> TraceabilityArtifacts:
    return TraceabilityArtifacts(
        reviews=[{"id": "review-1"}, {"id": "review-2"}],
        topics=[{"topic_id": "TOPIC-001", "review_ids": ["review-1"]}],
        topic_validation={"status": "Success", "passed": True},
        issues=[{"issue_id": "ISSUE-001", "topic_ids": ["TOPIC-001"], "review_ids": ["review-1"]}],
        issue_validation={"status": "Success", "passed": True},
        issue_classification={"classifications": [{"issue_id": "ISSUE-001", "issue_type": "problem"}]},
        finding_eligibility={"eligibility": [{"issue_id": "ISSUE-001", "eligible_for_finding": True}]},
        findings=[{"finding_id": "FINDING-001", "issue_ids": ["ISSUE-001"], "review_ids": ["review-1"]}],
        finding_validation={"status": "Success", "passed": True},
        evidence_report={"evidence_reports": [{"finding_id": "FINDING-001", "support_count": 1, "evidence_limitations": ["fixture"]}]},
        requirements=[
            {
                "requirement_id": "REQ-001",
                "finding_ids": ["FINDING-001"],
                "acceptance_criteria": ["Subscription terms are visible."],
                "priority": "P1",
            }
        ],
        requirement_validation={"status": "Success", "passed": True},
        priority_report={"priority_report": [{"requirement_id": "REQ-001", "final_priority": "P1"}]},
        roadmap={
            "versions": [{"version_id": "V1", "requirement_ids": ["REQ-001"]}],
            "roadmap_items": [{"requirement_id": "REQ-001", "version_id": "V1", "priority": "P1"}],
        },
        roadmap_validation={"status": "Success", "passed": True},
        prds=[{"prd_id": "PRD-V1", "version_id": "V1", "requirement_ids": ["REQ-001"], "open_questions": ["fixture"]}],
        prd_validation={"status": "Success", "passed": True},
        test_cases=[_payload(["review-1"])["test_cases"][0]],
        test_case_validation={"status": "Success", "passed": True},
        test_coverage={
            "total_requirements": 1,
            "covered_requirements": 1,
            "requirement_coverage": 100.0,
            "total_acceptance_criteria": 1,
            "covered_acceptance_criteria": 1,
            "acceptance_criteria_coverage": 100.0,
            "uncovered_requirement_ids": [],
            "uncovered_acceptance_criteria_ids": [],
        },
        processing_statistics={"total": 2},
        processing_report={"input_count": 2},
    )


if __name__ == "__main__":
    unittest.main()
