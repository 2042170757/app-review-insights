import threading
import time
import unittest

from fastapi.testclient import TestClient

from app.api.server import create_app
from app.workflow.orchestrator import WorkflowActiveRunError, WorkflowOrchestrator
from app.workflow.pipeline import WorkflowStageExecutionResult


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class WorkflowRunIsolationTests(unittest.TestCase):
    def test_only_one_active_run_allowed_in_orchestrator(self) -> None:
        runner = BlockingRunner()
        orchestrator = WorkflowOrchestrator(pipeline_runner=runner)
        first = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")
        second = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")

        orchestrator.start_run_async(first.run_id)
        runner.wait_until_started()
        with self.assertRaises(WorkflowActiveRunError):
            orchestrator.start_run_async(second.run_id)
        runner.release()
        _wait_for_status(orchestrator, first.run_id, "completed")

    def test_api_returns_409_when_run_is_active(self) -> None:
        runner = BlockingRunner()
        orchestrator = WorkflowOrchestrator(pipeline_runner=runner)
        client = TestClient(create_app(orchestrator))

        first = client.post("/api/runs", json={"app_url": VALID_URL, "analysis_goal": "Goal"})
        runner.wait_until_started()
        second = client.post("/api/runs", json={"app_url": VALID_URL, "analysis_goal": "Goal"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"], "已有分析任务正在运行")
        runner.release()
        _wait_for_status(orchestrator, first.json()["run_id"], "completed")


class BlockingRunner:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release_event = threading.Event()

    def run_stage(self, *, stage: str, context: dict):
        if stage == "scope":
            self.started.set()
            self.release_event.wait(timeout=5)
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} complete",
            artifacts=[f"artifacts/{stage}.json"],
            summary={"stage": stage},
            elapsed_seconds=0.001,
        )

    def wait_until_started(self) -> None:
        if not self.started.wait(timeout=2):
            raise AssertionError("runner did not start")

    def release(self) -> None:
        self.release_event.set()


def _wait_for_status(orchestrator: WorkflowOrchestrator, run_id: str, status: str) -> None:
    for _ in range(100):
        if orchestrator.get_run(run_id).status == status:
            return
        time.sleep(0.01)
    raise AssertionError(f"run did not reach {status}")


if __name__ == "__main__":
    unittest.main()
