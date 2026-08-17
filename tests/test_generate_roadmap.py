import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.generate_roadmap import load_priority_report, load_requirement_validation, load_requirements


class GenerateRoadmapTests(unittest.TestCase):
    def test_loaders(self) -> None:
        with TemporaryDirectory() as temp_dir:
            requirements_path = Path(temp_dir) / "requirements.json"
            validation_path = Path(temp_dir) / "requirement_validation.json"
            priority_path = Path(temp_dir) / "priority_report.json"
            requirements_path.write_text(
                json.dumps({"requirements": [{"requirement_id": "REQ-001"}]}),
                encoding="utf-8",
            )
            validation_path.write_text(json.dumps({"status": "Success", "passed": True}), encoding="utf-8")
            priority_path.write_text(json.dumps({"priority_report": []}), encoding="utf-8")

            requirements = load_requirements(requirements_path)
            validation = load_requirement_validation(validation_path)
            priority = load_priority_report(priority_path)

        self.assertEqual(requirements[0]["requirement_id"], "REQ-001")
        self.assertTrue(validation["passed"])
        self.assertEqual(priority["priority_report"], [])

    def test_invalid_requirements_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "requirements.json"
            path.write_text(json.dumps({"requirements": "bad"}), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_requirements(path)


if __name__ == "__main__":
    unittest.main()
