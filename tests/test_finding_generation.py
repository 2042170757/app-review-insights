import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.finding_generation import build_finding_request, generate_findings
from app.llm.base import LLMRequest, LLMResponse, ModelRequestError, ModelTimeoutError
from app.llm.mock_provider import MockLLMProvider


class FindingGenerationTests(unittest.TestCase):
    def test_valid_finding(self) -> None:
        result = _run(_payload())

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(len(result.findings), 1)

    def test_unknown_issue(self) -> None:
        result = _run(_payload(issue_ids=["ISSUE-MISSING"]))

        self.assertTrue(result.generation_passed)
        self.assertFalse(result.validation.passed)
        self.assertEqual(result.validation.status, "Unknown Issue ID")

    def test_unknown_review(self) -> None:
        result = _run(_payload(review_ids=["missing-review"], support_count=1))

        self.assertTrue(result.generation_passed)
        self.assertEqual(result.validation.status, "Unknown Review ID")

    def test_positive_feedback_issue(self) -> None:
        result = _run(_payload(issue_ids=["ISSUE-007"], review_ids=["r7"], support_count=1))

        self.assertEqual(result.validation.status, "Ineligible Issue")

    def test_neutral_observation_issue(self) -> None:
        result = _run(_payload(issue_ids=["ISSUE-008"], review_ids=["r8"], support_count=1))

        self.assertEqual(result.validation.status, "Ineligible Issue")

    def test_evidence_mismatch(self) -> None:
        result = _run(_payload(issue_ids=["ISSUE-001"], review_ids=["r4"], support_count=1))

        self.assertEqual(result.validation.status, "Evidence Mismatch")

    def test_support_count_mismatch(self) -> None:
        result = _run(_payload(support_count=99))

        self.assertEqual(result.validation.status, "Support Count Mismatch")

    def test_confidence_out_of_range(self) -> None:
        result = _run(_payload(confidence=1.1))

        self.assertEqual(result.validation.status, "Schema Validation Failed")

    def test_duplicate_finding_id(self) -> None:
        finding = _finding()
        result = _run({"findings": [finding, finding]})

        self.assertEqual(result.validation.status, "Schema Validation Failed")

    def test_invalid_conflicting_review(self) -> None:
        result = _run(_payload(conflicting_review_ids=["missing-review"]))

        self.assertEqual(result.validation.status, "Conflicting Evidence Invalid")

    def test_scope_overclaim(self) -> None:
        result = _run(_payload(statement="All users are blocked by the paywall."))

        self.assertEqual(result.validation.status, "Scope Overclaim")

    def test_mixed_issue(self) -> None:
        result = _run(_payload(issue_ids=["ISSUE-004"], review_ids=["r4"], support_count=1))

        self.assertTrue(result.validation.passed)

    def test_low_evidence(self) -> None:
        result = _run(_payload(review_ids=["r1"], support_count=1))

        self.assertEqual(result.evidence_reports[0]["evidence_strength"], "Low")

    def test_conflict_evidence(self) -> None:
        result = _run(_payload(issue_ids=["ISSUE-004"], review_ids=["r4"], support_count=1, conflicting_review_ids=["r5"]))

        self.assertTrue(result.validation.passed)
        self.assertEqual(result.evidence_reports[0]["conflicting_count"], 1)

    def test_invalid_json(self) -> None:
        provider = MockLLMProvider("{not json")
        with TemporaryDirectory() as temp_dir:
            result = generate_findings(
                reviews=_reviews(),
                issues=_issues(),
                classifications=_classifications(),
                eligibility=_eligibility(),
                provider=provider,
                analysis_goal="Goal",
                output_dir=Path(temp_dir),
                is_mock=True,
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Invalid JSON")
        self.assertEqual(result.validation.status, "Invalid JSON")

    def test_model_request_failure(self) -> None:
        class FailingProvider:
            provider_name = "failing"
            model = "fake"

            def generate(self, request):
                raise ModelRequestError("request failed")

        with TemporaryDirectory() as temp_dir:
            result = generate_findings(
                reviews=_reviews(),
                issues=_issues(),
                classifications=_classifications(),
                eligibility=_eligibility(),
                provider=FailingProvider(),
                analysis_goal="Goal",
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Model Request Error")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_timeout(self) -> None:
        class TimeoutProvider:
            provider_name = "timeout"
            model = "fake"

            def generate(self, request):
                raise ModelTimeoutError("timeout")

        with TemporaryDirectory() as temp_dir:
            result = generate_findings(
                reviews=_reviews(),
                issues=_issues(),
                classifications=_classifications(),
                eligibility=_eligibility(),
                provider=TimeoutProvider(),
                analysis_goal="Goal",
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Timeout")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_analysis_goal_is_passed(self) -> None:
        provider = MockLLMProvider(json.dumps(_payload()))
        with TemporaryDirectory() as temp_dir:
            generate_findings(
                reviews=_reviews(),
                issues=_issues(),
                classifications=_classifications(),
                eligibility=_eligibility(),
                provider=provider,
                analysis_goal="Exact goal",
                output_dir=Path(temp_dir),
                is_mock=True,
            )

        self.assertEqual(provider.requests[0].analysis_goal, "Exact goal")
        self.assertIn("Exact goal", provider.requests[0].user_prompt)

    def test_build_finding_request_uses_only_eligible_issues(self) -> None:
        request = build_finding_request(
            reviews=_reviews(),
            issues=_issues(),
            classifications=_classifications(),
            eligibility=_eligibility(),
            analysis_goal="Goal",
        )

        self.assertIn("ISSUE-001", request.user_prompt)
        self.assertIn("ISSUE-004", request.user_prompt)
        self.assertNotIn("ISSUE-007", request.user_prompt)
        self.assertIn("Evidence-Grounded Finding Generation", request.system_prompt)

    def test_build_finding_request_keeps_support_and_conflicts_disjoint(self) -> None:
        request = build_finding_request(
            reviews=_reviews(),
            issues=_issues(),
            classifications=_classifications(),
            eligibility=_eligibility(),
            analysis_goal="Goal",
        )
        payload = json.loads(request.user_prompt)

        self.assertIn("evidence_partition_rule", payload)
        self.assertIn("review_ids and conflicting_review_ids must be disjoint", payload["evidence_partition_rule"])
        self.assertIn("must never appear in both lists", request.system_prompt)


def _run(payload: dict):
    provider = MockLLMProvider(json.dumps(payload))
    with TemporaryDirectory() as temp_dir:
        return generate_findings(
            reviews=_reviews(),
            issues=_issues(),
            classifications=_classifications(),
            eligibility=_eligibility(),
            provider=provider,
            analysis_goal="Goal",
            output_dir=Path(temp_dir),
            is_mock=True,
        )


def _payload(**overrides) -> dict:
    return {"findings": [_finding(**overrides)]}


def _finding(**overrides) -> dict:
    finding = {
        "finding_id": "FINDING-001",
        "issue_ids": ["ISSUE-001"],
        "review_ids": ["r1", "r2"],
        "title": "Paywall friction in the sample",
        "statement": "Among the reviewed sample, users report paywall friction.",
        "evidence_summary": "Two reviews support this finding.",
        "support_count": 2,
        "confidence": 0.82,
        "uncertainty": "Limited to the current review sample.",
        "conflicting_review_ids": [],
    }
    finding.update(overrides)
    return finding


def _reviews() -> list[dict]:
    return [
        {"id": "r1", "rating": 1, "clean_title": "Paywall", "clean_body": "Paywall issue."},
        {"id": "r2", "rating": 2, "clean_title": "Subscription", "clean_body": "Subscription issue."},
        {"id": "r4", "rating": 3, "clean_title": "Workout", "clean_body": "Mixed workout issue."},
        {"id": "r5", "rating": 4, "clean_title": "Counter", "clean_body": "Conflicting evidence."},
        {"id": "r7", "rating": 5, "clean_title": "Love it", "clean_body": "Positive."},
        {"id": "r8", "rating": 3, "clean_title": "Observation", "clean_body": "Neutral."},
    ]


def _issues() -> list[dict]:
    return [
        {"issue_id": "ISSUE-001", "name": "Paywall", "description": "Paywall issue.", "review_ids": ["r1", "r2"], "confidence": 0.8, "uncertainty": ""},
        {"issue_id": "ISSUE-004", "name": "Mixed", "description": "Mixed issue.", "review_ids": ["r4", "r5"], "confidence": 0.7, "uncertainty": ""},
        {"issue_id": "ISSUE-007", "name": "Positive", "description": "Positive feedback.", "review_ids": ["r7"], "confidence": 0.9, "uncertainty": ""},
        {"issue_id": "ISSUE-008", "name": "Neutral", "description": "Neutral observation.", "review_ids": ["r8"], "confidence": 0.6, "uncertainty": ""},
    ]


def _classifications() -> list[dict]:
    return [
        {"issue_id": "ISSUE-001", "issue_type": "problem"},
        {"issue_id": "ISSUE-004", "issue_type": "mixed"},
        {"issue_id": "ISSUE-007", "issue_type": "positive_feedback"},
        {"issue_id": "ISSUE-008", "issue_type": "neutral_observation"},
    ]


def _eligibility() -> list[dict]:
    return [
        {"issue_id": "ISSUE-001", "issue_type": "problem", "eligible_for_finding": True},
        {"issue_id": "ISSUE-004", "issue_type": "mixed", "eligible_for_finding": True},
        {"issue_id": "ISSUE-007", "issue_type": "positive_feedback", "eligible_for_finding": False},
        {"issue_id": "ISSUE-008", "issue_type": "neutral_observation", "eligible_for_finding": False},
    ]


if __name__ == "__main__":
    unittest.main()
