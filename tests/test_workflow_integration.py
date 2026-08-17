import unittest

from app.workflow.orchestrator import WorkflowOrchestrator
from app.workflow.pipeline import WorkflowStageExecutionResult
from app.workflow.stages import RUN_COMPLETED, STATUS_COMPLETED, WORKFLOW_STAGE_IDS


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class WorkflowIntegrationTests(unittest.TestCase):
    def test_complete_workflow_updates_all_stages_and_artifacts(self) -> None:
        runner = RecordingRunner()
        orchestrator = WorkflowOrchestrator(pipeline_runner=runner)
        run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="Goal")

        result = orchestrator.run_pipeline_sync(run.run_id)

        self.assertEqual(result.status, RUN_COMPLETED)
        self.assertEqual(result.progress, 100.0)
        self.assertEqual(result.current_stage, None)
        self.assertEqual(runner.stages, list(WORKFLOW_STAGE_IDS))
        self.assertTrue(all(stage.status == STATUS_COMPLETED for stage in result.stages))
        self.assertTrue(all(stage.started_at for stage in result.stages))
        self.assertTrue(all(stage.completed_at for stage in result.stages))
        self.assertTrue(all(stage.artifacts for stage in result.stages))
        self.assertEqual(result.stages[0].summary["app_id"], "839285684")
        self.assertIsNotNone(result.total_elapsed_seconds)

    def test_scope_records_non_us_input_and_us_review_decision(self) -> None:
        orchestrator = WorkflowOrchestrator(pipeline_runner=RecordingRunner())
        run = orchestrator.create_run(
            app_url="https://apps.apple.com/cn/app/example/id839285684",
            analysis_goal="Goal",
        )

        result = orchestrator.run_pipeline_sync(run.run_id)

        self.assertEqual(result.stages[0].summary["storefront"], "CN")
        self.assertEqual(result.stages[0].summary["review_territory"], "US")
        self.assertTrue(result.stages[0].warnings)

    def test_constraints_are_stored_and_passed_to_workflow_context(self) -> None:
        runner = RecordingRunner()
        orchestrator = WorkflowOrchestrator(pipeline_runner=runner)
        run = orchestrator.create_run(
            app_url=VALID_URL,
            analysis_goal="Goal",
            constraints={"rating": {"min": 1, "max": 2}},
        )

        result = orchestrator.run_pipeline_sync(run.run_id)

        self.assertEqual(result.constraints, {"rating": {"min": 1, "max": 2}})
        self.assertEqual(result.stages[0].summary["constraints"], {"rating": {"min": 1, "max": 2}})
        self.assertTrue(all(context["constraints"] == {"rating": {"min": 1, "max": 2}} for context in runner.contexts))


class RecordingRunner:
    def __init__(self) -> None:
        self.stages: list[str] = []
        self.contexts: list[dict] = []

    def run_stage(self, *, stage: str, context: dict):
        self.stages.append(stage)
        self.contexts.append(dict(context))
        summary = {"stage": stage}
        if stage == "scope":
            summary = {
                "storefront": context["storefront"],
                "app_id": context["app_id"],
                "analysis_goal": context["analysis_goal"],
                "constraints": context.get("constraints", {}),
                "review_source": "apify",
                "review_territory": "US",
            }
            warnings = (
                ["Input storefront differs from required review territory; collection will use US reviews."]
                if context["storefront"] != "US"
                else []
            )
        else:
            warnings = []
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} complete",
            artifacts=[f"artifacts/{stage}.json"],
            warnings=warnings,
            summary=summary,
            elapsed_seconds=0.001,
        )


if __name__ == "__main__":
    unittest.main()
