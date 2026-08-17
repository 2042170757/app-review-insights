import unittest

from app.workflow.orchestrator import WorkflowOrchestrator
from app.workflow.pipeline import WorkflowStageExecutionError, WorkflowStageExecutionResult
from app.workflow.stages import (
    ERROR_VALIDATION,
    RUN_COMPLETED,
    RUN_FAILED,
    STAGE_PRD,
    STAGE_TRACEABILITY,
    STATUS_FAILED,
    STATUS_SKIPPED,
    WORKFLOW_STAGE_IDS,
)


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class WorkflowValidationStateTests(unittest.TestCase):
    def test_runtime_pass_submission_pending_does_not_fail_run(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=ValidationRunner())
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")

        result = orchestrator.run_pipeline_sync(run.run_id)

        self.assertEqual(result.status, RUN_COMPLETED)
        self.assertEqual(result.runtime_validation_status, "pass")
        self.assertEqual(result.submission_validation_status, "pending")
        self.assertEqual(result.stages[-1].status, "completed")
        self.assertTrue(result.warnings)

    def test_runtime_traceability_failure_fails_run(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=ValidationRunner(runtime_status="fail"))
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")

        result = orchestrator.run_pipeline_sync(run.run_id)

        self.assertEqual(result.status, RUN_FAILED)
        self.assertEqual(result.current_stage, STAGE_TRACEABILITY)
        self.assertEqual(result.runtime_validation_status, "fail")
        self.assertEqual(result.stages[-1].status, STATUS_FAILED)

    def test_prd_validator_failure_still_skips_downstream(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=PRDFailingRunner())
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")

        result = orchestrator.run_pipeline_sync(run.run_id)

        self.assertEqual(result.status, RUN_FAILED)
        self.assertEqual(result.runtime_validation_status, "fail")
        self.assertEqual(result.stages[8].status, STATUS_FAILED)
        self.assertEqual(result.stages[9].status, STATUS_SKIPPED)
        self.assertEqual(result.stages[10].status, STATUS_SKIPPED)


class ValidationRunner:
    def __init__(self, *, runtime_status: str = "pass") -> None:
        self.runtime_status = runtime_status

    def run_stage(self, *, stage: str, context: dict):
        if stage == STAGE_TRACEABILITY:
            summary = {
                "runtime_validation_status": self.runtime_status,
                "submission_validation_status": "pending",
                "submission_blockers": ["R. UI readiness"],
            }
            if self.runtime_status != "pass":
                raise WorkflowStageExecutionError(
                    stage=stage,
                    error_type=ERROR_VALIDATION,
                    message="runtime validation failed",
                    artifacts=["artifacts/analysis/final_validation_report.json"],
                    summary=summary,
                )
            return WorkflowStageExecutionResult(
                stage=stage,
                message="traceability complete",
                artifacts=["artifacts/analysis/final_validation_report.json"],
                warnings=["Backend analysis pipeline completed, but final submission requirements are not yet complete."],
                summary=summary,
                elapsed_seconds=0.001,
            )
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} complete",
            artifacts=[f"artifacts/{stage}.json"],
            summary={"stage": stage},
            elapsed_seconds=0.001,
        )


class PRDFailingRunner:
    def run_stage(self, *, stage: str, context: dict):
        if stage == STAGE_PRD:
            raise WorkflowStageExecutionError(
                stage=stage,
                error_type=ERROR_VALIDATION,
                message="PRD Validator failed: Goal Incoherence",
                artifacts=["artifacts/analysis/prd_validation.json"],
                summary={"validation": "Goal Incoherence"},
            )
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} complete",
            artifacts=[f"artifacts/{stage}.json"],
            summary={"stage": stage, "order_count": len(WORKFLOW_STAGE_IDS)},
            elapsed_seconds=0.001,
        )


if __name__ == "__main__":
    unittest.main()
