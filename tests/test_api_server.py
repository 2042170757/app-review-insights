import unittest

from fastapi.testclient import TestClient

from app.api.server import create_app
from app.workflow.models import DEFAULT_ANALYSIS_GOAL
from app.workflow.orchestrator import WorkflowOrchestrator


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class APIServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = WorkflowOrchestrator()
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

        response = self.client.get(f"/api/runs/{created['run_id']}")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["run_id"], created["run_id"])
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["analysis_goal"], DEFAULT_ANALYSIS_GOAL)
        self.assertEqual(payload["progress"], 0.0)
        self.assertEqual(len(payload["stages"]), 11)
        self.assertTrue(payload["is_mock"])

    def test_get_run_stages(self) -> None:
        created = self.client.post("/api/runs", json={"app_url": VALID_URL, "analysis_goal": "Goal"}).json()

        response = self.client.get(f"/api/runs/{created['run_id']}/stages")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["stages"]), 11)
        self.assertEqual(payload["stages"][0]["stage"], "scope")

    def test_get_unknown_run_returns_404(self) -> None:
        response = self.client.get("/api/runs/does-not-exist")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
