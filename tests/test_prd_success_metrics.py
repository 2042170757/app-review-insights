import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.prd_generator import create_mock_provider, generate_prds
from app.prd_validator import STATUS_SUCCESS, STATUS_SUCCESS_METRIC_INVALID, validate_prd_output


class PRDSuccessMetricsTests(unittest.TestCase):
    def test_valid_metric_passes(self) -> None:
        payload = _payload(success_metrics=["Cancellation completion rate."])

        result = _validate(payload)

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_empty_metrics_with_open_question_passes(self) -> None:
        payload = _payload(
            success_metrics=[],
            open_questions=[
                "What measurable success metric should define successful subscription clarity?",
                "What proportion of the library should remain free?",
            ],
        )

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_empty_metrics_without_metric_open_question_fails(self) -> None:
        payload = _payload(success_metrics=[], open_questions=["Confirm final launch sequencing."])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_vague_metric_fails(self) -> None:
        payload = _payload(success_metrics=["Increase engagement"])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_metric_definition_missing_fails(self) -> None:
        payload = _payload(success_metrics=["Subscription clarity"])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_unsupported_numeric_target_fails(self) -> None:
        payload = _payload(success_metrics=["Decrease subscription complaints by 20%."])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_evidence_backed_numeric_target_passes(self) -> None:
        payload = _payload(success_metrics=["Decrease subscription complaints by 10%."])
        requirements = _requirements_by_id()
        requirements["REQ-001"]["success_metrics"] = ["Decrease subscription complaints by 10%."]

        result = _validate(payload, requirements_by_id=requirements)

        self.assertTrue(result.passed)

    def test_multiple_metrics_pass(self) -> None:
        payload = _payload(
            success_metrics=[
                "Cancellation completion rate.",
                "Percentage of users who can identify renewal price before confirmation.",
                "Average task completion time.",
            ]
        )

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_duplicate_metrics_fail(self) -> None:
        payload = _payload(success_metrics=["Cancellation completion rate.", "Cancellation completion rate."])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_unknown_goal_allows_empty_metrics_when_open_question_exists(self) -> None:
        raw_output = json.dumps(
            _payload(
                success_metrics=[],
                open_questions=[
                    "What measurable success metric or target should define long-term value preservation?",
                    "What proportion of the library should remain free?",
                ],
            )
        )
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
                analysis_goal="分析高评分用户为什么愿意长期使用这个 App，以及哪些体验值得保留",
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(result.prds[0]["success_metrics"], [])

    def test_positive_goal_metric_definition_can_pass(self) -> None:
        payload = _payload(success_metrics=["Retention rate of users engaging with the highlighted experience."])

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_json_import_style_empty_metrics_pass(self) -> None:
        payload = _payload(
            success_metrics=[],
            open_questions=[
                "What measurable success metric should define success for this imported JSON review dataset?",
                "What proportion of the library should remain free?",
            ],
        )

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_csv_import_style_empty_metrics_pass(self) -> None:
        payload = _payload(
            success_metrics=[],
            open_questions=[
                "What measurable success metric should define success for this imported CSV review dataset?",
                "What proportion of the library should remain free?",
            ],
        )

        result = _validate(payload)

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


def _payload(*, success_metrics: list[str], open_questions: list[str] | None = None) -> dict:
    return {
        "prds": [
            {
                "prd_id": "PRD-V1",
                "version_id": "V1",
                "title": "Subscription clarity PRD",
                "overview": "Define subscription clarity scope.",
                "problem_statement": "Users need clearer subscription terms.",
                "evidence_summary": "Evidence is traceable through REQ-001 and FINDING-001.",
                "goals": ["Improve subscription billing clarity"],
                "non_goals": ["Do not expand scope beyond validated requirements."],
                "requirement_ids": ["REQ-001"],
                "risks": ["Metric target may require product decision."],
                "success_metrics": success_metrics,
                "open_questions": open_questions
                or [
                    "What measurable success target should be set for subscription clarity?",
                    "What proportion of the library should remain free?",
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
                "name": "Subscription",
                "goal": "Improve subscription billing clarity.",
                "requirement_ids": ["REQ-001"],
                "risks": [],
                "success_metrics": [],
            }
        ]
    }


def _versions_by_id() -> dict:
    return {item["version_id"]: item for item in _roadmap()["versions"]}


def _requirements_by_id() -> dict:
    return {
        "REQ-001": {
            "requirement_id": "REQ-001",
            "title": "Clarify subscription billing",
            "description": "Subscription terms should be clear to users.",
            "finding_ids": ["FINDING-001"],
            "success_metrics": [],
        }
    }


def _findings_by_id() -> dict:
    return {
        "FINDING-001": {
            "finding_id": "FINDING-001",
            "title": "Subscription confusion",
            "statement": "Users report unclear subscription terms.",
            "issue_ids": ["ISSUE-001"],
            "review_ids": ["review-001"],
        }
    }


def _issues_by_id() -> dict:
    return {"ISSUE-001": {"issue_id": "ISSUE-001", "topic_ids": ["TOPIC-001"], "review_ids": ["review-001"]}}


def _topics_by_id() -> dict:
    return {"TOPIC-001": {"topic_id": "TOPIC-001", "review_ids": ["review-001"]}}


def _reviews() -> list[dict]:
    return [{"id": "review-001"}]


if __name__ == "__main__":
    unittest.main()
