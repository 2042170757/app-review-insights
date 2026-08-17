import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.generate_requirements import (
    build_default_mock_output,
    load_evidence_report,
    load_finding_validation,
    load_findings,
    save_outputs,
)
from app.requirement_validator import validate_requirement_output


class GenerateRequirementsTests(unittest.TestCase):
    def test_default_mock_output_uses_first_validated_finding(self) -> None:
        raw_output = build_default_mock_output(_findings())
        payload = json.loads(raw_output)

        self.assertEqual(payload["requirements"][0]["finding_ids"], ["FINDING-001"])
        self.assertEqual(payload["requirements"][0]["source_review_ids"], ["r1", "r2"])

    def test_default_mock_output_empty_without_findings(self) -> None:
        raw_output = build_default_mock_output([])

        self.assertEqual(json.loads(raw_output), {"requirements": []})

    def test_save_outputs_marks_mock_result(self) -> None:
        raw_output = build_default_mock_output(_findings())
        validation = validate_requirement_output(
            raw_output,
            findings_by_id={finding["finding_id"]: finding for finding in _findings()},
            finding_validation_passed=True,
            eligible_finding_ids={"FINDING-001"},
        )
        with TemporaryDirectory() as temp_dir:
            paths = save_outputs(
                raw_output=raw_output,
                validation=validation,
                requirements=[requirement.__dict__ for requirement in validation.requirements],
                output_dir=Path(temp_dir),
            )
            raw = json.loads(paths["raw"].read_text(encoding="utf-8"))
            requirements = json.loads(paths["requirements"].read_text(encoding="utf-8"))
            requirement_validation = json.loads(paths["validation"].read_text(encoding="utf-8"))

        self.assertEqual(raw["provider"], "mock")
        self.assertTrue(raw["is_mock"])
        self.assertEqual(len(requirements["requirements"]), 1)
        self.assertEqual(requirement_validation["status"], "Success")

    def test_loaders(self) -> None:
        with TemporaryDirectory() as temp_dir:
            findings_path = Path(temp_dir) / "findings.json"
            finding_validation_path = Path(temp_dir) / "finding_validation.json"
            evidence_report_path = Path(temp_dir) / "evidence_report.json"
            findings_path.write_text(json.dumps({"findings": _findings()}), encoding="utf-8")
            finding_validation_path.write_text(json.dumps({"status": "Success", "passed": True}), encoding="utf-8")
            evidence_report_path.write_text(json.dumps({"evidence_reports": []}), encoding="utf-8")

            findings = load_findings(findings_path)
            finding_validation = load_finding_validation(finding_validation_path)
            evidence_report = load_evidence_report(evidence_report_path)

        self.assertEqual(findings[0]["finding_id"], "FINDING-001")
        self.assertTrue(finding_validation["passed"])
        self.assertEqual(evidence_report["evidence_reports"], [])


def _findings() -> list[dict]:
    return [
        {
            "finding_id": "FINDING-001",
            "issue_ids": ["ISSUE-001"],
            "review_ids": ["r1", "r2"],
            "title": "Paywall friction",
            "statement": "Users report unclear subscription and paywall expectations.",
            "evidence_summary": "Two reviews support subscription clarity concerns.",
            "support_count": 2,
            "confidence": 0.82,
            "uncertainty": "Small sample.",
            "conflicting_review_ids": [],
        }
    ]


if __name__ == "__main__":
    unittest.main()
