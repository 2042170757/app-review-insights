import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.llm.base import LLMRequest, LLMResponse, ModelTimeoutError
from app.roadmap_planner import (
    build_default_mock_output,
    build_roadmap_request,
    create_mock_provider,
    plan_roadmap,
    save_roadmap_outputs,
)


class RoadmapPlannerTests(unittest.TestCase):
    def test_default_mock_output_assigns_all_requirements(self) -> None:
        payload = json.loads(build_default_mock_output(_requirements()))

        self.assertEqual(len(payload["roadmap_items"]), 3)
        self.assertEqual(payload["roadmap_items"][0]["version_id"], "V1")
        self.assertEqual(payload["roadmap_items"][2]["version_id"], "V2")
        self.assertTrue(all(version["requirement_ids"] for version in payload["versions"]))

    def test_plan_roadmap_with_mock_provider(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = plan_roadmap(
                requirements=_requirements(),
                requirement_validation={"status": "Success", "passed": True},
                priority_report=_priority_report(),
                evidence_report=_evidence_report(),
                existing_roadmap_validation=_existing_roadmap_validation(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result.generation_passed)
        self.assertEqual(result.provider, "mock")
        self.assertEqual(len(result.roadmap["roadmap_items"]), 3)

    def test_requirement_validation_failure(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = plan_roadmap(
                requirements=_requirements(),
                requirement_validation={"status": "Schema Validation Failed", "passed": False},
                priority_report=_priority_report(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Requirement Validation Failed")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_timeout_skips_validation(self) -> None:
        provider = _FailingProvider(ModelTimeoutError("Timeout"))
        with TemporaryDirectory() as temp_dir:
            result = plan_roadmap(
                requirements=_requirements(),
                requirement_validation={"status": "Success", "passed": True},
                priority_report=_priority_report(),
                provider=provider,
                output_dir=Path(temp_dir),
                is_mock=False,
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Timeout")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_schema_validation_failure_marks_generation_failed(self) -> None:
        provider = create_mock_provider(json.dumps({"versions": [], "roadmap_items": {}}))
        with TemporaryDirectory() as temp_dir:
            result = plan_roadmap(
                requirements=_requirements(),
                requirement_validation={"status": "Success", "passed": True},
                priority_report=_priority_report(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Schema Validation Failed")
        self.assertEqual(result.validation.status, "Schema Validation Failed")

    def test_analysis_goal_passed_to_provider(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            plan_roadmap(
                requirements=_requirements(),
                requirement_validation={"status": "Success", "passed": True},
                priority_report=_priority_report(),
                provider=provider,
                analysis_goal="custom goal",
                output_dir=Path(temp_dir),
            )

        self.assertEqual(provider.requests[0].analysis_goal, "custom goal")
        self.assertIn("custom goal", provider.requests[0].user_prompt)

    def test_build_request_contains_evidence_and_existing_dependencies(self) -> None:
        request = build_roadmap_request(
            requirements=_requirements(),
            priority_report=_priority_report(),
            evidence_report=_evidence_report(),
            existing_dependencies_by_requirement_id={"REQ-002": ["REQ-001"]},
            analysis_goal="goal",
        )
        payload = json.loads(request.user_prompt)

        self.assertEqual(payload["analysis_goal"], "goal")
        self.assertEqual(payload["validated_requirements"][0]["requirement_id"], "REQ-001")
        self.assertEqual(payload["existing_dependencies_by_requirement_id"]["REQ-002"], ["REQ-001"])

    def test_save_outputs_marks_mock(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = plan_roadmap(
                requirements=_requirements(),
                requirement_validation={"status": "Success", "passed": True},
                priority_report=_priority_report(),
                provider=provider,
                output_dir=Path(temp_dir),
            )
            paths = save_roadmap_outputs(result, output_dir=Path(temp_dir))
            raw = json.loads(paths["raw"].read_text(encoding="utf-8"))
            roadmap = json.loads(paths["roadmap"].read_text(encoding="utf-8"))
            validation = json.loads(paths["validation"].read_text(encoding="utf-8"))

        self.assertEqual(raw["provider"], "mock")
        self.assertTrue(raw["is_mock"])
        self.assertEqual(len(roadmap["versions"]), 2)
        self.assertEqual(validation["status"], "Success")

    def test_save_outputs_preserves_deferred_rationale(self) -> None:
        raw_output = json.dumps(
            {
                "versions": [
                    {
                        "version_id": "V1",
                        "name": "Subscription access and billing clarity",
                        "goal": "Improve subscription pricing, access, and billing transparency.",
                        "requirement_ids": ["REQ-001", "REQ-002"],
                        "rationale": "These requirements share the subscription and billing product goal.",
                        "risks": [],
                        "success_metrics": [],
                    }
                ],
                "roadmap_items": [_item("REQ-001"), _item("REQ-002")],
                "deferred_requirement_ids": ["REQ-003"],
                "deferred_rationale": {"REQ-003": "Evidence is too weak for this roadmap."},
            }
        )
        provider = create_mock_provider(raw_output)
        with TemporaryDirectory() as temp_dir:
            result = plan_roadmap(
                requirements=_requirements(),
                requirement_validation={"status": "Success", "passed": True},
                priority_report=_priority_report(),
                provider=provider,
                output_dir=Path(temp_dir),
            )
            roadmap = json.loads(Path(result.saved_paths["roadmap"]).read_text(encoding="utf-8"))

        self.assertTrue(result.generation_passed)
        self.assertEqual(roadmap["deferred_requirement_ids"], ["REQ-003"])
        self.assertEqual(
            roadmap["deferred_rationale"],
            {"REQ-003": "Evidence is too weak for this roadmap."},
        )


def _requirements() -> list[dict]:
    return [
        {"requirement_id": "REQ-001", "priority": "P1", "title": "Clarify subscription pricing"},
        {"requirement_id": "REQ-002", "priority": "P1", "title": "Simplify cancellation"},
        {"requirement_id": "REQ-003", "priority": "P2", "title": "Improve workout content"},
    ]


def _priority_report() -> dict:
    return {
        "priority_report": [
            {"requirement_id": "REQ-001", "final_priority": "P1"},
            {"requirement_id": "REQ-002", "final_priority": "P1"},
            {"requirement_id": "REQ-003", "final_priority": "P2"},
        ]
    }


def _evidence_report() -> dict:
    return {"evidence_reports": [{"finding_id": "FINDING-001", "evidence_strength": "High"}]}


def _existing_roadmap_validation() -> dict:
    return {"roadmap_items": [{"requirement_id": "REQ-001", "dependencies": []}]}


class _FailingProvider:
    provider_name = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise self.error


def _item(requirement_id: str, *, version_id: str = "V1", priority: str | None = None) -> dict:
    priority = priority or {"REQ-001": "P1", "REQ-002": "P1", "REQ-003": "P2"}.get(requirement_id, "P1")
    return {
        "requirement_id": requirement_id,
        "version_id": version_id,
        "priority": priority,
        "rationale": "Validated roadmap assignment.",
        "dependencies": [],
    }


if __name__ == "__main__":
    unittest.main()
