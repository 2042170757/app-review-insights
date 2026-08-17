import unittest

from app.final_validation import (
    audit_exam_requirements,
    audit_statistics_model_separation,
    audit_uncertainty_conflict,
    run_generalization_audit,
)
from app.model_registry import audit_ai_deterministic_boundary, audit_failure_state_registry
from app.traceability import TraceabilityGraph
from tests.test_traceability import _artifacts


class FinalValidationTests(unittest.TestCase):
    def test_statistics_model_separation_passes_for_consistent_fixture(self) -> None:
        result = audit_statistics_model_separation(_artifacts())

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["errors"], [])

    def test_statistics_model_separation_detects_support_count_mismatch(self) -> None:
        artifacts = _artifacts()
        artifacts.evidence_report["evidence_reports"][0]["support_count"] = 99

        result = audit_statistics_model_separation(artifacts)

        self.assertEqual(result["status"], "FAIL")
        self.assertIn("support_count", result["errors"][0])

    def test_uncertainty_conflict_audit_requires_fields(self) -> None:
        artifacts = _artifacts()

        result = audit_uncertainty_conflict(artifacts)

        self.assertEqual(result["status"], "PASS")

    def test_uncertainty_conflict_audit_detects_missing_open_questions(self) -> None:
        artifacts = _artifacts()
        artifacts.prds[0]["open_questions"] = []

        result = audit_uncertainty_conflict(artifacts)

        self.assertEqual(result["status"], "FAIL")
        self.assertIn("missing open_questions", result["errors"][0])

    def test_generalization_audit_uses_fixtures_without_network(self) -> None:
        result = run_generalization_audit()

        self.assertEqual(result["status"], "PASS")
        self.assertIn("com.example.reader", result["fixture_app_ids"])
        self.assertIn("zh", result["fixture_languages"])
        self.assertGreaterEqual(result["duplicate_count"], 2)

    def test_exam_requirement_coverage_marks_ui_missing(self) -> None:
        traceability = TraceabilityGraph(_artifacts()).validate()

        result = audit_exam_requirements(
            traceability_status=traceability,
            statistics_model={"status": "PASS"},
            failure_state=audit_failure_state_registry(),
            uncertainty_conflict={"status": "PASS"},
            boundary=audit_ai_deterministic_boundary(),
            generalization={"status": "PASS"},
        )

        self.assertEqual(result["items"]["R. UI readiness"], "MISSING")
        self.assertLess(result["coverage"], 100.0)


if __name__ == "__main__":
    unittest.main()
