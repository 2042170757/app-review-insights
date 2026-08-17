import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.server import create_app
from app.workflow.artifacts import RUN_ARTIFACT_ROOT_ENV
from app.workflow.orchestrator import WorkflowOrchestrator
from app.workflow.pipeline import WorkflowStageExecutionResult


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class APIResultsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_run_root = os.environ.get(RUN_ARTIFACT_ROOT_ENV)
        os.environ[RUN_ARTIFACT_ROOT_ENV] = str(Path(self.tempdir.name) / "run_snapshots")
        self.source_dir = Path(self.tempdir.name) / "source"
        self.orchestrator = WorkflowOrchestrator(pipeline_runner=_ArtifactRunner(self.source_dir))
        self.client = TestClient(create_app(self.orchestrator))

    def tearDown(self) -> None:
        if self.previous_run_root is None:
            os.environ.pop(RUN_ARTIFACT_ROOT_ENV, None)
        else:
            os.environ[RUN_ARTIFACT_ROOT_ENV] = self.previous_run_root
        self.tempdir.cleanup()

    def test_result_endpoints_return_run_artifact_payloads(self) -> None:
        run = self.orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")
        self.orchestrator.run_pipeline_sync(run.run_id)

        reviews = self.client.get(f"/api/runs/{run.run_id}/reviews").json()
        topics = self.client.get(f"/api/runs/{run.run_id}/topics").json()
        issues = self.client.get(f"/api/runs/{run.run_id}/issues").json()
        findings = self.client.get(f"/api/runs/{run.run_id}/findings").json()
        requirements = self.client.get(f"/api/runs/{run.run_id}/requirements").json()
        roadmap = self.client.get(f"/api/runs/{run.run_id}/roadmap").json()
        prd = self.client.get(f"/api/runs/{run.run_id}/prd").json()
        test_cases = self.client.get(f"/api/runs/{run.run_id}/test-cases").json()
        traceability = self.client.get(f"/api/runs/{run.run_id}/traceability").json()
        validation = self.client.get(f"/api/runs/{run.run_id}/validation").json()

        self.assertTrue(reviews["available"])
        self.assertEqual(reviews["reviews"][0]["id"], f"{run.run_id}-review")
        self.assertEqual(topics["topics"][0]["review_ids"], [f"{run.run_id}-review"])
        self.assertEqual(issues["issues"][0]["issue_type"], "problem")
        self.assertTrue(issues["issues"][0]["eligible_for_finding"])
        self.assertEqual(findings["findings"][0]["issue_ids"], ["ISSUE-001"])
        self.assertEqual(requirements["requirements"][0]["finding_ids"], ["FINDING-001"])
        self.assertEqual(roadmap["versions"][0]["requirement_ids"], ["REQ-001"])
        self.assertEqual(prd["prds"][0]["requirement_ids"], ["REQ-001"])
        self.assertEqual(test_cases["test_cases"][0]["requirement_id"], "REQ-001")
        self.assertEqual(traceability["graph"]["review_to_topics"][f"{run.run_id}-review"], ["TOPIC-001"])
        self.assertEqual(traceability["graph"]["test_case_to_reviews"]["TC-001"], [f"{run.run_id}-review"])
        self.assertEqual(traceability["graph"]["review_to_test_cases"][f"{run.run_id}-review"], ["TC-001"])
        self.assertEqual(validation["runtime_validation_status"], "pass")
        self.assertEqual(validation["submission_validation_status"], "pending")
        self.assertEqual(validation["metadata"]["model_registry"][0]["max_tokens"], 3000)
        self.assertEqual(validation["metadata"]["model_registry"][0]["thinking"], "disabled")

    def test_result_endpoints_are_isolated_by_run_id(self) -> None:
        first = self.orchestrator.create_run(app_url=VALID_URL, analysis_goal="First")
        self.orchestrator.run_pipeline_sync(first.run_id)
        first_payload = self.client.get(f"/api/runs/{first.run_id}/reviews").json()

        second = self.orchestrator.create_run(app_url=VALID_URL, analysis_goal="Second")
        self.orchestrator.run_pipeline_sync(second.run_id)
        second_payload = self.client.get(f"/api/runs/{second.run_id}/reviews").json()
        first_after_second = self.client.get(f"/api/runs/{first.run_id}/reviews").json()

        self.assertEqual(first_payload["reviews"][0]["id"], f"{first.run_id}-review")
        self.assertEqual(first_after_second["reviews"][0]["id"], f"{first.run_id}-review")
        self.assertEqual(second_payload["reviews"][0]["id"], f"{second.run_id}-review")
        self.assertNotEqual(first_after_second["reviews"][0]["id"], second_payload["reviews"][0]["id"])

    def test_missing_artifacts_are_reported_as_unavailable(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=_NoArtifactRunner())
        client = TestClient(create_app(orchestrator))
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")
        orchestrator.run_pipeline_sync(run.run_id)

        response = client.get(f"/api/runs/{run.run_id}/reviews")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])
        self.assertEqual(response.json()["reviews"], [])

    def test_unknown_run_result_endpoint_returns_404(self) -> None:
        response = self.client.get("/api/runs/not-a-run/reviews")

        self.assertEqual(response.status_code, 404)


