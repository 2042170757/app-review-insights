import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.generate_test_cases import (
    load_object,
    load_optional_findings,
    load_optional_reviews,
    load_prds,
    load_requirements,
)


class GenerateTestCasesTests(unittest.TestCase):
    def test_loaders(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            requirements_path = base / "requirements.json"
            prds_path = base / "prds.json"
            findings_path = base / "findings.json"
            reviews_path = base / "reviews.json"
            requirements_path.write_text(json.dumps({"requirements": [{"requirement_id": "REQ-001"}]}), encoding="utf-8")
            prds_path.write_text(json.dumps({"prds": [{"prd_id": "PRD-V1"}]}), encoding="utf-8")
            findings_path.write_text(json.dumps({"findings": [{"finding_id": "FINDING-001"}]}), encoding="utf-8")
            reviews_path.write_text(json.dumps({"reviews": [{"id": "review-001"}]}), encoding="utf-8")

            requirements = load_requirements(requirements_path)
            prds = load_prds(prds_path)
            findings = load_optional_findings(findings_path)
            reviews = load_optional_reviews(reviews_path)

        self.assertEqual(requirements[0]["requirement_id"], "REQ-001")
        self.assertEqual(prds[0]["prd_id"], "PRD-V1")
        self.assertEqual(findings[0]["finding_id"], "FINDING-001")
        self.assertEqual(reviews[0]["id"], "review-001")

    def test_optional_loaders_allow_missing_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)

            self.assertEqual(load_optional_findings(base / "missing-findings.json"), [])
            self.assertEqual(load_optional_reviews(base / "missing-reviews.json"), [])

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
