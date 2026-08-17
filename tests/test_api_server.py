import unittest
import time

from fastapi.testclient import TestClient

from app.api.server import create_app
from app.workflow.models import DEFAULT_ANALYSIS_GOAL
from app.workflow.orchestrator import WorkflowOrchestrator
from app.workflow.pipeline import WorkflowStageExecutionResult


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class APIServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = WorkflowOrchestrator(pipeline_runner=_FastRunner())
        self.client = TestClient(create_app(self.orchestrator))

    def test_health(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_post_runs_returns_run_id(self) -> None:
        response = self.client.post(
            "/api/runs",
            json={"app_url": VALID_URL, "analysis_goal": "Goal"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("run_id", response.json())

    def test_post_runs_rejects_invalid_url(self) -> None:
        response = self.client.post(
            "/api/runs",
            json={"app_url": "https://example.com/xxx", "analysis_goal": "Goal"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid App Store URL")

    def test_get_run_returns_full_run_state(self) -> None:
        created = self.client.post("/api/runs", json={"app_url": VALID_URL, "analysis_goal": ""}).json()

        self._wait_for_terminal_run(created["run_id"])
        response = self.client.get(f"/api/runs/{created['run_id']}")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["run_id"], created["run_id"])
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["analysis_goal"], DEFAULT_ANALYSIS_GOAL)
        self.assertEqual(payload["progress"], 100.0)
        self.assertEqual(len(payload["stages"]), 11)
        self.assertFalse(payload["is_mock"])

    def test_get_run_stages(self) -> None:
        created = self.client.post("/api/runs", json={"app_url": VALID_URL, "analysis_goal": "Goal"}).json()

        self._wait_for_terminal_run(created["run_id"])
        response = self.client.get(f"/api/runs/{created['run_id']}/stages")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["stages"]), 11)
        self.assertEqual(payload["stages"][0]["stage"], "scope")

    def test_ui_polling_can_observe_run_state(self) -> None:
        created = self.client.post("/api/runs", json={"app_url": VALID_URL, "analysis_goal": "Goal"}).json()

        response = self.client.get(f"/api/runs/{created['run_id']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json()["status"], {"running", "completed"})

    def test_get_unknown_run_returns_404(self) -> None:
        response = self.client.get("/api/runs/does-not-exist")

        self.assertEqual(response.status_code, 404)

    def _wait_for_terminal_run(self, run_id: str) -> None:
        for _ in range(50):
            payload = self.client.get(f"/api/runs/{run_id}").json()
            if payload["status"] in {"completed", "failed"}:
                return
            time.sleep(0.01)
        self.fail("run did not reach a terminal state")


class _FastRunner:
    def run_stage(self, *, stage: str, context: dict):
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} done",
            artifacts=[f"artifacts/{stage}.json"],
            summary={"run_id": context["run_id"]},
            elapsed_seconds=0.001,
        )


if __name__ == "__main__":
    unittest.main()
