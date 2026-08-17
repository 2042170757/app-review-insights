import unittest

from app.demo import DEMO_ANALYSIS_GOAL, DEMO_APP_URL, REQUIRED_STAGE_ARTIFACTS, create_demo_run_state, load_demo_cache
from app.workflow.orchestrator import WorkflowOrchestrator


class DemoModeTests(unittest.TestCase):
    def test_create_demo_run_state_is_completed_without_pending_stages(self) -> None:
        run = create_demo_run_state(run_id="demo-test", cache=load_demo_cache())

        self.assertEqual(run.run_id, "demo-test")
        self.assertTrue(run.is_demo)
        self.assertEqual(run.app_url, DEMO_APP_URL)
        self.assertEqual(run.analysis_goal, DEMO_ANALYSIS_GOAL)
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.progress, 100.0)
        self.assertTrue(all(stage.status == "completed" for stage in run.stages))
        artifact_stages = {stage.stage: stage.artifacts for stage in run.stages}
        self.assertTrue(all(artifact_stages[stage] for stage in REQUIRED_STAGE_ARTIFACTS))

    def test_orchestrator_registers_demo_run_without_active_pipeline(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=_CountingRunner())

        run = orchestrator.create_demo_run()
        loaded = orchestrator.get_run(run.run_id)

        self.assertEqual(loaded.run_id, run.run_id)
        self.assertTrue(loaded.is_demo)
        self.assertEqual(loaded.data_source, "cached_demo")
        self.assertEqual(orchestrator._runner.calls, 0)


class _CountingRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run_stage(self, *, stage: str, context: dict):
        self.calls += 1
        raise AssertionError("Demo run should not execute stages")


if __name__ == "__main__":
    unittest.main()
