import unittest

from app.workflow.pipeline import (
    FINDING_STAGE_GOAL,
    MIXED_FINDING_STAGE_GOAL,
    MIXED_REQUIREMENT_STAGE_GOAL,
    POSITIVE_FINDING_STAGE_GOAL,
    POSITIVE_REQUIREMENT_STAGE_GOAL,
    REQUIREMENT_STAGE_GOAL,
    BackendPipelineRunner,
    WorkflowStageExecutionResult,
)
from app.workflow.stages import (
    STAGE_FINDING_GENERATION,
    STAGE_ISSUE_CONSOLIDATION,
    STAGE_REQUIREMENT_GENERATION,
)


class PositiveFeedbackPipelineTests(unittest.TestCase):
    def test_problem_focus_preserves_existing_stage_goals(self) -> None:
        runner = RecordingPipelineRunner()

        runner._run_stage(stage=STAGE_FINDING_GENERATION, context={"analysis_focus": "problem_analysis"})
        runner._run_stage(stage=STAGE_REQUIREMENT_GENERATION, context={"analysis_focus": "problem_analysis"})

        self.assertIn(FINDING_STAGE_GOAL, runner.commands[0])
        self.assertIn(REQUIREMENT_STAGE_GOAL, runner.commands[1])
        self.assertIn("problem_analysis", runner.commands[0])
        self.assertIn("problem_analysis", runner.commands[1])

    def test_positive_focus_uses_positive_stage_goals(self) -> None:
        runner = RecordingPipelineRunner()

        runner._run_stage(stage=STAGE_FINDING_GENERATION, context={"analysis_focus": "positive_feedback_analysis"})
        runner._run_stage(stage=STAGE_REQUIREMENT_GENERATION, context={"analysis_focus": "positive_feedback_analysis"})

        self.assertIn(POSITIVE_FINDING_STAGE_GOAL, runner.commands[0])
        self.assertIn(POSITIVE_REQUIREMENT_STAGE_GOAL, runner.commands[1])
        self.assertIn("positive_feedback_analysis", runner.commands[0])
        self.assertIn("positive_feedback_analysis", runner.commands[1])

    def test_mixed_focus_uses_mixed_stage_goals(self) -> None:
        runner = RecordingPipelineRunner()

        runner._run_stage(stage=STAGE_FINDING_GENERATION, context={"analysis_focus": "mixed_analysis"})
        runner._run_stage(stage=STAGE_REQUIREMENT_GENERATION, context={"analysis_focus": "mixed_analysis"})

        self.assertIn(MIXED_FINDING_STAGE_GOAL, runner.commands[0])
        self.assertIn(MIXED_REQUIREMENT_STAGE_GOAL, runner.commands[1])

    def test_issue_consolidation_and_classification_receive_focus(self) -> None:
        runner = RecordingPipelineRunner()

        runner._run_stage(
            stage=STAGE_ISSUE_CONSOLIDATION,
            context={"analysis_goal": "goal", "analysis_focus": "positive_feedback_analysis"},
        )

        self.assertIn("app.consolidate_issues", runner.commands[0])
        self.assertIn("--analysis-focus", runner.commands[0])
        self.assertIn("positive_feedback_analysis", runner.commands[0])
        self.assertIn("app.classify_issues", runner.commands[1])
        self.assertIn("positive_feedback_analysis", runner.commands[1])


class RecordingPipelineRunner(BackendPipelineRunner):
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def _command_stage(self, *, stage, command, artifacts, summary_loader):
        self.commands.append(command)
        return WorkflowStageExecutionResult(stage=stage, message=f"{stage} complete")


if __name__ == "__main__":
    unittest.main()
