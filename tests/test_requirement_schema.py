import unittest

from app.requirement_schema import REQUIREMENT_JSON_SCHEMA, Requirement, RequirementGenerationOutput, VALID_PRIORITIES


class RequirementSchemaTests(unittest.TestCase):
    def test_valid_priorities(self) -> None:
        self.assertEqual(VALID_PRIORITIES, {"P0", "P1", "P2", "P3"})

    def test_requirement_dataclass(self) -> None:
        requirement = Requirement(
            requirement_id="REQ-001",
            finding_ids=["FINDING-001"],
            title="Clarify subscription terms",
            description="Users need clear subscription terms before committing.",
            acceptance_criteria=["Users can see trial length, renewal date, and total price before confirming."],
            priority="P1",
            priority_rationale="Validated finding has direct purchase-impact evidence.",
            risks=[],
            success_metrics=[],
            uncertainty="Priority scoring is not implemented in Phase 4a.",
            source_review_ids=["r1"],
        )

        self.assertEqual(requirement.requirement_id, "REQ-001")
        self.assertEqual(requirement.requirement_type, "problem")
        self.assertEqual(requirement.source_review_ids, ["r1"])

    def test_generation_output_dataclass(self) -> None:
        output = RequirementGenerationOutput(requirements=[])

        self.assertEqual(output.requirements, [])

    def test_json_schema_requires_phase_4a_fields(self) -> None:
        required = set(REQUIREMENT_JSON_SCHEMA["properties"]["requirements"]["items"]["required"])

        self.assertIn("requirement_id", required)
        self.assertIn("finding_ids", required)
        self.assertIn("acceptance_criteria", required)
        self.assertIn("priority", required)
        self.assertIn("priority_rationale", required)
        self.assertIn("uncertainty", required)
        self.assertNotIn("requirement_type", required)
        self.assertIn("requirement_type", REQUIREMENT_JSON_SCHEMA["properties"]["requirements"]["items"]["properties"])


if __name__ == "__main__":
    unittest.main()
