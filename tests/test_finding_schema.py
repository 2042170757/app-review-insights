import unittest

from app.finding_schema import FINDING_JSON_SCHEMA, Finding, FindingGenerationOutput


class FindingSchemaTests(unittest.TestCase):
    def test_finding_dataclass(self) -> None:
        finding = Finding(
            finding_id="FINDING-001",
            issue_ids=["ISSUE-001"],
            review_ids=["r1", "r2"],
            title="Paywall friction",
            statement="Users report paywall friction.",
            evidence_summary="Two reviews support this finding.",
            support_count=2,
            confidence=0.82,
            uncertainty="Small sample.",
            conflicting_review_ids=[],
        )

        self.assertEqual(finding.finding_id, "FINDING-001")
        self.assertEqual(finding.support_count, 2)

    def test_output_dataclass(self) -> None:
        output = FindingGenerationOutput(findings=[])

        self.assertEqual(output.findings, [])

    def test_json_schema_requires_expected_fields(self) -> None:
        schema = FINDING_JSON_SCHEMA["properties"]["findings"]["items"]

        self.assertEqual(FINDING_JSON_SCHEMA["required"], ["findings"])
        self.assertIn("support_count", schema["required"])
        self.assertIn("conflicting_review_ids", schema["required"])
        self.assertEqual(schema["properties"]["confidence"]["minimum"], 0)
        self.assertEqual(schema["properties"]["confidence"]["maximum"], 1)


if __name__ == "__main__":
    unittest.main()
