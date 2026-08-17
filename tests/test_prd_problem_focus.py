import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.prd_generator import create_mock_provider, generate_prds
from app.prd_validator import STATUS_SUCCESS, STATUS_SUCCESS_METRIC_INVALID, validate_prd_output


class PRDProblemFocusMetricTests(unittest.TestCase):
    def test_measurable_score_metric_passes(self) -> None:
        payload = _payload(success_metrics=["User satisfaction score with workout content"])

        result = _validate(payload)

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_user_reported_and_number_metrics_pass(self) -> None:
        payload = _payload(
            success_metrics=[
                "User-reported notification satisfaction",
                "Number of user-reported freezes during export",
            ]
        )

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_vague_satisfaction_metric_still_fails(self) -> None:
        payload = _payload(success_metrics=["Improve user satisfaction"])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_empty_metrics_with_metric_open_question_passes(self) -> None:
        payload = _payload(
            success_metrics=[],
            open_questions=[
                "What measurable success metric should define content quality improvement?",
                "What target should be used for any workout content satisfaction score?",
            ],
        )

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_empty_metrics_without_metric_open_question_fails(self) -> None:
        payload = _payload(success_metrics=[], open_questions=["Confirm rollout order."])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_unsupported_numeric_target_still_fails(self) -> None:
        payload = _payload(success_metrics=["Decrease content quality complaints by 20%."])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_evidence_backed_numeric_target_passes(self) -> None:
        payload = _payload(success_metrics=["Decrease content quality complaints by 20%."])
        requirements = _requirements_by_id()
        requirements["REQ-004"]["success_metrics"] = ["Decrease content quality complaints by 20%."]

        result = _validate(payload, requirements_by_id=requirements)

        self.assertTrue(result.passed)

    def test_duplicate_metric_still_fails(self) -> None:
        payload = _payload(
            success_metrics=[
                "User satisfaction score with workout content",
                "User satisfaction score with workout content",
            ]
        )

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_problem_focus_mock_prd_accepts_score_metric(self) -> None:
        raw_output = json.dumps(_payload(success_metrics=["User satisfaction score with workout content"]))
        provider = create_mock_provider(raw_output)

        with TemporaryDirectory() as temp_dir:
            result = generate_prds(
                requirements=list(_requirements_by_id().values()),
                requirement_validation=_pass_validation(),
                roadmap=_roadmap(),
                roadmap_validation=_pass_validation(),
                findings=list(_findings_by_id().values()),
                finding_validation=_pass_validation(),
                issues=list(_issues_by_id().values()),
                topics=list(_topics_by_id().values()),
                reviews=_reviews(),
                provider=provider,
                analysis_goal="基于已验证 Roadmap Version、Requirements、Findings 与 Evidence 生成 PRD。",
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(result.prds[0]["success_metrics"], ["User satisfaction score with workout content"])

    def test_positive_focus_empty_metrics_still_passes(self) -> None:
        payload = _payload(
            success_metrics=[],
            requirement_type="positive_feedback",
            open_questions=[
                "What measurable success metric should define preservation of this valued experience?",
                "What target should be set for preserving positive user feedback?",
            ],
        )
        requirements = _requirements_by_id(requirement_type="positive_feedback")

        result = _validate(payload, requirements_by_id=requirements)

        self.assertTrue(result.passed)


def _validate(payload: dict, *, requirements_by_id: dict | None = None):
    return validate_prd_output(
        json.dumps(payload),
        requirements_by_id=requirements_by_id or _requirements_by_id(),
        versions_by_id=_versions_by_id(),
        findings_by_id=_findings_by_id(),
        issues_by_id=_issues_by_id(),
        topics_by_id=_topics_by_id(),
        valid_review_ids={"review-001"},
        requirement_validation_passed=True,
        roadmap_validation_passed=True,
        finding_validation_passed=True,
    )


def _payload(
    *,
    success_metrics: list[str],
    open_questions: list[str] | None = None,
    requirement_type: str = "problem",
) -> dict:
    statement = (
        "Users value the workout content and need that value preserved."
        if requirement_type == "positive_feedback"
        else "Users report declining workout content quality."
    )
    return {
        "prds": [
            {
                "prd_id": "PRD-V1",
                "version_id": "V1",
                "title": "Workout content quality PRD",
                "overview": "Define workout content quality scope.",
                "problem_statement": statement,
                "evidence_summary": "Evidence is traceable through REQ-004 and FINDING-004.",
                "goals": ["Improve workout content quality."],
                "non_goals": ["Do not expand scope beyond validated requirements."],
                "requirement_ids": ["REQ-004"],
                "risks": ["Content quality perception may remain subjective."],
                "success_metrics": success_metrics,
                "open_questions": open_questions
                or [
                    "What measurable success target should be set for workout content quality?",
                ],
            }
        ]
    }


def _pass_validation() -> dict:
    return {"status": "Success", "passed": True}


def _roadmap() -> dict:
    return {
        "versions": [
            {
                "version_id": "V1",
                "name": "Workout Content",
                "goal": "Improve workout content quality.",
                "requirement_ids": ["REQ-004"],
                "risks": [],
                "success_metrics": ["User satisfaction score with workout content"],
            }
        ]
    }


def _versions_by_id() -> dict:
    return {item["version_id"]: item for item in _roadmap()["versions"]}


def _requirements_by_id(*, requirement_type: str = "problem") -> dict:
    return {
        "REQ-004": {
            "requirement_id": "REQ-004",
            "requirement_type": requirement_type,
            "title": "Improve workout content quality",
            "description": "Workout content quality should address user complaints.",
            "acceptance_criteria": ["Users can identify refreshed workout content."],
            "finding_ids": ["FINDING-004"],
            "success_metrics": ["User satisfaction score with workout content"],
        }
    }


def _findings_by_id() -> dict:
    return {
        "FINDING-004": {
            "finding_id": "FINDING-004",
            "title": "Declining content quality",
            "statement": "Users report declining workout content quality.",
            "issue_ids": ["ISSUE-004"],
            "review_ids": ["review-001"],
        }
    }


def _issues_by_id() -> dict:
    return {"ISSUE-004": {"issue_id": "ISSUE-004", "topic_ids": ["TOPIC-004"], "review_ids": ["review-001"]}}


def _topics_by_id() -> dict:
    return {"TOPIC-004": {"topic_id": "TOPIC-004", "review_ids": ["review-001"]}}


def _reviews() -> list[dict]:
    return [{"id": "review-001"}]


if __name__ == "__main__":
    unittest.main()
