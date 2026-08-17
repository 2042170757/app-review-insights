import json
import unittest

from app.prd_generator import build_default_mock_output, build_prd_request
from app.prd_validator import validate_prd_output


class WorkflowPRDGoalTests(unittest.TestCase):
    def test_prd_request_marks_version_goal_as_required_prd_goal(self) -> None:
        request = build_prd_request(
            requirements=_requirements(),
            roadmap=_roadmap(),
            findings=_findings(),
            evidence_report={"evidence_reports": []},
            analysis_goal="分析订阅价格问题",
        )
        payload = json.loads(request.user_prompt)

        self.assertEqual(payload["analysis_goal"], "分析订阅价格问题")
        self.assertEqual(payload["validated_versions"][0]["goal"], "Improve subscription clarity.")
        self.assertEqual(payload["validated_versions"][0]["required_prd_goal"], "Improve subscription clarity.")
        self.assertIn("goals[0] must exactly equal", payload["goal_alignment_rule"])

    def test_prd_request_requires_measurable_success_metrics(self) -> None:
        request = build_prd_request(
            requirements=_requirements(),
            roadmap=_roadmap(),
            findings=_findings(),
            evidence_report={"evidence_reports": []},
            analysis_goal="分析订阅价格问题",
        )
        payload = json.loads(request.user_prompt)

        self.assertIn("success_metric_rule", payload)
        self.assertIn("observable metric", payload["success_metric_rule"])
        self.assertIn("rate", payload["success_metric_rule"])
        self.assertIn("Avoid vague standalone metrics", payload["success_metric_rule"])

    def test_analysis_goal_does_not_replace_version_goal_in_default_prd(self) -> None:
        raw_output = build_default_mock_output(roadmap=_roadmap(), requirements=_requirements())
        payload = json.loads(raw_output)

        self.assertEqual(payload["prds"][0]["goals"][0], "Improve subscription clarity.")
        self.assertNotEqual(payload["prds"][0]["goals"][0], "分析订阅价格问题")

    def test_correct_version_goal_passes_prd_validation(self) -> None:
        raw_output = json.dumps(
            {
                "prds": [
                    {
                        "prd_id": "PRD-V1",
                        "version_id": "V1",
                        "title": "Subscription clarity",
                        "overview": "Clarifies the subscription experience.",
                        "problem_statement": "Users need clearer subscription information.",
                        "evidence_summary": "FINDING-001 supports REQ-001.",
                        "goals": ["Improve subscription clarity."],
                        "non_goals": ["Do not change unrelated content workflows."],
                        "requirement_ids": ["REQ-001"],
                        "risks": [],
                        "success_metrics": ["Reduction in subscription complaints."],
                        "open_questions": ["What free access threshold should be used?"],
                    }
                ]
            }
        )

        result = validate_prd_output(
            raw_output,
            requirements_by_id={"REQ-001": _requirements()[0]},
            versions_by_id={"V1": _roadmap()["versions"][0]},
            findings_by_id={"FINDING-001": _findings()[0]},
            issues_by_id={"ISSUE-001": {"issue_id": "ISSUE-001", "topic_ids": ["TOPIC-001"], "review_ids": ["review-1"]}},
            topics_by_id={"TOPIC-001": {"topic_id": "TOPIC-001", "review_ids": ["review-1"]}},
            valid_review_ids={"review-1"},
            requirement_validation_passed=True,
            roadmap_validation_passed=True,
            finding_validation_passed=True,
        )

        self.assertTrue(result.passed)

    def test_goal_incoherence_is_still_rejected(self) -> None:
        raw_output = json.dumps(
            {
                "prds": [
                    {
                        "prd_id": "PRD-V1",
                        "version_id": "V1",
                        "title": "Workout content",
                        "overview": "Improves workout content.",
                        "problem_statement": "Users need better workouts.",
                        "evidence_summary": "FINDING-001 supports REQ-001.",
                        "goals": ["Improve workout content variety."],
                        "non_goals": [],
                        "requirement_ids": ["REQ-001"],
                        "risks": [],
                        "success_metrics": ["Reduction in subscription complaints."],
                        "open_questions": ["What exact price copy should be used?"],
                    }
                ]
            }
        )

        result = validate_prd_output(
            raw_output,
            requirements_by_id={"REQ-001": _requirements()[0]},
            versions_by_id={"V1": _roadmap()["versions"][0]},
            findings_by_id={"FINDING-001": _findings()[0]},
            issues_by_id={"ISSUE-001": {"issue_id": "ISSUE-001", "topic_ids": ["TOPIC-001"], "review_ids": ["review-1"]}},
            topics_by_id={"TOPIC-001": {"topic_id": "TOPIC-001", "review_ids": ["review-1"]}},
            valid_review_ids={"review-1"},
            requirement_validation_passed=True,
            roadmap_validation_passed=True,
            finding_validation_passed=True,
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Goal Incoherence")


def _roadmap() -> dict:
    return {
        "versions": [
            {
                "version_id": "V1",
                "name": "Subscription",
                "goal": "Improve subscription clarity.",
                "requirement_ids": ["REQ-001"],
                "risks": [],
                "success_metrics": ["Reduction in subscription complaints."],
            }
        ]
    }


def _requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "title": "Show subscription price",
            "description": "Make subscription pricing clear before purchase.",
            "acceptance_criteria": ["Subscription price is visible before purchase."],
            "priority": "P1",
            "priority_rationale": "Fixture.",
            "risks": [],
            "success_metrics": ["Reduction in subscription complaints."],
            "uncertainty": "",
            "source_review_ids": ["review-1"],
        }
    ]


def _findings() -> list[dict]:
    return [
        {
            "finding_id": "FINDING-001",
            "issue_ids": ["ISSUE-001"],
            "review_ids": ["review-1"],
            "title": "Subscription clarity",
            "statement": "Users need clearer subscription pricing.",
            "evidence_summary": "review-1 supports it.",
            "support_count": 1,
            "confidence": 0.9,
            "uncertainty": "",
            "conflicting_review_ids": [],
        }
    ]


if __name__ == "__main__":
    unittest.main()
