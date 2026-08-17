import unittest

from app.issue_schema import ISSUE_CONSOLIDATION_JSON_SCHEMA, Issue, IssueConsolidationOutput


class IssueSchemaTests(unittest.TestCase):
    def test_issue_dataclass(self) -> None:
        issue = Issue(
            issue_id="ISSUE-001",
            name="Subscription transparency",
            description="Users do not understand subscription terms.",
            topic_ids=["TOPIC-001"],
            review_ids=["r1"],
            merge_rationale="Topic evidence points to the same subscription issue.",
            confidence=0.86,
            uncertainty="Small sample.",
        )

        self.assertEqual(issue.issue_id, "ISSUE-001")
        self.assertEqual(issue.topic_ids, ["TOPIC-001"])
        self.assertEqual(issue.review_ids, ["r1"])

    def test_issue_output_dataclass(self) -> None:
        output = IssueConsolidationOutput(issues=[], unmerged_topic_ids=["TOPIC-001"])

        self.assertEqual(output.issues, [])
        self.assertEqual(output.unmerged_topic_ids, ["TOPIC-001"])

    def test_json_schema_requires_expected_fields(self) -> None:
        issue_schema = ISSUE_CONSOLIDATION_JSON_SCHEMA["properties"]["issues"]["items"]

        self.assertEqual(ISSUE_CONSOLIDATION_JSON_SCHEMA["required"], ["issues", "unmerged_topic_ids"])
        self.assertIn("merge_rationale", issue_schema["required"])
        self.assertIn("topic_ids", issue_schema["required"])
        self.assertIn("review_ids", issue_schema["required"])
        self.assertEqual(issue_schema["properties"]["confidence"]["minimum"], 0)
        self.assertEqual(issue_schema["properties"]["confidence"]["maximum"], 1)
        self.assertIn("unmerged_topic_ids", ISSUE_CONSOLIDATION_JSON_SCHEMA["properties"])


if __name__ == "__main__":
    unittest.main()
