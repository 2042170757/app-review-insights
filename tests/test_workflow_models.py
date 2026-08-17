import unittest

from app.workflow.models import (
    DEFAULT_ANALYSIS_GOAL,
    WorkflowError,
    WorkflowRevision,
    WorkflowWarning,
    calculate_progress,
    initialize_stage_states,
    new_run_state,
    normalize_analysis_goal,
)
from app.workflow.stages import (
    ERROR_AUTH,
    REVISION_APPLIED,
    RUN_QUEUED,
    STATUS_COMPLETED,
    STATUS_PENDING,
    WORKFLOW_STAGES,
)


class WorkflowModelsTests(unittest.TestCase):
    def test_run_state_creation(self) -> None:
        run = new_run_state(
            run_id="run-1",
            app_url="https://apps.apple.com/us/app/example/id123",
            analysis_goal="Goal",
            storefront="US",
            app_id="123",
        )

        self.assertEqual(run.run_id, "run-1")
        self.assertEqual(run.status, RUN_QUEUED)
        self.assertIsNone(run.current_stage)
        self.assertEqual(run.progress, 0.0)
        self.assertEqual(run.app_id, "123")
        self.assertEqual(run.analysis_focus, "problem_analysis")
        self.assertTrue(run.is_mock)

    def test_run_state_normalizes_analysis_focus(self) -> None:
        run = new_run_state(
            run_id="run-1",
            app_url="https://apps.apple.com/us/app/example/id123",
            analysis_goal="Goal",
            analysis_focus="positive_feedback",
            storefront="US",
            app_id="123",
        )

        self.assertEqual(run.analysis_focus, "positive_feedback_analysis")

    def test_stage_initialization(self) -> None:
        stages = initialize_stage_states()

        self.assertEqual(len(stages), 11)
        self.assertEqual(stages[0].stage, WORKFLOW_STAGES[0].stage)
        self.assertTrue(all(stage.status == STATUS_PENDING for stage in stages))

    def test_progress_calculation(self) -> None:
        stages = initialize_stage_states()
        for stage in stages[:5]:
            stage.status = STATUS_COMPLETED

        self.assertEqual(calculate_progress(stages), 45.5)

    def test_progress_is_100_when_all_completed(self) -> None:
        stages = initialize_stage_states()
        for stage in stages:
            stage.status = STATUS_COMPLETED

        self.assertEqual(calculate_progress(stages), 100.0)

    def test_empty_analysis_goal_uses_default(self) -> None:
        self.assertEqual(normalize_analysis_goal("  "), DEFAULT_ANALYSIS_GOAL)
        self.assertEqual(normalize_analysis_goal(None), DEFAULT_ANALYSIS_GOAL)

    def test_error_warning_revision_models(self) -> None:
        error = WorkflowError(stage="scope", type=ERROR_AUTH, message="DEEPSEEK_API_KEY secret", recoverable=False)
        warning = WorkflowWarning(stage="scope", type="coverage", message="Potential gap")
        revision = WorkflowRevision(
            revision_id="rev-1",
            stage="scope",
            reason="Adjust scope",
            status=REVISION_APPLIED,
        )

        self.assertEqual(error.type, ERROR_AUTH)
        self.assertIn("<redacted>", error.message)
        self.assertEqual(warning.to_dict()["message"], "Potential gap")
        self.assertEqual(revision.status, REVISION_APPLIED)


if __name__ == "__main__":
    unittest.main()
