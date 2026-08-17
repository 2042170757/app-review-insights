import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.generate_prd import (
    load_findings,
    load_issues,
    load_object,
    load_requirements,
    load_reviews,
    load_topics,
    load_validation,
)


class GeneratePRDTests(unittest.TestCase):
    def test_loaders(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            requirements_path = base / "requirements.json"
            findings_path = base / "findings.json"
            issues_path = base / "issues.json"
            topics_path = base / "topics.json"
            reviews_path = base / "reviews.json"
            validation_path = base / "validation.json"
            requirements_path.write_text(json.dumps({"requirements": [{"requirement_id": "REQ-001"}]}), encoding="utf-8")
            findings_path.write_text(json.dumps({"findings": [{"finding_id": "FINDING-001"}]}), encoding="utf-8")
            issues_path.write_text(json.dumps({"issues": [{"issue_id": "ISSUE-001"}]}), encoding="utf-8")
            topics_path.write_text(json.dumps({"topics": [{"topic_id": "TOPIC-001"}]}), encoding="utf-8")
            reviews_path.write_text(json.dumps({"reviews": [{"id": "review-001"}]}), encoding="utf-8")
            validation_path.write_text(json.dumps({"status": "Success", "passed": True}), encoding="utf-8")

            requirements = load_requirements(requirements_path)
            findings = load_findings(findings_path)
            issues = load_issues(issues_path)
            topics = load_topics(topics_path)
            reviews = load_reviews(reviews_path)
            validation = load_validation(validation_path, "Validation")

        self.assertEqual(requirements[0]["requirement_id"], "REQ-001")
        self.assertEqual(findings[0]["finding_id"], "FINDING-001")
        self.assertEqual(issues[0]["issue_id"], "ISSUE-001")
        self.assertEqual(topics[0]["topic_id"], "TOPIC-001")
        self.assertEqual(reviews[0]["id"], "review-001")
        self.assertTrue(validation["passed"])

    def test_invalid_requirements_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "requirements.json"
            path.write_text(json.dumps({"requirements": "bad"}), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_requirements(path)

    def test_invalid_object_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.json"
            path.write_text(json.dumps([]), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_object(path, "Bad")


if __name__ == "__main__":
    unittest.main()
