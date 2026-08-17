import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.roadmap_planner import build_default_mock_output, create_mock_provider, plan_roadmap, save_roadmap_outputs


class RoadmapPlannerTests(unittest.TestCase):
    def test_default_mock_output_assigns_all_requirements(self) -> None:
        payload = json.loads(build_default_mock_output(_requirements()))

        self.assertEqual(len(payload["roadmap_items"]), 3)
        self.assertEqual(payload["roadmap_items"][0]["version_id"], "V1")
        self.assertEqual(payload["roadmap_items"][2]["version_id"], "V2")

    def test_plan_roadmap_with_mock_provider(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = plan_roadmap(
                requirements=_requirements(),
                requirement_validation={"status": "Success", "passed": True},
                priority_report=_priority_report(),
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
        self.assertEqual(result.validation.status, "Requirement Validation Failed")

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
        self.assertEqual(len(roadmap["versions"]), 4)
        self.assertEqual(validation["status"], "Success")


def _requirements() -> list[dict]:
    return [
        {"requirement_id": "REQ-001", "priority": "P1"},
        {"requirement_id": "REQ-002", "priority": "P1"},
        {"requirement_id": "REQ-003", "priority": "P2"},
    ]


def _priority_report() -> dict:
    return {
        "priority_report": [
            {"requirement_id": "REQ-001", "final_priority": "P1"},
            {"requirement_id": "REQ-002", "final_priority": "P1"},
            {"requirement_id": "REQ-003", "final_priority": "P2"},
        ]
    }


if __name__ == "__main__":
    unittest.main()
