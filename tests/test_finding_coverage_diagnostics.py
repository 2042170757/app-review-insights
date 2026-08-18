import json
import unittest

from app.finding_coverage_diagnostics import diagnose_finding_coverage_payloads


class FindingCoverageDiagnosticsTests(unittest.TestCase):
    def test_eligible_issue_with_finding(self) -> None:
        report = _diagnose(
            raw_findings=[_finding(issue_ids=["ISSUE-012"])],
            findings=[_finding(issue_ids=["ISSUE-012"])],
        )

        self.assertTrue(report["eligible_for_finding"])
        self.assertTrue(report["finding_generation_input_contains_issue"])
        self.assertTrue(report["finding_generated"])
        self.assertTrue(report["finding_generated_in_raw"])

    def test_eligible_issue_without_finding(self) -> None:
        report = _diagnose(raw_findings=[], findings=[])

        self.assertTrue(report["eligible_for_finding"])
        self.assertTrue(report["finding_generation_input_contains_issue"])
        self.assertFalse(report["finding_generated"])
        self.assertEqual(report["root_cause"], "Model Omission")

    def test_ineligible_positive_feedback(self) -> None:
        report = _diagnose(
            issue=_positive_issue(),
            classifications=[{"issue_id": "ISSUE-012", "issue_type": "positive_feedback"}],
            eligibility=[
                {
                    "issue_id": "ISSUE-012",
                    "issue_type": "positive_feedback",
                    "eligible_for_finding": False,
                    "finding_type": "positive_feedback",
                }
            ],
            raw_findings=[],
            findings=[],
        )

        self.assertFalse(report["eligible_for_finding"])
        self.assertFalse(report["finding_generation_input_contains_issue"])
        self.assertEqual(report["root_cause"], "Expected Exclusion")

    def test_insufficient_evidence(self) -> None:
        issue = _problem_issue(review_ids=["r1"])
        report = _diagnose(issue=issue, reviews=[_review("r1", rating=1)], raw_findings=[], findings=[])

        self.assertEqual(report["supporting_review_count"], 1)
        self.assertEqual(report["evidence_strength"], "Low")
        self.assertEqual(report["root_cause"], "Evidence Insufficient")

    def test_finding_validator_failure(self) -> None:
        report = _diagnose(
            raw_findings=[_finding(issue_ids=["ISSUE-012"])],
            findings=[],
            finding_validation={
                "status": "Unknown Review ID",
                "passed": False,
                "errors": ["findings[0].review_ids: unknown review id missing-review"],
            },
        )

        self.assertTrue(report["finding_generated_in_raw"])
        self.assertFalse(report["finding_generated"])
        self.assertEqual(report["finding_validation"], "Unknown Review ID")
        self.assertEqual(report["root_cause"], "Validator Bug")

    def test_unknown_issue(self) -> None:
        report = _diagnose(issues=[], raw_findings=[], findings=[])

        self.assertFalse(report["issue_exists"])
        self.assertEqual(report["root_cause"], "Unknown / Requires Further Investigation")

    def test_finding_generation_omission_with_wrong_issue_output(self) -> None:
        report = _diagnose(
            raw_findings=[_finding(issue_ids=["ISSUE-999"])],
            findings=[_finding(issue_ids=["ISSUE-999"])],
        )

        self.assertTrue(report["finding_generation_input_contains_issue"])
        self.assertFalse(report["finding_generated_in_raw"])
        self.assertEqual(report["raw_findings_with_other_issue_ids"][0]["issue_ids"], ["ISSUE-999"])
        self.assertEqual(report["root_cause"], "Model Omission")

    def test_traceability_diagnosis(self) -> None:
        report = _diagnose(
            raw_findings=[],
            findings=[],
            traceability_report={"critical_issues": ["ISSUE-012: eligible issue has no downstream finding"]},
        )

        self.assertEqual(
            report["traceability_rule"],
            "Eligible Issues are expected to have at least one downstream Finding.",
        )
        self.assertEqual(report["traceability_errors_for_issue"], ["ISSUE-012: eligible issue has no downstream finding"])

    def test_positive_feedback_misclassified_as_mixed_is_classification_bug(self) -> None:
        report = _diagnose(
            issue=_positive_issue(),
            reviews=[_review("r1", rating=5, body="I love this app."), _review("r2", rating=5, body="Great app.")],
            classifications=[{"issue_id": "ISSUE-012", "issue_type": "mixed"}],
            eligibility=[
                {
                    "issue_id": "ISSUE-012",
                    "issue_type": "mixed",
                    "eligible_for_finding": True,
                    "finding_type": "product_problem",
                    "reason": "Mixed issues are eligible.",
                }
            ],
            raw_findings=[],
            findings=[],
        )

        self.assertTrue(report["positive_feedback_likely"])
        self.assertEqual(report["issue_type"], "mixed")
        self.assertEqual(report["root_cause"], "Classification Bug")


