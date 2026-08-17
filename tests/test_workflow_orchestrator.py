import unittest

from app.workflow.orchestrator import WorkflowInputError, WorkflowOrchestrator, validate_app_store_url
from app.workflow.stages import (
    ERROR_INPUT,
    REVISION_PROPOSED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_QUEUED,
    RUN_RUNNING,
    STAGE_COLLECTION,
    STAGE_PROCESSING,
    STAGE_SCOPE,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SKIPPED,
)


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class WorkflowOrchestratorTests(unittest.TestCase):
    def test_create_run_queued(self) -> None:
        run = WorkflowOrchestrator().create_run(app_url=VALID_URL, analysis_goal="Goal")

        self.assertEqual(run.status, RUN_QUEUED)
        self.assertEqual(run.progress, 0.0)
        self.assertEqual(run.storefront, "US")
        self.assertEqual(run.app_id, "839285684")

    def test_stage_status_changes_to_running_and_completed(self) -> None:
        orchestrator = WorkflowOrchestrator()
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")

        run = orchestrator.mark_stage_running(run.run_id, STAGE_SCOPE)
        self.assertEqual(run.status, RUN_RUNNING)
        self.assertEqual(run.stages[0].status, STATUS_RUNNING)

        run = orchestrator.mark_stage_completed(run.run_id, STAGE_SCOPE)
        self.assertEqual(run.stages[0].status, STATUS_COMPLETED)
        self.assertEqual(run.current_stage, STAGE_COLLECTION)
        self.assertEqual(run.progress, 9.1)

    def test_all_completed_sets_run_completed(self) -> None:
        orchestrator = WorkflowOrchestrator()
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")

        for stage in list(stage.stage for stage in run.stages):
            run = orchestrator.mark_stage_completed(run.run_id, stage)

        self.assertEqual(run.status, RUN_COMPLETED)
        self.assertEqual(run.progress, 100.0)

    def test_failed_stage_skips_following_pending_stages(self) -> None:
        orchestrator = WorkflowOrchestrator()
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")
        orchestrator.mark_stage_completed(run.run_id, STAGE_SCOPE)

        run = orchestrator.mark_stage_failed(
            run.run_id,
            STAGE_COLLECTION,
            error_type=ERROR_INPUT,
            message="Provider failed",
            recoverable=True,
        )

        self.assertEqual(run.status, RUN_FAILED)
        self.assertEqual(run.stages[1].status, STATUS_FAILED)
        self.assertTrue(all(stage.status == STATUS_SKIPPED for stage in run.stages[2:]))
        self.assertEqual(run.errors[0].type, ERROR_INPUT)

    def test_pending_is_not_completed_without_transition(self) -> None:
        run = WorkflowOrchestrator().create_run(app_url=VALID_URL, analysis_goal="Goal")

        self.assertTrue(all(stage.status == STATUS_PENDING for stage in run.stages))

    def test_error_warning_revision_records(self) -> None:
        orchestrator = WorkflowOrchestrator()
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")

        orchestrator.add_error(run.run_id, stage=STAGE_SCOPE, error_type=ERROR_INPUT, message="Bad input", recoverable=True)
        orchestrator.add_warning(run.run_id, stage=STAGE_PROCESSING, warning_type="data_quality", message="Sparse evidence")
        run = orchestrator.add_revision(
            run.run_id,
            stage=STAGE_SCOPE,
            reason="Scope changed",
            status=REVISION_PROPOSED,
        )

        self.assertEqual(len(run.errors), 1)
        self.assertEqual(len(run.warnings), 1)
        self.assertEqual(len(run.revisions), 1)

    def test_valid_us_app_store_url(self) -> None:
        result = validate_app_store_url(VALID_URL)

        self.assertTrue(result.valid)
        self.assertEqual(result.storefront, "US")
        self.assertEqual(result.app_id, "839285684")

    def test_valid_non_us_app_store_url(self) -> None:
        result = validate_app_store_url("https://apps.apple.com/cn/app/example/id839285684")

        self.assertTrue(result.valid)
        self.assertEqual(result.storefront, "CN")

    def test_invalid_url(self) -> None:
        result = validate_app_store_url("https://example.com/xxx")

        self.assertFalse(result.valid)
        self.assertEqual(result.error, "Invalid App Store URL")

    def test_http_url_is_invalid_for_workflow(self) -> None:
        result = validate_app_store_url("http://apps.apple.com/us/app/example/id123")

        self.assertFalse(result.valid)

    def test_create_run_rejects_invalid_url(self) -> None:
        with self.assertRaises(WorkflowInputError):
            WorkflowOrchestrator().create_run(app_url="https://example.com/xxx", analysis_goal="Goal")


if __name__ == "__main__":
    unittest.main()
