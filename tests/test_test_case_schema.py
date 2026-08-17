import unittest

from app.test_case_schema import TEST_CASE_JSON_SCHEMA, VALID_TEST_TYPES, TestCase, TestCaseGenerationOutput


class TestCaseSchemaTests(unittest.TestCase):
    def test_test_case_dataclass(self) -> None:
        test_case = TestCase(
            test_case_id="TC-001",
            requirement_id="REQ-001",
            acceptance_criteria_ids=["REQ-001-AC-1"],
            title="Validate free access",
            preconditions=[],
            steps=["Open the relevant product flow."],
            expected_result="The free access criterion is satisfied.",
            test_type="functional",
            priority="P1",
            source_review_ids=["review-001"],
        )

        self.assertEqual(test_case.test_case_id, "TC-001")
        self.assertEqual(test_case.test_type, "functional")
        self.assertEqual(test_case.source_review_ids, ["review-001"])

    def test_generation_output_dataclass(self) -> None:
        output = TestCaseGenerationOutput(test_cases=[])

        self.assertEqual(output.test_cases, [])

    def test_schema_requires_core_fields(self) -> None:
        required = set(TEST_CASE_JSON_SCHEMA["properties"]["test_cases"]["items"]["required"])

        self.assertIn("test_case_id", required)
        self.assertIn("requirement_id", required)
        self.assertIn("acceptance_criteria_ids", required)
        self.assertIn("expected_result", required)
        self.assertIn("source_review_ids", required)
        self.assertIn("functional", VALID_TEST_TYPES)


if __name__ == "__main__":
    unittest.main()
