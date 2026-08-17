import os
import tempfile
import unittest
from unittest.mock import patch

from app.workflow.pipeline import (
    BackendPipelineRunner,
    FINDING_STAGE_GOAL,
    PRD_STAGE_GOAL,
    REQUIREMENT_STAGE_GOAL,
    ROADMAP_STAGE_GOAL,
    WorkflowStageExecutionError,
    WorkflowStageExecutionResult,
)
from app.workflow.stages import (
    STAGE_FINDING_GENERATION,
    STAGE_PRD,
    STAGE_REQUIREMENT_GENERATION,
    STAGE_ROADMAP,
    STAGE_TOPIC_DISCOVERY,
    STAGE_TRACEABILITY,
)


class WorkflowPipelineAdapterTests(unittest.TestCase):
    def test_topic_discovery_receives_analysis_goal(self) -> None:
        runner = RecordingPipelineRunner()

        runner._run_stage(stage=STAGE_TOPIC_DISCOVERY, context={"analysis_goal": "用户输入目标"})

        self.assertIn("--goal", runner.commands[0])
        self.assertIn("用户输入目标", runner.commands[0])

    def test_finding_generation_uses_stage_goal(self) -> None:
        runner = RecordingPipelineRunner()

        runner._run_stage(stage=STAGE_FINDING_GENERATION, context={"analysis_goal": "订阅价格分析目标"})

        self.assertIn("--goal", runner.commands[0])
        self.assertIn(FINDING_STAGE_GOAL, runner.commands[0])
        self.assertNotIn("订阅价格分析目标", runner.commands[0])

    def test_requirement_generation_uses_stage_goal(self) -> None:
        runner = RecordingPipelineRunner()

        runner._run_stage(stage=STAGE_REQUIREMENT_GENERATION, context={"analysis_goal": "订阅价格分析目标"})

        self.assertIn("--goal", runner.commands[0])
        self.assertIn(REQUIREMENT_STAGE_GOAL, runner.commands[0])
        self.assertNotIn("订阅价格分析目标", runner.commands[0])

    def test_roadmap_generation_uses_stage_goal(self) -> None:
        runner = RecordingPipelineRunner()

        runner._run_stage(stage=STAGE_ROADMAP, context={"analysis_goal": "订阅价格分析目标"})

        self.assertIn("--goal", runner.commands[0])
        self.assertIn(ROADMAP_STAGE_GOAL, runner.commands[0])
        self.assertNotIn("订阅价格分析目标", runner.commands[0])

    def test_prd_generation_uses_stage_goal(self) -> None:
        runner = RecordingPipelineRunner()

        runner._run_stage(stage=STAGE_PRD, context={"analysis_goal": "订阅价格分析目标"})

        self.assertIn("app.generate_prd", runner.commands[0])
        self.assertIn("--goal", runner.commands[0])
        self.assertIn(PRD_STAGE_GOAL, runner.commands[0])
        self.assertNotIn("订阅价格分析目标", runner.commands[0])

    def test_traceability_writes_structured_report_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                with patch("app.workflow.pipeline.run_final_validation", return_value=FakeFinalValidation("PASS")):
                    result = BackendPipelineRunner()._run_stage(stage=STAGE_TRACEABILITY, context={})
            finally:
                os.chdir(original_cwd)

        self.assertEqual(result.summary["downstream_safety"], "PASS")
        self.assertIn("artifacts\\analysis\\final_validation_report.json", result.artifacts)

    def test_traceability_failure_keeps_report_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                with patch("app.workflow.pipeline.run_final_validation", return_value=FakeFinalValidation("FAIL")):
                    with self.assertRaises(WorkflowStageExecutionError) as raised:
                        BackendPipelineRunner()._run_stage(stage=STAGE_TRACEABILITY, context={})
            finally:
                os.chdir(original_cwd)

        self.assertEqual(raised.exception.summary["downstream_safety"], "FAIL")
        self.assertIn("artifacts\\analysis\\final_validation_report.json", raised.exception.artifacts)


class RecordingPipelineRunner(BackendPipelineRunner):
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def _command_stage(self, *, stage, command, artifacts, summary_loader):
        self.commands.append(command)
        return WorkflowStageExecutionResult(stage=stage, message=f"{stage} complete")


class FakeFinalValidation:
    def __init__(self, downstream_safety: str) -> None:
        self.downstream_safety = downstream_safety
        self.critical_issues = [] if downstream_safety == "PASS" else ["critical issue"]
        self.missing_final_deliverables = []
        self.non_blocking_issues = []

    def to_dict(self):
        return {
            "forward_traceability": "PASS",
            "backward_traceability": "PASS",
            "artifact_consistency": "PASS",
            "evidence_traceability": "PASS",
            "explicit_test_case_review_link": "PASS",
            "statistics_model_separation": "PASS",
            "failure_state_audit": "PASS",
            "uncertainty_conflict_audit": "PASS",
            "ai_deterministic_boundary": "PASS",
            "generalization": "PASS",
            "exam_requirement_coverage": 100.0,
            "downstream_safety": self.downstream_safety,
            "critical_issues": self.critical_issues,
            "missing_final_deliverables": self.missing_final_deliverables,
            "counts": {},
        }


if __name__ == "__main__":
    unittest.main()
