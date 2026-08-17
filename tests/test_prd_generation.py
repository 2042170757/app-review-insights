import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.llm.base import LLMRequest, LLMResponse, ModelRequestError
from app.prd_generator import build_prd_request, build_default_mock_output, create_mock_provider, generate_prds


class PRDGenerationPhase6bTests(unittest.TestCase):
    def test_model_request_error_skips_validation(self) -> None:
        provider = _FailingProvider(ModelRequestError("Model Request Error: failed"))
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
        self.assertEqual(result.generation_status, "Model Request Error")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_analysis_goal_is_passed_to_request(self) -> None:
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
                analysis_goal="分析订阅问题",
                output_dir=Path(temp_dir),
            )

        self.assertEqual(provider.requests[0].analysis_goal, "分析订阅问题")
        self.assertIn("分析订阅问题", provider.requests[0].user_prompt)

    def test_request_requires_open_questions_for_uncertain_parameters(self) -> None:
        request = build_prd_request(
            requirements=_requirements(),
            roadmap=_roadmap(),
            findings=_findings(),
            evidence_report={"evidence_reports": []},
            analysis_goal="goal",
        )
        payload = json.loads(request.user_prompt)

        self.assertEqual(
            payload["validated_versions"][0]["required_open_questions"][0]["requirement_id"],
            "REQ-001",
        )


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
                "success_metrics": ["Decrease subscription complaint rate."],
            }
        ]
    }


def _requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "title": "Provide free access options",
            "description": "Clarify free access for subscription users.",
            "success_metrics": ["Decrease subscription complaint rate."],
        }
    ]


def _findings() -> list[dict]:
    return [{"finding_id": "FINDING-001", "issue_ids": ["ISSUE-001"], "review_ids": ["review-001"]}]


def _issues() -> list[dict]:
    return [{"issue_id": "ISSUE-001", "topic_ids": ["TOPIC-001"], "review_ids": ["review-001"]}]


def _topics() -> list[dict]:
    return [{"topic_id": "TOPIC-001", "review_ids": ["review-001"]}]


def _reviews() -> list[dict]:
    return [{"id": "review-001"}]


class _FailingProvider:
    provider_name = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise self.error


if __name__ == "__main__":
    unittest.main()
