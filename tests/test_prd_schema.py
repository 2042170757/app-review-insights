import unittest

from app.prd_schema import PRD, PRDGenerationOutput, PRD_JSON_SCHEMA


class PRDSchemaTests(unittest.TestCase):
    def test_prd_dataclass(self) -> None:
        prd = PRD(
            prd_id="PRD-V1",
            version_id="V1",
            title="Subscription PRD",
            overview="Overview",
            problem_statement="Problem",
            evidence_summary="Evidence from REQ-001 and FINDING-001.",
            goals=["Improve subscription clarity"],
            non_goals=[],
            requirement_ids=["REQ-001"],
            risks=[],
            success_metrics=[],
            open_questions=[],
        )

        self.assertEqual(prd.prd_id, "PRD-V1")
        self.assertEqual(prd.requirement_ids, ["REQ-001"])

    def test_generation_output_dataclass(self) -> None:
        output = PRDGenerationOutput(prds=[])

        self.assertEqual(output.prds, [])

    def test_schema_requires_prd_fields(self) -> None:
        required = set(PRD_JSON_SCHEMA["properties"]["prds"]["items"]["required"])

        self.assertIn("prd_id", required)
        self.assertIn("version_id", required)
        self.assertIn("requirement_ids", required)
        self.assertIn("evidence_summary", required)


if __name__ == "__main__":
    unittest.main()
