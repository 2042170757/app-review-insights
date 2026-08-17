import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.classify_issues import load_issues, save_outputs
from app.finding_eligibility import evaluate_finding_eligibilities
from app.issue_consolidation import build_validation_context
from app.issue_type import classify_issues


class ClassifyIssuesCliLogicTests(unittest.TestCase):
    def test_issue_007_positive_feedback_and_ineligible(self) -> None:
        classifications = classify_issues([_issue_007()])
        eligibility = evaluate_finding_eligibilities([item.to_dict() for item in classifications])

        self.assertEqual(classifications[0].issue_type, "positive_feedback")
        self.assertFalse(eligibility[0].eligible_for_finding)

    def test_outputs_are_saved(self) -> None:
        classifications = classify_issues([_issue_007()])
        eligibility = evaluate_finding_eligibilities([item.to_dict() for item in classifications])
        with TemporaryDirectory() as temp_dir:
            paths = save_outputs(classifications, eligibility, output_dir=Path(temp_dir))
            classification_payload = json.loads(paths["classification"].read_text(encoding="utf-8"))
            eligibility_payload = json.loads(paths["eligibility"].read_text(encoding="utf-8"))

        self.assertTrue(classification_payload["is_deterministic"])
        self.assertTrue(eligibility_payload["is_deterministic"])
        self.assertEqual(classification_payload["classifications"][0]["issue_type"], "positive_feedback")

    def test_load_issues(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "issues.json"
            path.write_text(json.dumps({"issues": [_issue_007()]}), encoding="utf-8")

            issues = load_issues(path)

        self.assertEqual(issues[0]["issue_id"], "ISSUE-007")

    def test_evidence_integrity_context_is_unchanged(self) -> None:
        topics = [{"topic_id": "TOPIC-007", "review_ids": ["r7"]}]
        reviews = [{"id": "r7"}]

        before = build_validation_context(reviews, topics)
        classifications = classify_issues([_issue_007()])
        eligibility = evaluate_finding_eligibilities([item.to_dict() for item in classifications])
        after = build_validation_context(reviews, topics)

        self.assertEqual(before, after)
        self.assertEqual(classifications[0].issue_id, "ISSUE-007")
        self.assertFalse(eligibility[0].eligible_for_finding)


def _issue_007() -> dict:
    return {
        "issue_id": "ISSUE-007",
        "name": "Positive workout experience and effectiveness",
        "description": "Users express positive feedback about workouts and motivation.",
        "topic_ids": ["TOPIC-007"],
        "review_ids": ["r7"],
        "merge_rationale": "All reviews express positive feedback about the app's workouts and effectiveness.",
        "confidence": 0.95,
        "uncertainty": "High confidence as many reviews are positive.",
    }


if __name__ == "__main__":
    unittest.main()
