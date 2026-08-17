import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.llm.base import LLMRequest, LLMResponse, ModelTimeoutError
from app.prd_generator import (
    build_default_mock_output,
    build_prd_request,
    create_mock_provider,
    generate_prds,
    save_prd_outputs,
)


class PRDGeneratorTests(unittest.TestCase):
    def test_default_mock_output_creates_prd_per_version(self) -> None:
        payload = json.loads(build_default_mock_output(roadmap=_roadmap(), requirements=_requirements()))

        self.assertEqual(len(payload["prds"]), 2)
        self.assertEqual(payload["prds"][0]["prd_id"], "PRD-V1")
        self.assertEqual(payload["prds"][0]["requirement_ids"], ["REQ-001", "REQ-002"])

    def test_generate_prds_with_mock_provider(self) -> None:
        provider = create_mock_provider(build_default_mock_output(roadmap=_roadmap(), requirements=_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = generate_prds(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                roadmap=_roadmap(),
                roadmap_validation=_pass_validation(),
                findings=_findings(),
                finding_validation=_pass_validation(),
                issues=_issues(),
                topics=_topics(),
                reviews=_reviews(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(result.provider, "mock")
        self.assertEqual(len(result.prds), 2)

    def test_failed_input_validation_skips_generation(self) -> None:
        provider = create_mock_provider(build_default_mock_output(roadmap=_roadmap(), requirements=_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = generate_prds(
                requirements=_requirements(),
                requirement_validation={"status": "Failed", "passed": False},
                roadmap=_roadmap(),
                roadmap_validation=_pass_validation(),
                findings=_findings(),
                finding_validation=_pass_validation(),
                issues=_issues(),
                topics=_topics(),
                reviews=_reviews(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Input Validation Failed")
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(provider.requests, [])

    def test_timeout_skips_validation(self) -> None:
        provider = _FailingProvider(ModelTimeoutError("Timeout"))
        with TemporaryDirectory() as temp_dir:
            result = generate_prds(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                roadmap=_roadmap(),
                roadmap_validation=_pass_validation(),
                findings=_findings(),
                finding_validation=_pass_validation(),
                issues=_issues(),
                topics=_topics(),
                reviews=_reviews(),
                provider=provider,
                output_dir=Path(temp_dir),
                is_mock=False,
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Timeout")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_analysis_goal_passed_to_provider(self) -> None:
        provider = create_mock_provider(build_default_mock_output(roadmap=_roadmap(), requirements=_requirements()))
        with TemporaryDirectory() as temp_dir:
            generate_prds(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                roadmap=_roadmap(),
                roadmap_validation=_pass_validation(),
                findings=_findings(),
                finding_validation=_pass_validation(),
                issues=_issues(),
                topics=_topics(),
                reviews=_reviews(),
                provider=provider,
                analysis_goal="custom PRD goal",
                output_dir=Path(temp_dir),
            )

        self.assertEqual(provider.requests[0].analysis_goal, "custom PRD goal")
        self.assertIn("custom PRD goal", provider.requests[0].user_prompt)

    def test_build_request_contains_versions_requirements_and_evidence(self) -> None:
        request = build_prd_request(
            requirements=_requirements(),
            roadmap=_roadmap(),
            findings=_findings(),
            evidence_report=_evidence_report(),
            analysis_goal="goal",
        )
        payload = json.loads(request.user_prompt)

        self.assertEqual(payload["analysis_goal"], "goal")
        self.assertEqual(payload["validated_versions"][0]["version_id"], "V1")
        self.assertEqual(payload["validated_versions"][0]["requirements"][0]["requirement_id"], "REQ-001")
        self.assertEqual(payload["validated_versions"][0]["required_open_questions"][0]["requirement_id"], "REQ-001")
        self.assertEqual(
            payload["validated_versions"][0]["requirements"][0]["findings"][0]["evidence_report"]["finding_id"],
            "FINDING-001",
        )
        self.assertIn("success_metric_rule", payload)
        self.assertIn("success_metrics: []", payload["success_metric_rule"])
        self.assertIn("metric definition", payload["open_question_guidance"]["all_prds"])

    def test_positive_requirement_rule_prefers_empty_metrics_when_unsupported(self) -> None:
        request = build_prd_request(
            requirements=[{"requirement_id": "REQ-001", "requirement_type": "positive_feedback", "finding_ids": ["FINDING-001"]}],
            roadmap={
                "versions": [
                    {
                        "version_id": "V1",
                        "name": "Preserve strengths",
                        "goal": "Preserve valued workout strengths.",
                        "requirement_ids": ["REQ-001"],
                        "rationale": "Positive evidence.",
                        "risks": [],
                        "success_metrics": [],
                    }
                ]
            },
            findings=[{"finding_id": "FINDING-001", "finding_type": "positive_feedback", "issue_ids": ["ISSUE-001"], "review_ids": ["review-001"]}],
            evidence_report=_evidence_report(),
            analysis_goal="positive goal",
        )
        payload = json.loads(request.user_prompt)

        self.assertIn("positive_feedback Requirements", payload["requirement_type_rule"])
        self.assertIn("success_metrics as []", payload["requirement_type_rule"])
        self.assertIn("remains high", request.system_prompt)

    def test_default_mock_output_allows_empty_metrics_with_open_question(self) -> None:
        roadmap = _roadmap()
        roadmap["versions"][0]["success_metrics"] = []

        payload = json.loads(build_default_mock_output(roadmap=roadmap, requirements=_requirements()))

        self.assertEqual(payload["prds"][0]["success_metrics"], [])
        self.assertTrue(any("success metric" in question for question in payload["prds"][0]["open_questions"]))

    def test_invalid_json_marks_generation_failed(self) -> None:
        provider = create_mock_provider("{not json")
        with TemporaryDirectory() as temp_dir:
            result = generate_prds(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                roadmap=_roadmap(),
                roadmap_validation=_pass_validation(),
                findings=_findings(),
                finding_validation=_pass_validation(),
                issues=_issues(),
                topics=_topics(),
                reviews=_reviews(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Invalid JSON")

    def test_schema_validation_marks_generation_failed(self) -> None:
        provider = create_mock_provider(json.dumps({"prds": [{"prd_id": "PRD-V1"}]}))
        with TemporaryDirectory() as temp_dir:
            result = generate_prds(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                roadmap=_roadmap(),
                roadmap_validation=_pass_validation(),
                findings=_findings(),
                finding_validation=_pass_validation(),
                issues=_issues(),
                topics=_topics(),
                reviews=_reviews(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Schema Validation Failed")

    def test_save_outputs_marks_mock(self) -> None:
        provider = create_mock_provider(build_default_mock_output(roadmap=_roadmap(), requirements=_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = generate_prds(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                roadmap=_roadmap(),
                roadmap_validation=_pass_validation(),
                findings=_findings(),
                finding_validation=_pass_validation(),
                issues=_issues(),
                topics=_topics(),
                reviews=_reviews(),
                provider=provider,
                output_dir=Path(temp_dir),
            )
            paths = save_prd_outputs(result, output_dir=Path(temp_dir))
            raw = json.loads(paths["raw"].read_text(encoding="utf-8"))
            prds = json.loads(paths["prds"].read_text(encoding="utf-8"))

        self.assertTrue(raw["is_mock"])
        self.assertEqual(raw["provider"], "mock")
        self.assertEqual(len(prds["prds"]), 2)


def _pass_validation() -> dict:
    return {"status": "Success", "passed": True}


def _roadmap() -> dict:
    return {
        "versions": [
            {
                "version_id": "V1",
                "name": "Subscription and Billing",
                "goal": "Improve subscription billing clarity.",
                "requirement_ids": ["REQ-001", "REQ-002"],
                "risks": [],
                "success_metrics": ["Decrease subscription complaint rate."],
            },
            {
                "version_id": "V2",
                "name": "Workout Content",
                "goal": "Improve workout content quality.",
                "requirement_ids": ["REQ-003"],
                "risks": [],
                "success_metrics": ["Decrease content complaint rate."],
            },
        ],
        "roadmap_items": [],
    }


def _requirements() -> list[dict]:
    return [
        {"requirement_id": "REQ-001", "finding_ids": ["FINDING-001"]},
        {"requirement_id": "REQ-002", "finding_ids": ["FINDING-001"]},
        {"requirement_id": "REQ-003", "finding_ids": ["FINDING-002"]},
    ]


def _findings() -> list[dict]:
    return [
        {"finding_id": "FINDING-001", "issue_ids": ["ISSUE-001"], "review_ids": ["review-001"]},
        {"finding_id": "FINDING-002", "issue_ids": ["ISSUE-002"], "review_ids": ["review-002"]},
    ]


def _evidence_report() -> dict:
    return {
        "evidence_reports": [
            {"finding_id": "FINDING-001", "evidence_strength": "High"},
            {"finding_id": "FINDING-002", "evidence_strength": "Medium"},
        ]
    }


def _issues() -> list[dict]:
    return [
        {"issue_id": "ISSUE-001", "topic_ids": ["TOPIC-001"], "review_ids": ["review-001"]},
        {"issue_id": "ISSUE-002", "topic_ids": ["TOPIC-002"], "review_ids": ["review-002"]},
    ]


def _topics() -> list[dict]:
    return [
        {"topic_id": "TOPIC-001", "review_ids": ["review-001"]},
        {"topic_id": "TOPIC-002", "review_ids": ["review-002"]},
    ]


def _reviews() -> list[dict]:
    return [{"id": "review-001"}, {"id": "review-002"}]


class _FailingProvider:
    provider_name = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise self.error


if __name__ == "__main__":
    unittest.main()