class _ArtifactRunner:
    def __init__(self, source_dir: Path) -> None:
        self.source_dir = source_dir

    def run_stage(self, *, stage: str, context: dict):
        self.source_dir.mkdir(parents=True, exist_ok=True)
        artifacts = _write_stage_artifacts(self.source_dir, stage, context["run_id"])
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} done",
            artifacts=[str(path) for path in artifacts],
            summary=_summary_for_stage(stage),
            elapsed_seconds=0.001,
        )


class _NoArtifactRunner:
    def run_stage(self, *, stage: str, context: dict):
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} done",
            artifacts=[],
            summary={},
            elapsed_seconds=0.001,
        )


def _write_stage_artifacts(source_dir: Path, stage: str, run_id: str) -> list[Path]:
    stage_payloads = {
        "collection": {
            "normalized_reviews.json": {
                "reviews": [
                    {
                        "id": f"{run_id}-review",
                        "source": "apify",
                        "app_id": "839285684",
                        "territory": "US",
                        "rating": 1,
                        "title": "Raw title",
                        "body": "Raw body",
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ]
            },
            "dataset_metadata.json": {"provider": "apify", "territory": "US", "actual_count": 1},
        },
        "processing": {
            "reviews.json": {
                "reviews": [
                    {
                        "id": f"{run_id}-review",
                        "source": "apify",
                        "app_id": "839285684",
                        "territory": "US",
                        "rating": 1,
                        "raw_title": "Raw title",
                        "raw_body": "Raw body",
                        "clean_title": "Clean title",
                        "clean_body": "Clean body",
                        "language": "en",
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ]
            },
            "statistics.json": {"total": 1, "average_rating": 1.0},
            "processing_report.json": {"input_count": 1, "valid_count": 1, "retained_count": 1},
        },
        "topic_discovery": {
            "topics.json": {
                "topics": [
                    {
                        "topic_id": "TOPIC-001",
                        "name": "Topic",
                        "description": "Topic description",
                        "review_ids": [f"{run_id}-review"],
                        "confidence": 0.8,
                        "uncertainty": "Low",
                    }
                ]
            },
            "topic_validation.json": {"status": "PASS", "errors": []},
            "topic_discovery_raw.json": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
        "issue_consolidation": {
            "issues.json": {
                "issues": [
                    {
                        "issue_id": "ISSUE-001",
                        "name": "Issue",
                        "description": "Issue description",
                        "topic_ids": ["TOPIC-001"],
                        "review_ids": [f"{run_id}-review"],
                        "merge_rationale": "Single topic issue.",
                        "confidence": 0.8,
                        "uncertainty": "Low",
                    }
                ],
                "unmerged_topic_ids": [],
            },
            "issue_validation.json": {"status": "PASS", "errors": []},
            "issue_classification.json": {
                "classifications": [
                    {"issue_id": "ISSUE-001", "issue_type": "problem", "classification_reason": "Problem"}
                ]
            },
            "finding_eligibility.json": {
                "eligibility": [
                    {
                        "issue_id": "ISSUE-001",
                        "issue_type": "problem",
                        "eligible_for_finding": True,
                        "reason": "Problem issues are eligible.",
                    }
                ]
            },
            "issue_consolidation_raw.json": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
        "finding_generation": {
            "findings.json": {
                "findings": [
                    {
                        "finding_id": "FINDING-001",
                        "title": "Finding",
                        "statement": "Finding statement",
                        "issue_ids": ["ISSUE-001"],
                        "review_ids": [f"{run_id}-review"],
                        "support_count": 1,
                        "confidence": 0.8,
                        "uncertainty": "Low",
                    }
                ]
            },
            "finding_validation.json": {"status": "PASS", "errors": []},
            "evidence_report.json": {
                "evidence_reports": [
                    {"finding_id": "FINDING-001", "evidence_strength": "moderate", "conflicting_count": 0}
                ]
            },
            "finding_generation_raw.json": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
        "requirement_generation": {
            "requirements.json": {
                "requirements": [
                    {
                        "requirement_id": "REQ-001",
                        "title": "Requirement",
                        "description": "Requirement description",
                        "finding_ids": ["FINDING-001"],
                        "priority": "P1",
                        "acceptance_criteria": [{"acceptance_criteria_id": "REQ-001-AC-1", "statement": "Criterion"}],
                    }
                ]
            },
            "requirement_validation.json": {"status": "PASS", "errors": []},
            "priority_report.json": {"priority_report": [{"requirement_id": "REQ-001", "final_priority": "P1"}]},
            "requirement_generation_raw.json": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
        "roadmap": {
            "roadmap.json": {
                "versions": [
                    {
                        "version_id": "V1",
                        "name": "Version 1",
                        "goal": "Goal",
                        "requirement_ids": ["REQ-001"],
                    }
                ],
                "roadmap_items": [{"requirement_id": "REQ-001", "version_id": "V1", "priority": "P1"}],
                "deferred": [],
            },
            "roadmap_validation.json": {"status": "PASS", "errors": []},
            "roadmap_generation_raw.json": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
        "prd": {
            "prds.json": {
                "prds": [
                    {
                        "prd_id": "PRD-V1",
                        "version_id": "V1",
                        "title": "PRD",
                        "goal": "Goal",
                        "requirement_ids": ["REQ-001"],
                        "open_questions": ["Decision pending"],
                    }
                ]
            },
            "prd_validation.json": {"status": "PASS", "errors": []},
            "prd_generation_raw.json": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
        "test_cases": {
            "test_cases.json": {
                "test_cases": [
                    {
                        "test_case_id": "TC-001",
                        "requirement_id": "REQ-001",
                        "acceptance_criteria_ids": ["REQ-001-AC-1"],
                        "title": "Test case",
                        "source_review_ids": [f"{run_id}-review"],
                    }
                ]
            },
            "test_case_validation.json": {"status": "PASS", "errors": []},
            "test_coverage.json": {"requirement_coverage": "PASS", "acceptance_criteria_coverage": "PASS"},
            "test_case_generation_raw.json": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        },
        "traceability": {
            "final_validation_report.json": {
                "runtime_validation_status": "pass",
                "submission_validation_status": "pending",
                "submission_blockers": ["UI readiness"],
                "counts": {"reviews": 1, "topics": 1},
                "model_registry": [
                    {
                        "task": "Topic Discovery",
                        "provider": "deepseek",
                        "model": "deepseek-v4-flash",
                        "configuration": {
                            "thinking": {"type": "disabled"},
                            "max_tokens": 3000,
                            "temperature": 0.2,
                            "stream": False,
                            "timeout_seconds": 60,
                            "response_format": {"type": "json_object"},
                        },
                    }
                ],
            }
        },
    }
    paths = []
    for filename, payload in stage_payloads.get(stage, {}).items():
        path = source_dir / filename
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(path)
    return paths


def _summary_for_stage(stage: str) -> dict[str, object]:
    if stage == "traceability":
        return {"runtime_validation_status": "pass", "submission_validation_status": "pending"}
    return {}


if __name__ == "__main__":
    unittest.main()
