import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.llm.base import LLMProvider, LLMRequest, LLMResponse
from app.prd_generator import build_prd_request, generate_prds
from app.workflow.orchestrator import WorkflowOrchestrator
from app.workflow.pipeline import WorkflowStageExecutionResult
from app.workflow.stages import STAGE_PRD


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class PRDMetricWorkflowConsistencyTests(unittest.TestCase):
    def test_generate_prds_uses_same_prompt_context_as_prd_only_request(self) -> None:
        requirements = _requirements()
        roadmap = _roadmap()
        findings = _findings()
        evidence_report = _evidence_report()
        provider = _RecordingProvider(_valid_prd_output())

        with TemporaryDirectory() as temp_dir:
            result = generate_prds(
                requirements=requirements,
                requirement_validation=_pass_validation(),
                roadmap=roadmap,
                roadmap_validation=_pass_validation(),
                findings=findings,
                finding_validation=_pass_validation(),
                issues=_issues(),
                topics=_topics(),
                reviews=_reviews(),
                evidence_report=evidence_report,
                provider=provider,
                analysis_goal="workflow PRD stage goal",
                output_dir=Path(temp_dir),
            )

        direct_request = build_prd_request(
            requirements=requirements,
            roadmap=roadmap,
            findings=findings,
            evidence_report=evidence_report,
            analysis_goal="workflow PRD stage goal",
        )
        self.assertTrue(result.validation.passed)
        self.assertEqual(provider.requests[0].system_prompt, direct_request.system_prompt)
        self.assertEqual(json.loads(provider.requests[0].user_prompt), json.loads(direct_request.user_prompt))

    def test_full_workflow_prd_context_keeps_analysis_goal_separate_from_version_goal(self) -> None:
        request = build_prd_request(
            requirements=_requirements(),
            roadmap=_roadmap(),
            findings=_findings(),
            evidence_report=_evidence_report(),
            analysis_goal="分析低评分用户对订阅和价格的主要问题",
        )
        payload = json.loads(request.user_prompt)

        self.assertEqual(payload["analysis_goal"], "分析低评分用户对订阅和价格的主要问题")
        self.assertEqual(payload["validated_versions"][0]["required_prd_goal"], "Improve workout content quality.")
        self.assertEqual(payload["validated_versions"][0]["requirements"][0]["requirement_id"], "REQ-004")
        self.assertIn("score", payload["success_metric_rule"])

    def test_current_run_artifact_snapshot_prevents_stale_prd_artifact_reads(self) -> None:
        with TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            original_root = os.environ.get("WORKFLOW_RUN_ARTIFACT_ROOT")
            os.chdir(temp_dir)
            os.environ["WORKFLOW_RUN_ARTIFACT_ROOT"] = str(Path(temp_dir) / "run_artifacts")
            try:
                canonical = Path("artifacts/analysis/prds.json")
                runner = _PRDArtifactRunner(canonical)
                orchestrator = WorkflowOrchestrator(pipeline_runner=runner)

                first = orchestrator.create_run(app_url=VALID_URL, analysis_goal="first")
                first_result = orchestrator.run_pipeline_sync(first.run_id)
                second = orchestrator.create_run(app_url=VALID_URL, analysis_goal="second")
                second_result = orchestrator.run_pipeline_sync(second.run_id)

                first_prd_artifact = _stage_artifact(first_result, STAGE_PRD, "prds.json")
                second_prd_artifact = _stage_artifact(second_result, STAGE_PRD, "prds.json")
                first_payload = json.loads(Path(first_prd_artifact).read_text(encoding="utf-8"))
                second_payload = json.loads(Path(second_prd_artifact).read_text(encoding="utf-8"))
            finally:
                os.chdir(original_cwd)
                if original_root is None:
                    os.environ.pop("WORKFLOW_RUN_ARTIFACT_ROOT", None)
                else:
                    os.environ["WORKFLOW_RUN_ARTIFACT_ROOT"] = original_root

        self.assertNotEqual(first_prd_artifact, second_prd_artifact)
        self.assertEqual(first_payload["run_id"], first_result.run_id)
        self.assertEqual(second_payload["run_id"], second_result.run_id)

    def test_stale_artifact_detection_uses_run_specific_snapshot_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            original_root = os.environ.get("WORKFLOW_RUN_ARTIFACT_ROOT")
            os.chdir(temp_dir)
            os.environ["WORKFLOW_RUN_ARTIFACT_ROOT"] = str(Path(temp_dir) / "run_artifacts")
            try:
                canonical = Path("artifacts/analysis/prds.json")
                runner = _PRDArtifactRunner(canonical)
                orchestrator = WorkflowOrchestrator(pipeline_runner=runner)
                run = orchestrator.create_run(app_url=VALID_URL, analysis_goal="goal")
                result = orchestrator.run_pipeline_sync(run.run_id)
                prd_artifact = _stage_artifact(result, STAGE_PRD, "prds.json")
            finally:
                os.chdir(original_cwd)
                if original_root is None:
                    os.environ.pop("WORKFLOW_RUN_ARTIFACT_ROOT", None)
                else:
                    os.environ["WORKFLOW_RUN_ARTIFACT_ROOT"] = original_root

        self.assertIn(run.run_id, prd_artifact)
        self.assertNotEqual(Path(prd_artifact).as_posix(), "artifacts/analysis/prds.json")


