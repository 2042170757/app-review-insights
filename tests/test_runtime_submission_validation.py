import unittest

from app.workflow.validation import (
    VALIDATION_FAIL,
    VALIDATION_PASS,
    VALIDATION_PENDING,
    split_final_validation_report,
)


class RuntimeSubmissionValidationTests(unittest.TestCase):
    def test_runtime_pass_submission_pending_when_only_ui_readiness_missing(self) -> None:
        result = split_final_validation_report(_report(missing_final_deliverables=["R. UI readiness"]))

        self.assertEqual(result.runtime_validation_status, VALIDATION_PASS)
        self.assertEqual(result.submission_validation_status, VALIDATION_PENDING)
        self.assertEqual(result.submission_blockers, ["R. UI readiness"])
        self.assertTrue(result.warnings)

    def test_runtime_fail_when_backend_traceability_fails(self) -> None:
        report = _report(missing_final_deliverables=["R. UI readiness"])
        report["evidence_traceability"] = "FAIL"

        result = split_final_validation_report(report)

        self.assertEqual(result.runtime_validation_status, VALIDATION_FAIL)
        self.assertEqual(result.submission_validation_status, VALIDATION_PENDING)
        self.assertIn("evidence_traceability: FAIL", result.runtime_errors)

    def test_submission_pass_when_no_submission_blockers(self) -> None:
        result = split_final_validation_report(_report(missing_final_deliverables=[]))

        self.assertEqual(result.runtime_validation_status, VALIDATION_PASS)
        self.assertEqual(result.submission_validation_status, VALIDATION_PASS)
        self.assertEqual(result.warnings, [])


def _report(*, missing_final_deliverables: list[str]) -> dict:
    return {
        "forward_traceability": "PASS",
        "backward_traceability": "PASS",
        "artifact_consistency": "PASS",
        "evidence_traceability": "PASS",
        "explicit_test_case_review_link": "PASS",
        "statistics_model_separation": "PASS",
        "failure_state_audit": "PASS",
        "uncertainty_conflict_audit": "PASS",
        "ai_deterministic_boundary": "PASS",
        "generalization": "PASS",
        "downstream_safety": "PASS",
        "critical_issues": [],
        "missing_final_deliverables": missing_final_deliverables,
    }


if __name__ == "__main__":
    unittest.main()
