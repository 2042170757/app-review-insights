import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.server import create_app
from app.workflow.artifacts import RUN_ARTIFACT_ROOT_ENV
from app.workflow.orchestrator import WorkflowOrchestrator
from app.workflow.pipeline import WorkflowStageExecutionError, WorkflowStageExecutionResult
from app.workflow.stages import ERROR_VALIDATION, REVISION_APPLIED


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class APIDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_run_root = os.environ.get(RUN_ARTIFACT_ROOT_ENV)
        os.environ[RUN_ARTIFACT_ROOT_ENV] = str(Path(self.tempdir.name) / "run_snapshots")

    def tearDown(self) -> None:
        if self.previous_run_root is None:
            os.environ.pop(RUN_ARTIFACT_ROOT_ENV, None)
        else:
            os.environ[RUN_ARTIFACT_ROOT_ENV] = self.previous_run_root
        self.tempdir.cleanup()

    def test_errors_warnings_revisions_and_metadata_endpoints(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=_DiagnosticsRunner(Path(self.tempdir.name) / "source"))
        client = TestClient(create_app(orchestrator))
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")
        orchestrator.run_pipeline_sync(run.run_id)
        orchestrator.add_revision(
            run.run_id,
            stage="prd",
            reason="Goal Incoherence",
            status=REVISION_APPLIED,
        )

        orchestrator.add_warning(
            run.run_id,
            stage="finding_generation",
            warning_type="evidence_warning",
            message="Evidence sample small",
        )

        warnings = client.get(f"/api/runs/{run.run_id}/warnings").json()
        revisions = client.get(f"/api/runs/{run.run_id}/revisions").json()
        metadata = client.get(f"/api/runs/{run.run_id}/metadata").json()

        self.assertEqual(warnings["warnings"][0]["category"], "Warning")
        self.assertEqual(warnings["warnings"][0]["blocking"], False)
        self.assertIn("timestamp", warnings["warnings"][0])
        self.assertEqual(revisions["revisions"][0]["status"], "applied")
        self.assertEqual(revisions["revisions"][0]["stage"], "prd")
        self.assertIn("timestamp", revisions["revisions"][0])
        self.assertEqual(metadata["data"]["provider"], "apify")
        self.assertEqual(metadata["data"]["territory"], "US")
        self.assertEqual(metadata["data"]["app_id"], "839285684")
        self.assertEqual(metadata["data"]["cached_label"], "Cached for this Run")
        self.assertEqual(metadata["model"]["model_registry"][0]["max_tokens"], 3000)
        self.assertNotIn("API_KEY", json.dumps(metadata))

    def test_prd_failure_propagates_skipped_stages_without_success(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=_FailingPrdRunner())
        client = TestClient(create_app(orchestrator))
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")
        orchestrator.run_pipeline_sync(run.run_id)

        run_payload = client.get(f"/api/runs/{run.run_id}").json()
        errors = client.get(f"/api/runs/{run.run_id}/errors").json()

        stage_status = {stage["stage"]: stage["status"] for stage in run_payload["stages"]}
        self.assertEqual(stage_status["prd"], "failed")
        self.assertEqual(stage_status["test_cases"], "skipped")
        self.assertEqual(stage_status["traceability"], "skipped")
        self.assertEqual(errors["errors"][0]["category"], "Error")
        self.assertEqual(errors["errors"][0]["type"], ERROR_VALIDATION)
        self.assertEqual(errors["errors"][0]["recoverable"], True)
        self.assertTrue(errors["failure_propagation"]["has_failure"])
        self.assertEqual(errors["failure_propagation"]["failed_stage"], "prd")
        self.assertIn("test_cases", errors["failure_propagation"]["skipped_stages"])
        self.assertIn("后续阶段未执行", errors["failure_propagation"]["message"])

    def test_unknown_run_diagnostic_endpoint_returns_404(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=_DiagnosticsRunner(Path(self.tempdir.name) / "source"))
        client = TestClient(create_app(orchestrator))

        response = client.get("/api/runs/not-a-run/errors")

        self.assertEqual(response.status_code, 404)


class _DiagnosticsRunner:
    def __init__(self, source_dir: Path) -> None:
        self.source_dir = source_dir

    def run_stage(self, *, stage: str, context: dict):
        self.source_dir.mkdir(parents=True, exist_ok=True)
        artifacts = _write_stage_artifacts(self.source_dir, stage, context["run_id"])
        warnings = ["Data coverage limited"] if stage == "collection" else []
        summary = {}
        if stage == "collection":
            summary = {
                "provider": "apify",
                "territory": "US",
                "app_id": "839285684",
                "requested_limit": 50,
                "actual_count": 1,
            }
        if stage == "traceability":
            summary = {"runtime_validation_status": "pass", "submission_validation_status": "pending"}
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} done",
            artifacts=[str(path) for path in artifacts],
            warnings=warnings,
            summary=summary,
            elapsed_seconds=0.001,
        )


class _FailingPrdRunner:
    def run_stage(self, *, stage: str, context: dict):
        if stage == "prd":
            raise WorkflowStageExecutionError(
                stage=stage,
                error_type=ERROR_VALIDATION,
                message="Goal Incoherence",
            )
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} done",
            artifacts=[],
            summary={},
            elapsed_seconds=0.001,
        )


def _write_stage_artifacts(source_dir: Path, stage: str, run_id: str) -> list[Path]:
    payloads = {
        "collection": {
            "dataset_metadata.json": {
                "provider": "apify",
                "territory": "US",
                "app_id": "839285684",
                "retrieved_at": "2026-08-17T00:00:00Z",
                "requested_limit": 50,
                "actual_count": 1,
                "limitations": ["Data coverage limited"],
            }
        },
        "traceability": {
            "final_validation_report.json": {
                "runtime_validation_status": "pass",
                "submission_validation_status": "pending",
                "submission_blockers": ["R. UI readiness"],
                "model_registry": [
                    {
                        "task": "Finding Generation",
                        "provider": "deepseek",
                        "model": "deepseek-v4-flash",
                        "configuration": {
                            "thinking": {"type": "disabled"},
                            "max_tokens": 3000,
                            "temperature": 0.2,
                            "stream": False,
                            "timeout_seconds": 60,
                        },
                    }
                ],
            }
        },
    }
    paths: list[Path] = []
    for filename, payload in payloads.get(stage, {}).items():
        path = source_dir / filename
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(path)
    return paths


if __name__ == "__main__":
    unittest.main()
