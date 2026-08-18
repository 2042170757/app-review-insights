import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.final_failure_diagnostics import (
    ALLOWED_CATEGORIES,
    diagnose_final_failures,
    diagnose_json_import_failure,
    diagnose_mixed_focus_failure,
)


class FinalFailureDiagnosticsTests(unittest.TestCase):
    def test_json_goal_incoherence_detection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "json-initial"
            _write_json_import_run(root, validation_status="Goal Incoherence")

            report = diagnose_json_import_failure(root)

        self.assertEqual(report["category"], "Validator Bug")
        self.assertEqual(report["stage"], "prd")
        self.assertTrue(report["goal_alignment"][0]["validator_rejected_despite_first_goal_match"])

    def test_json_missing_open_question_detection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            initial = Path(temp_dir) / "json-initial"
            retry = Path(temp_dir) / "json-retry"
            _write_json_import_run(initial, validation_status="PASS")
            _write_json_import_run(
                retry,
                validation_status="Missing Open Question",
                validation_errors=["prds[0].open_questions: missing product decision question for REQ-007"],
                requirement_id="REQ-007",
                requirement_title="App crashes when opening large files",
                open_questions=["What constitutes a large file and acceptable crash-free open rate?"],
            )

            report = diagnose_json_import_failure(initial, retry_run_root=retry)

        self.assertEqual(report["category"], "Validator Bug")
        self.assertEqual(report["missing_open_questions"][0]["requirement_id"], "REQ-007")
        self.assertTrue(report["missing_open_questions"][0]["contextual_question_present"])
        self.assertFalse(report["missing_open_questions"][0]["legacy_question_present"])

    def test_json_artifact_isolation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "json"
            _write_json_import_run(root, validation_status="PASS")

            report = diagnose_json_import_failure(root)

        self.assertTrue(report["artifact_isolation"]["passed"])
        self.assertEqual(report["artifact_isolation"]["source_type"], "json")
        self.assertEqual(report["artifact_isolation"]["display_source"], "Imported JSON")

    def test_mixed_unknown_review_id(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "mixed-initial"
            _write_mixed_topic_failure(root)

            report = diagnose_mixed_focus_failure(root)

        self.assertEqual(report["category"], "Model Reference Hallucination")
        self.assertEqual(report["topic_unknown_review_id"]["unknown_review_ids"], ["missing-review"])
        self.assertFalse(report["topic_unknown_review_id"]["unknown_review_details"][0]["in_processed_reviews"])
        self.assertTrue(report["topic_unknown_review_id"]["unknown_review_details"][0]["raw_contains"])

    def test_mixed_requirement_invalid_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            initial = Path(temp_dir) / "mixed-initial"
            retry = Path(temp_dir) / "mixed-retry"
            _write_mixed_topic_failure(initial)
            _write_mixed_requirement_failure(retry)

            report = diagnose_mixed_focus_failure(initial, retry_run_root=retry)

        self.assertEqual(report["category"], "Generator Bug")
        self.assertEqual(report["stage"], "requirement_generation")
        self.assertEqual(report["requirement_invalid_json"]["finish_reason"], "length")
        self.assertEqual(report["requirement_invalid_json"]["completion_tokens"], 3000)

    def test_retry_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            initial = Path(temp_dir) / "mixed-initial"
            retry = Path(temp_dir) / "mixed-retry"
            _write_mixed_topic_failure(initial)
            _write_mixed_requirement_failure(retry)

            report = diagnose_mixed_focus_failure(initial, retry_run_root=retry)

        retry_report = report["requirement_invalid_json"]
        self.assertTrue(retry_report["retry_attempted"])
        self.assertEqual(retry_report["retry_reason"], "invalid_json")
        self.assertFalse(retry_report["retry_success"])
        self.assertEqual(retry_report["retry_error"], "no recoverable JSON object found")

    def test_problem_positive_separation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            initial = Path(temp_dir) / "mixed-initial"
            retry = Path(temp_dir) / "mixed-retry"
            _write_mixed_topic_failure(initial)
            _write_mixed_requirement_failure(retry)

            report = diagnose_mixed_focus_failure(initial, retry_run_root=retry)

        separation = report["problem_positive_separation"]
        self.assertEqual(separation["problem_finding_count"], 1)
        self.assertEqual(separation["positive_feedback_finding_count"], 1)
        self.assertEqual(separation["separation_status"], "PASS")

    def test_root_cause_classification(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runs = root / "runs"
            matrix = root / "matrix.json"
            output = root / "diagnosis.json"
            _write_json_import_run(runs / "json-a", validation_status="Goal Incoherence")
            _write_json_import_run(
                runs / "json-b",
                validation_status="Missing Open Question",
                validation_errors=["prds[0].open_questions: missing product decision question for REQ-007"],
                requirement_id="REQ-007",
                requirement_title="App crashes when opening large files",
                open_questions=["What large file threshold should be supported without crashing?"],
            )
            _write_mixed_topic_failure(runs / "mixed-a")
            _write_mixed_requirement_failure(runs / "mixed-b")
            _write(
                matrix,
                {
                    "tests": [
                        {
                            "id": "json_import_generalization",
                            "status": "FAIL",
                            "run_id": "json-a",
                            "retry_run_id": "json-b",
                        },
                        {
                            "id": "mixed_focus_regression",
                            "status": "FAIL",
                            "run_id": "mixed-a",
                            "retry_run_id": "mixed-b",
                        },
                    ]
                },
            )

            report = diagnose_final_failures(matrix_path=matrix, runs_root=runs, output_path=output)

            self.assertTrue(output.exists())
            self.assertIn(report["json_import"]["category"], ALLOWED_CATEGORIES)
            self.assertIn(report["mixed_focus"]["category"], ALLOWED_CATEGORIES)
            self.assertEqual(report["json_import"]["category"], "Validator Bug")
            self.assertEqual(report["mixed_focus"]["category"], "Generator Bug")


def _write_json_import_run(
    root: Path,
    *,
    validation_status: str,
    validation_errors: list[str] | None = None,
    requirement_id: str = "REQ-001",
    requirement_title: str = "Search results fail to load reliably",
    open_questions: list[str] | None = None,
) -> None:
    version_goal = "Improve search reliability and prevent large file crashes."
    requirement = {
        "requirement_id": requirement_id,
        "title": requirement_title,
        "description": requirement_title,
        "finding_ids": ["FINDING-001"],
    }
    prd = {
        "prd_id": "PRD-V1",
        "version_id": "V1",
        "goals": [version_goal, "Provide reliable export support for user content."],
        "requirement_ids": [requirement_id],
        "open_questions": open_questions or ["What measurable success target should be defined?"],
        "success_metrics": ["Percentage of searches that return results."],
    }
    errors = validation_errors
    if errors is None and validation_status == "Goal Incoherence":
        errors = ["prds[0].goals: do not align with version goal V1"]
    elif errors is None:
        errors = []
    _write(
        root / "collection" / "dataset_metadata.json",
        {
            "source_type": "json",
            "display_source": "Imported JSON",
            "provider": "json_import",
            "record_count": 1,
            "valid_count": 1,
            "territory": "Unknown / Not provided",
        },
    )
    _write(root / "collection" / "import_validation.json", {"status": "PASS"})
    _write(root / "processing" / "scope_report.json", {"input_count": 1, "selected_count": 1, "excluded_count": 0})
    _write(root / "processing" / "reviews.json", {"reviews": [{"id": "review-001"}]})
    _write(root / "requirement_generation" / "requirements.json", {"requirements": [requirement]})
    _write(
        root / "roadmap" / "roadmap.json",
        {
            "versions": [
                {
                    "version_id": "V1",
                    "goal": version_goal,
                    "requirement_ids": [requirement_id],
                }
            ]
        },
    )
    _write(
        root / "prd" / "prd_generation_raw.json",
        {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "analysis_goal": "Generate PRD",
            "raw_output": json.dumps({"prds": [prd]}),
            "extracted_json": json.dumps({"prds": [prd]}),
        },
    )
    _write(root / "prd" / "prd_validation.json", {"status": validation_status, "passed": validation_status == "PASS", "errors": errors})


def _write_mixed_topic_failure(root: Path) -> None:
    raw_output = json.dumps(
        {
            "topics": [
                {
                    "topic_id": "TOPIC-001",
                    "name": "Mixed topic",
                    "review_ids": ["review-001", "missing-review"],
                }
            ]
        }
    )
    _write(root / "collection" / "dataset_metadata.json", {"provider": "apify", "source_type": "app_store", "app_id": "839285684"})
    _write(root / "processing" / "scope_report.json", {"input_count": 1, "selected_count": 1, "excluded_count": 0})
    _write(root / "processing" / "reviews.json", {"reviews": [{"id": "review-001"}]})
    _write(root / "processing" / "selected_reviews.json", {"reviews": [{"id": "review-001"}]})
    _write(
        root / "topic_discovery" / "topic_discovery_raw.json",
        {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "analysis_goal": "Mixed focus",
            "raw_output": raw_output,
            "extracted_json": raw_output,
        },
    )
    _write(
        root / "topic_discovery" / "topic_validation.json",
        {"status": "Unknown Review ID", "passed": False, "errors": ["topics[0].review_ids: unknown review id missing-review"]},
    )


def _write_mixed_requirement_failure(root: Path) -> None:
    recovery = {
        "attempted": True,
        "method": "invalid_json",
        "success": False,
        "retry_attempted": True,
        "retry_reason": "invalid_json",
        "retry_success": False,
        "retry_error": "no recoverable JSON object found",
    }
    _write(
        root / "finding_generation" / "findings.json",
        {
            "findings": [
                {"finding_id": "FINDING-001", "finding_type": "product_problem"},
                {"finding_id": "FINDING-002", "finding_type": "positive_feedback"},
            ]
        },
    )
    _write(
        root / "requirement_generation" / "requirement_generation_raw.json",
        {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "analysis_goal": "Generate requirements",
            "analysis_focus": "mixed_analysis",
            "generation_status": "Invalid JSON",
            "raw_output": "{\"requirements\": [",
            "json_recovery": recovery,
            "response_metadata": {
                "provider_response": {
                    "choices": [{"finish_reason": "length"}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 3000, "total_tokens": 3100},
                }
            },
        },
    )
    _write(
        root / "requirement_generation" / "requirement_validation.json",
        {"status": "SKIPPED", "passed": False, "errors": ["no recoverable JSON object found"]},
    )


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
