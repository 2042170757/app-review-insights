import unittest

from app.workflow.orchestrator import WorkflowOrchestrator
from app.workflow.pipeline import WorkflowStageExecutionError, WorkflowStageExecutionResult
from app.workflow.stages import (
    ERROR_AUTH,
    ERROR_DATA,
    ERROR_PROVIDER,
    ERROR_TIMEOUT,
    RUN_FAILED,
    STAGE_COLLECTION,
    STAGE_PRD,
    STAGE_PROCESSING,
    STAGE_REQUIREMENT_GENERATION,
    STAGE_SCOPE,
    STAGE_TEST_CASES,
    STAGE_TOPIC_DISCOVERY,
    STATUS_FAILED,
    STATUS_SKIPPED,
)


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class WorkflowFailureTests(unittest.TestCase):
    def test_scope_failure_skips_following_stages(self) -> None:
        result = _run_with_failure(STAGE_SCOPE, ERROR_DATA)

        self.assertEqual(result.status, RUN_FAILED)
        self.assertEqual(result.stages[0].status, STATUS_FAILED)
        self.assertTrue(all(stage.status == STATUS_SKIPPED for stage in result.stages[1:]))

    def test_collection_failure_skips_following_stages(self) -> None:
        result = _run_with_failure(STAGE_COLLECTION, ERROR_PROVIDER)

        self.assertEqual(result.stages[1].status, STATUS_FAILED)
        self.assertTrue(all(stage.status == STATUS_SKIPPED for stage in result.stages[2:]))

    def test_processing_failure_skips_following_stages(self) -> None:
        result = _run_with_failure(STAGE_PROCESSING, ERROR_DATA)

        self.assertEqual(result.stages[2].status, STATUS_FAILED)
        self.assertTrue(all(stage.status == STATUS_SKIPPED for stage in result.stages[3:]))

    def test_topic_timeout_skips_downstream_semantic_stages(self) -> None:
        result = _run_with_failure(STAGE_TOPIC_DISCOVERY, ERROR_TIMEOUT)

        self.assertEqual(result.stages[3].status, STATUS_FAILED)
        self.assertEqual(result.errors[0].type, ERROR_TIMEOUT)
        self.assertTrue(all(stage.status == STATUS_SKIPPED for stage in result.stages[4:]))

    def test_missing_api_key_fails_at_topic_discovery(self) -> None:
        result = _run_with_failure(STAGE_TOPIC_DISCOVERY, ERROR_AUTH, "Missing API Key: DEEPSEEK_API_KEY is not configured.")

        self.assertEqual(result.status, RUN_FAILED)
        self.assertEqual(result.errors[0].type, ERROR_AUTH)
        self.assertIn("Missing API Key", result.errors[0].message)

    def test_requirement_failure_skips_later_stages(self) -> None:
        result = _run_with_failure(STAGE_REQUIREMENT_GENERATION, ERROR_PROVIDER)

        self.assertEqual(result.stages[6].status, STATUS_FAILED)
        self.assertTrue(all(stage.status == STATUS_SKIPPED for stage in result.stages[7:]))

    def test_prd_failure_skips_later_stages(self) -> None:
        result = _run_with_failure(STAGE_PRD, ERROR_PROVIDER)

        self.assertEqual(result.stages[8].status, STATUS_FAILED)
        self.assertTrue(all(stage.status == STATUS_SKIPPED for stage in result.stages[9:]))

    def test_test_case_failure_skips_traceability(self) -> None:
        result = _run_with_failure(STAGE_TEST_CASES, ERROR_PROVIDER)

        self.assertEqual(result.stages[9].status, STATUS_FAILED)
        self.assertEqual(result.stages[10].status, STATUS_SKIPPED)


def _run_with_failure(stage: str, error_type: str, message: str = "stage failed"):
    orchestrator = WorkflowOrchestrator(pipeline_runner=FailingRunner(stage, error_type, message))
    run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")
    return orchestrator.run_pipeline_sync(run.run_id)


class FailingRunner:
    def __init__(self, failed_stage: str, error_type: str, message: str) -> None:
        self.failed_stage = failed_stage
        self.error_type = error_type
        self.message = message

    def run_stage(self, *, stage: str, context: dict):
        if stage == self.failed_stage:
            raise WorkflowStageExecutionError(
                stage=stage,
                error_type=self.error_type,
                message=self.message,
                artifacts=[f"artifacts/{stage}.json"],
                warnings=["warning before failure"],
                summary={"failed_stage": stage},
            )
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} complete",
            artifacts=[f"artifacts/{stage}.json"],
            summary={"stage": stage},
            elapsed_seconds=0.001,
        )


if __name__ == "__main__":
    unittest.main()