class _RecordingProvider(LLMProvider):
    provider_name = "recording"
    model = "recording-prd-model"

    def __init__(self, raw_text: str) -> None:
        self.raw_text = raw_text
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(raw_text=self.raw_text, provider=self.provider_name, model=self.model)


class _PRDArtifactRunner:
    def __init__(self, canonical: Path) -> None:
        self.canonical = canonical
        self.counter = 0

    def run_stage(self, *, stage: str, context: dict):
        self.counter += 1
        self.canonical.parent.mkdir(parents=True, exist_ok=True)
        self.canonical.write_text(
            json.dumps({"run_counter": self.counter, "run_id": context["run_id"], "stage": stage}),
            encoding="utf-8",
        )
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} complete",
            artifacts=[str(self.canonical)],
            summary={"runtime_validation_status": "pass"} if stage == "traceability" else {},
        )


def _stage_artifact(result, stage_id: str, filename: str) -> str:
    for stage in result.stages:
        if stage.stage == stage_id:
            for artifact in stage.artifacts:
                if Path(artifact).name == filename:
                    return artifact
    raise AssertionError(f"missing artifact {filename} for stage {stage_id}")


def _valid_prd_output() -> str:
    return json.dumps(
        {
            "prds": [
                {
                    "prd_id": "PRD-V1",
                    "version_id": "V1",
                    "title": "Workout content quality PRD",
                    "overview": "Define workout content quality scope.",
                    "problem_statement": "Users report declining workout content quality.",
                    "evidence_summary": "Evidence is traceable through REQ-004 and FINDING-004.",
                    "goals": ["Improve workout content quality."],
                    "non_goals": ["Do not expand scope beyond validated requirements."],
                    "requirement_ids": ["REQ-004"],
                    "risks": ["Content quality perception may remain subjective."],
                    "success_metrics": ["User satisfaction score with workout content"],
                    "open_questions": ["What target should be used for the workout content satisfaction score?"],
                }
            ]
        }
    )


def _pass_validation() -> dict:
    return {"status": "Success", "passed": True}


def _roadmap() -> dict:
    return {
        "versions": [
            {
                "version_id": "V1",
                "name": "Workout Content",
                "goal": "Improve workout content quality.",
                "requirement_ids": ["REQ-004"],
                "risks": [],
                "success_metrics": ["User satisfaction score with workout content"],
            }
        ]
    }


def _requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-004",
            "requirement_type": "problem",
            "title": "Improve workout content quality",
            "description": "Workout content quality should address user complaints.",
            "acceptance_criteria": ["Users can identify refreshed workout content."],
            "finding_ids": ["FINDING-004"],
            "success_metrics": ["User satisfaction score with workout content"],
        }
    ]


def _findings() -> list[dict]:
    return [
        {
            "finding_id": "FINDING-004",
            "title": "Declining content quality",
            "statement": "Users report declining workout content quality.",
            "issue_ids": ["ISSUE-004"],
            "review_ids": ["review-001"],
        }
    ]


def _evidence_report() -> dict:
    return {"evidence_reports": [{"finding_id": "FINDING-004", "evidence_strength": "Medium"}]}


def _issues() -> list[dict]:
    return [{"issue_id": "ISSUE-004", "topic_ids": ["TOPIC-004"], "review_ids": ["review-001"]}]


def _topics() -> list[dict]:
    return [{"topic_id": "TOPIC-004", "review_ids": ["review-001"]}]


def _reviews() -> list[dict]:
    return [{"id": "review-001"}]


if __name__ == "__main__":
    unittest.main()
