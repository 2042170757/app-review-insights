import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.prd_generator import (
    build_default_mock_output,
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
                "success_metrics": ["Decrease subscription complaints by 10%."],
            },
            {
                "version_id": "V2",
                "name": "Workout Content",
                "goal": "Improve workout content quality.",
                "requirement_ids": ["REQ-003"],
                "risks": [],
                "success_metrics": ["Decrease content complaints by 10%."],
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


if __name__ == "__main__":
    unittest.main()