def _diagnose(**overrides):
    issue = overrides.get("issue", _problem_issue())
    reviews = overrides.get("reviews", [_review("r1"), _review("r2")])
    raw_findings = overrides.get("raw_findings", [])
    payload = {
        "issue_id": "ISSUE-012",
        "reviews": reviews,
        "issues": overrides.get("issues", [issue]),
        "classifications": overrides.get("classifications", [{"issue_id": "ISSUE-012", "issue_type": "problem"}]),
        "eligibility": overrides.get(
            "eligibility",
            [
                {
                    "issue_id": "ISSUE-012",
                    "issue_type": "problem",
                    "eligible_for_finding": True,
                    "finding_type": "product_problem",
                    "reason": "Problem issues are eligible.",
                }
            ],
        ),
        "raw_generation": overrides.get(
            "raw_generation",
            {
                "analysis_goal": "Goal",
                "analysis_focus": "problem_analysis",
                "raw_output": json.dumps({"findings": raw_findings}),
                "extracted_json": json.dumps({"findings": raw_findings}),
            },
        ),
        "findings": overrides.get("findings", []),
        "finding_validation": overrides.get("finding_validation", {"status": "Success", "passed": True, "errors": []}),
        "evidence_reports": overrides.get("evidence_reports", []),
        "traceability_report": overrides.get("traceability_report", {}),
    }
    return diagnose_finding_coverage_payloads(**payload)


def _problem_issue(review_ids=None):
    return {
        "issue_id": "ISSUE-012",
        "name": "Search failure",
        "description": "Users cannot reliably search articles.",
        "topic_ids": ["TOPIC-001"],
        "review_ids": review_ids or ["r1", "r2"],
        "merge_rationale": "The reviews describe the same search failure.",
        "confidence": 0.8,
        "uncertainty": "Small sample.",
    }


def _positive_issue():
    return {
        "issue_id": "ISSUE-012",
        "name": "Positive feedback and appreciation",
        "description": "Users express overall satisfaction with the app and praise its usefulness.",
        "topic_ids": ["TOPIC-012"],
        "review_ids": ["r1", "r2"],
        "merge_rationale": "This is not a product problem but is preserved for deterministic classification.",
        "confidence": 0.95,
        "uncertainty": "High confidence as reviews are clearly positive.",
    }


def _finding(issue_ids=None):
    return {
        "finding_id": "FINDING-001",
        "finding_type": "product_problem",
        "issue_ids": issue_ids or ["ISSUE-012"],
        "review_ids": ["r1", "r2"],
        "title": "Search failure",
        "statement": "The current review sample reports search failure.",
        "evidence_summary": "Two reviews support this finding.",
        "support_count": 2,
        "confidence": 0.8,
        "uncertainty": "Small sample.",
        "conflicting_review_ids": [],
    }


def _review(review_id: str, *, rating: int = 1, body: str = "Search does not work."):
    return {
        "id": review_id,
        "rating": rating,
        "clean_title": "Review",
        "clean_body": body,
        "language": "en",
        "created_at": "2026-08-18T00:00:00Z",
    }


if __name__ == "__main__":
    unittest.main()
