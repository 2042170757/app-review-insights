import unittest

from app.roadmap_schema import Dependency, ROADMAP_JSON_SCHEMA, RoadmapItem, RoadmapPlan


class RoadmapSchemaTests(unittest.TestCase):
    def test_dependency_dataclass(self) -> None:
        dependency = Dependency(requirement_id="REQ-002", depends_on="REQ-001")

        self.assertEqual(dependency.requirement_id, "REQ-002")
        self.assertEqual(dependency.depends_on, "REQ-001")

    def test_roadmap_item_dataclass(self) -> None:
        item = RoadmapItem(
            requirement_id="REQ-001",
            version_id="V1",
            priority="P1",
            rationale="Schedule first.",
            dependencies=[],
        )

        self.assertEqual(item.priority, "P1")

    def test_roadmap_plan_dataclass(self) -> None:
        plan = RoadmapPlan(versions=[], roadmap_items=[])

        self.assertEqual(plan.versions, [])
        self.assertEqual(plan.roadmap_items, [])

    def test_schema_requires_roadmap_item_fields(self) -> None:
        required = set(ROADMAP_JSON_SCHEMA["properties"]["roadmap_items"]["items"]["required"])

        self.assertIn("requirement_id", required)
        self.assertIn("version_id", required)
        self.assertIn("priority", required)
        self.assertIn("dependencies", required)


if __name__ == "__main__":
    unittest.main()
