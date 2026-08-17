import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.demo import DEMO_CACHE_ROOT_ENV
from app.api.server import create_app
from app.workflow.orchestrator import WorkflowOrchestrator
from app.workflow.pipeline import WorkflowStageExecutionError, WorkflowStageExecutionResult
from app.workflow.stages import ERROR_PROVIDER


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class DemoAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_cache_root = os.environ.get(DEMO_CACHE_ROOT_ENV)

    def tearDown(self) -> None:
        if self.previous_cache_root is None:
            os.environ.pop(DEMO_CACHE_ROOT_ENV, None)
        else:
            os.environ[DEMO_CACHE_ROOT_ENV] = self.previous_cache_root

    def test_demo_run_returns_completed_run_state(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=_ForbiddenRunner())
        client = TestClient(create_app(orchestrator))

        response = client.get("/api/demo/run")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["is_demo"])
        self.assertEqual(payload["data_source"], "cached_demo")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["progress"], 100.0)
        self.assertEqual(payload["runtime_validation_status"], "pass")
        self.assertEqual(payload["submission_validation_status"], "pending")
        self.assertEqual(len(payload["stages"]), 11)
        self.assertFalse(orchestrator._runner.called)

    def test_demo_result_endpoints_use_existing_dashboard_payloads(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=_ForbiddenRunner())
        client = TestClient(create_app(orchestrator))
        run = client.get("/api/demo/run").json()
        run_id = run["run_id"]

        reviews = client.get(f"/api/runs/{run_id}/reviews").json()
        topics = client.get(f"/api/runs/{run_id}/topics").json()
        findings = client.get(f"/api/runs/{run_id}/findings").json()
        requirements = client.get(f"/api/runs/{run_id}/requirements").json()
        roadmap = client.get(f"/api/runs/{run_id}/roadmap").json()
        prd = client.get(f"/api/runs/{run_id}/prd").json()
        test_cases = client.get(f"/api/runs/{run_id}/test-cases").json()
        traceability = client.get(f"/api/runs/{run_id}/traceability").json()
        metadata = client.get(f"/api/runs/{run_id}/metadata").json()

        self.assertEqual(len(reviews["reviews"]), 50)
        self.assertGreater(len(topics["topics"]), 0)
        self.assertGreater(len(findings["findings"]), 0)
        self.assertGreater(len(requirements["requirements"]), 0)
        self.assertGreater(len(roadmap["versions"]), 0)
        self.assertGreater(len(prd["prds"]), 0)
        self.assertGreater(len(test_cases["test_cases"]), 0)
        self.assertEqual(traceability["validation"]["runtime_validation_status"], "pass")
        self.assertEqual(metadata["data"]["display_source"], "Cached / Demo Data")
        self.assertEqual(metadata["data"]["cached_label"], "Cached / Demo Data")
        self.assertEqual(metadata["data"]["artifact_source"], "Built-in Demo Cache")
        self.assertTrue(metadata["data"]["is_demo"])
        self.assertNotIn("API_KEY", json.dumps(metadata))

    def test_demo_metadata_endpoint_validates_cache(self) -> None:
        client = TestClient(create_app(WorkflowOrchestrator(pipeline_runner=_ForbiddenRunner())))

        response = client.get("/api/demo/metadata")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "PASS")
        self.assertEqual(response.json()["metadata"]["mode"], "cached_demo")

    def test_missing_demo_cache_returns_explicit_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            os.environ[DEMO_CACHE_ROOT_ENV] = str(Path(tempdir) / "missing")
            client = TestClient(create_app(WorkflowOrchestrator(pipeline_runner=_ForbiddenRunner())))

            response = client.get("/api/demo/run")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["type"], "Invalid Demo Cache")

    def test_live_failure_does_not_fallback_to_demo(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=_FailingLiveRunner())
        client = TestClient(create_app(orchestrator))

        created = client.post("/api/runs", json={"app_url": VALID_URL, "analysis_goal": "Goal"})
        run_id = created.json()["run_id"]
        _wait_for_terminal(client, run_id)
        run = client.get(f"/api/runs/{run_id}").json()
        metadata = client.get(f"/api/runs/{run_id}/metadata").json()

        self.assertEqual(run["status"], "failed")
        self.assertFalse(run["is_demo"])
        self.assertNotEqual(metadata["data"].get("display_source"), "Cached / Demo Data")

    def test_demo_and_live_run_ids_are_isolated(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=_FastRunner())
        client = TestClient(create_app(orchestrator))

        demo = client.get("/api/demo/run").json()
        live = client.post("/api/runs", json={"app_url": VALID_URL, "analysis_goal": "Goal"}).json()
        _wait_for_terminal(client, live["run_id"])
        live_payload = client.get(f"/api/runs/{live['run_id']}").json()
        demo_payload = client.get(f"/api/runs/{demo['run_id']}").json()

        self.assertNotEqual(demo["run_id"], live["run_id"])
        self.assertTrue(demo_payload["is_demo"])
        self.assertFalse(live_payload["is_demo"])
        self.assertEqual(demo_payload["data_source"], "cached_demo")
        self.assertEqual(live_payload["data_source"], "app_store")

    def test_offline_demo_does_not_require_provider_environment(self) -> None:
        previous_apify = os.environ.pop("APIFY_API_TOKEN", None)
        previous_deepseek = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            client = TestClient(create_app(WorkflowOrchestrator(pipeline_runner=_ForbiddenRunner())))

            response = client.get("/api/demo/run")
        finally:
            if previous_apify is not None:
                os.environ["APIFY_API_TOKEN"] = previous_apify
            if previous_deepseek is not None:
                os.environ["DEEPSEEK_API_KEY"] = previous_deepseek

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")


class _ForbiddenRunner:
    def __init__(self) -> None:
        self.called = False

    def run_stage(self, *, stage: str, context: dict):
        self.called = True
        raise AssertionError("Demo mode must not call the live pipeline runner")


class _FailingLiveRunner:
    def run_stage(self, *, stage: str, context: dict):
        raise WorkflowStageExecutionError(
            stage=stage,
            error_type=ERROR_PROVIDER,
            message="Live provider unavailable",
        )


class _FastRunner:
    def run_stage(self, *, stage: str, context: dict):
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} complete",
            artifacts=[],
            summary={},
            elapsed_seconds=0.001,
        )


def _wait_for_terminal(client: TestClient, run_id: str) -> None:
    for _ in range(100):
        payload = client.get(f"/api/runs/{run_id}").json()
        if payload["status"] in {"completed", "failed"}:
            return
        time.sleep(0.01)
    raise AssertionError("run did not reach terminal state")


if __name__ == "__main__":
    unittest.main()
