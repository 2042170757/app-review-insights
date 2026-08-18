import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.generalization_diagnostics import (
    diagnose_csv_finding,
    diagnose_json_prd_metric,
    diagnose_unknown_app_roadmap,
    write_diagnostic_reports,
)


class GeneralizationDiagnosticsTests(unittest.TestCase):
    def test_v4_schema_diagnosis(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_unknown_app_roadmap_run(root, version_ids=["V1", "V2", "V3", "V4"])

            report = diagnose_unknown_app_roadmap(root)

        self.assertFalse(report["version_schema_allows_v4"])
        self.assertEqual(report["expected_version_count"], 3)
        self.assertEqual(report["generated_invalid_version_ids"], ["V4"])
        self.assertEqual(report["diagnosis_category"], "Prompt Context Issue")

    def test_roadmap_schema_mismatch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_unknown_app_roadmap_run(root, version_ids=["V1", "V4"])

            report = diagnose_unknown_app_roadmap(root)

        self.assertEqual(report["generator_or_validator"], "Generator/prompt issue; Validator correctly rejects V4 against schema.")
        self.assertIn("Version.version_id", report["version_schema_rule"])
        self.assertIn("versions[1].version_id: invalid V4", report["validator_error"])

    def test_json_metric_diagnosis(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "json"
            baseline = Path(temp_dir) / "problem"
            _write_json_prd_metric_run(root, invalid_metric="User satisfaction with support improves")
            _write_problem_focus_baseline(baseline)

            report = diagnose_json_prd_metric(root, problem_focus_run_root=baseline)

        self.assertEqual(report["diagnosis_choice"], "A. Generator still generated vague metric")
        self.assertEqual(report["diagnosis_category"], "Generator Bug")
        self.assertEqual(report["invalid_metrics"][0]["metric"], "User satisfaction with support improves")
        self.assertFalse(report["invalid_metrics"][0]["is_measurable_by_validator"])
        self.assertTrue(report["problem_focus_baseline"]["validation_passed"])

    def test_csv_finding_diagnosis(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_csv_finding_run(root, classifications=["neutral_observation", "problem"], positive_issue_text=True)

            report = diagnose_csv_finding(root)

        self.assertEqual(report["analysis_focus"], "positive_feedback_analysis")
        self.assertEqual(report["topic_count"], 2)
        self.assertEqual(report["issue_count"], 2)
        self.assertEqual(report["eligible_issue_count"], 0)
        self.assertTrue(report["finding_generator_returned_empty"])

    def test_positive_focus_diagnosis(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_csv_finding_run(root, classifications=["neutral_observation"], positive_issue_text=True)

            report = diagnose_csv_finding(root)

        self.assertEqual(report["analysis_focus"], "positive_feedback_analysis")
        self.assertEqual(report["positive_feedback_issue_ids"], [])
        self.assertEqual(report["positive_text_issue_ids"], ["ISSUE-001"])
        self.assertEqual(report["diagnosis_category"], "Expected Limitation")

    def test_empty_finding_with_insufficient_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_csv_finding_run(root, classifications=["neutral_observation"], positive_issue_text=False)

            report = diagnose_csv_finding(root)

        self.assertEqual(report["diagnosis_category"], "Data Insufficiency")
        self.assertEqual(report["finding_raw_count"], 0)
        self.assertEqual(report["finding_valid_count"], 0)

    def test_finding_validation_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_csv_finding_run(
                root,
                classifications=["positive_feedback"],
                positive_issue_text=True,
                raw_findings=[
                    {
                        "finding_id": "FINDING-001",
                        "finding_type": "positive_feedback",
                        "issue_ids": ["ISSUE-001"],
                        "review_ids": ["unknown-review"],
                        "title": "Positive retention signal",
                        "statement": "Users value daily habit support.",
                        "evidence_summary": "Supported by ISSUE-001.",
                        "support_count": 1,
                        "confidence": 0.7,
                        "uncertainty": "Small sample.",
                        "conflicting_review_ids": [],
                    }
                ],
                finding_validation_status="Unknown Review ID",
                finding_validation_errors=["findings[0].review_ids: unknown review id unknown-review"],
            )

            report = diagnose_csv_finding(root)

        self.assertTrue(report["finding_generator_returned_rejected_results"])
        self.assertEqual(report["diagnosis_category"], "Validator Bug")
        self.assertEqual(report["finding_validation_status"], "Unknown Review ID")

    def test_writes_all_reports(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unknown = root / "unknown"
            json_run = root / "json"
            csv = root / "csv"
            output = root / "reports"
            _write_unknown_app_roadmap_run(unknown, version_ids=["V4"])
            _write_json_prd_metric_run(json_run, invalid_metric="User satisfaction with support improves")
            _write_csv_finding_run(csv, classifications=["neutral_observation"], positive_issue_text=True)

            paths = write_diagnostic_reports(
                unknown_app_run_root=unknown,
                json_run_root=json_run,
                csv_run_root=csv,
                output_dir=output,
            )

            self.assertTrue(paths["unknown_app_roadmap"].exists())
            self.assertTrue(paths["json_prd_metric"].exists())
            self.assertTrue(paths["csv_finding"].exists())


def _write_unknown_app_roadmap_run(root: Path, *, version_ids: list[str]) -> None:
    _write(
        root / "requirement_generation" / "requirements.json",
        {
            "requirements": [
                {"requirement_id": "REQ-001", "priority": "P1", "title": "Improve search reliability"},
                {"requirement_id": "REQ-002", "priority": "P2", "title": "Improve reading list export"},
            ]
        },
    )
    _write(
        root / "requirement_generation" / "priority_report.json",
        {"priority_report": [{"requirement_id": "REQ-001", "final_priority": "P1"}, {"requirement_id": "REQ-002", "final_priority": "P2"}]},
    )
    _write(root / "finding_generation" / "evidence_report.json", {"evidence_reports": []})
    versions = [
        {
            "version_id": version_id,
            "name": f"{version_id} Name",
            "goal": "Improve core product experience.",
            "requirement_ids": ["REQ-001"] if version_id != "V4" else ["REQ-002"],
            "rationale": "Product grouping.",
            "risks": [],
            "success_metrics": [],
        }
        for version_id in version_ids
    ]
    _write(
        root / "roadmap" / "roadmap_generation_raw.json",
        {
            "analysis_goal": "goal",
            "raw_output": json.dumps({"versions": versions, "roadmap_items": [], "deferred_requirement_ids": [], "deferred_rationale": {}}),
            "extracted_json": json.dumps({"versions": versions, "roadmap_items": [], "deferred_requirement_ids": [], "deferred_rationale": {}}),
        },
    )
    errors = [f"versions[{index}].version_id: invalid {version_id}" for index, version_id in enumerate(version_ids) if version_id == "V4"]
    _write(root / "roadmap" / "roadmap_validation.json", {"status": "Schema Validation Failed", "passed": False, "errors": errors})


def _write_json_prd_metric_run(root: Path, *, invalid_metric: str) -> None:
    _write(
        root / "requirement_generation" / "requirements.json",
        {
            "requirements": [
                {
                    "requirement_id": "REQ-001",
                    "requirement_type": "problem",
                    "finding_ids": ["FINDING-001"],
                    "title": "Support response clarity",
                    "description": "Users need clearer support responsiveness.",
                    "acceptance_criteria": ["Users can see support response expectations."],
                    "priority": "P2",
                    "risks": [],
                    "success_metrics": [],
                    "uncertainty": "Small sample.",
                }
            ]
        },
    )
    _write(
        root / "roadmap" / "roadmap.json",
        {
            "versions": [
                {
                    "version_id": "V1",
                    "name": "Support trust",
                    "goal": "Improve support response clarity.",
                    "requirement_ids": ["REQ-001"],
                    "rationale": "Support issue.",
                    "risks": [],
                    "success_metrics": [],
                }
            ],
            "roadmap_items": [],
            "deferred_requirement_ids": [],
            "deferred_rationale": {},
        },
    )
    _write(root / "finding_generation" / "findings.json", {"findings": [{"finding_id": "FINDING-001", "finding_type": "product_problem"}]})
    _write(root / "finding_generation" / "evidence_report.json", {"evidence_reports": []})
    prds = [
        {
            "prd_id": "PRD-V1",
            "version_id": "V1",
            "title": "Support PRD",
            "overview": "Support clarity.",
            "problem_statement": "Users report support uncertainty.",
            "evidence_summary": "Evidence cites REQ-001 and FINDING-001.",
            "goals": ["Improve support response clarity."],
            "non_goals": [],
            "requirement_ids": ["REQ-001"],
            "risks": [],
            "success_metrics": [invalid_metric],
            "open_questions": ["What measurable support success target should be defined?"],
        }
    ]
    _write(root / "prd" / "prd_generation_raw.json", {"analysis_goal": "goal", "raw_output": json.dumps({"prds": prds}), "extracted_json": json.dumps({"prds": prds})})
    _write(
        root / "prd" / "prd_validation.json",
        {
            "status": "Success Metric Invalid",
            "passed": False,
            "errors": ["prds[0].success_metrics[0]: not measurable"],
            "success_metric_errors": ["prds[0].success_metrics[0]: not measurable"],
        },
    )


def _write_problem_focus_baseline(root: Path) -> None:
    _write(root / "prd" / "prd_validation.json", {"status": "Success", "passed": True, "success_metric_errors": []})
    _write(root / "prd" / "prd_generation_raw.json", {"raw_output": json.dumps({"prds": [{"prd_id": "PRD-V1"}]})})


def _write_csv_finding_run(
    root: Path,
    *,
    classifications: list[str],
    positive_issue_text: bool,
    raw_findings: list[dict] | None = None,
    finding_validation_status: str = "Empty Findings",
    finding_validation_errors: list[str] | None = None,
) -> None:
    _write(root / "processing" / "statistics.json", {"total": 2})
    _write(root / "processing" / "scope_report.json", {"input_count": 2, "selected_count": 2})
    _write(root / "topic_discovery" / "topics.json", {"topics": [{"topic_id": "TOPIC-001"}, {"topic_id": "TOPIC-002"}]})
    issues = []
    for index, issue_type in enumerate(classifications, start=1):
        description = "Users appreciate helpful reminders and value habit support." if positive_issue_text else "Brief descriptive comment."
        issues.append(
            {
                "issue_id": f"ISSUE-{index:03d}",
                "name": "Helpful habit support" if positive_issue_text else "Short comment",
                "description": description,
                "review_ids": ["review-001"],
            }
        )
    _write(root / "issue_consolidation" / "issues.json", {"issues": issues})
    _write(
        root / "issue_consolidation" / "issue_classification.json",
        {
            "analysis_focus": "positive_feedback_analysis",
            "classifications": [
                {"issue_id": f"ISSUE-{index:03d}", "issue_type": issue_type}
                for index, issue_type in enumerate(classifications, start=1)
            ],
        },
    )
    _write(
        root / "issue_consolidation" / "finding_eligibility.json",
        {
            "analysis_focus": "positive_feedback_analysis",
            "eligibility": [
                {
                    "issue_id": f"ISSUE-{index:03d}",
                    "issue_type": issue_type,
                    "eligible_for_finding": issue_type == "positive_feedback",
                    "finding_type": "positive_feedback" if issue_type == "positive_feedback" else issue_type,
                }
                for index, issue_type in enumerate(classifications, start=1)
            ],
        },
    )
    raw_findings = raw_findings if raw_findings is not None else []
    _write(root / "finding_generation" / "finding_generation_raw.json", {"analysis_goal": "goal", "analysis_focus": "positive_feedback_analysis", "raw_output": json.dumps({"findings": raw_findings}), "extracted_json": json.dumps({"findings": raw_findings})})
    _write(root / "finding_generation" / "findings.json", {"findings": []})
    _write(root / "finding_generation" / "evidence_report.json", {"evidence_reports": []})
    _write(
        root / "finding_generation" / "finding_validation.json",
        {
            "status": finding_validation_status,
            "passed": finding_validation_status == "Empty Findings",
            "errors": finding_validation_errors or [],
        },
    )


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
