import unittest

from app.evidence_engine import (
    EVIDENCE_HIGH,
    EVIDENCE_INVALID,
    EVIDENCE_LOW,
    EVIDENCE_MEDIUM,
    calculate_evidence_report,
    calculate_evidence_reports,
    classify_evidence_strength,
)


class EvidenceEngineTests(unittest.TestCase):
    def test_evidence_strength_rules(self) -> None:
        self.assertEqual(classify_evidence_strength(0), EVIDENCE_INVALID)
        self.assertEqual(classify_evidence_strength(1), EVIDENCE_LOW)
        self.assertEqual(classify_evidence_strength(2), EVIDENCE_MEDIUM)
        self.assertEqual(classify_evidence_strength(3), EVIDENCE_MEDIUM)
        self.assertEqual(classify_evidence_strength(4), EVIDENCE_HIGH)

    def test_low_evidence_report(self) -> None:
        report = calculate_evidence_report(_finding(review_ids=["r1"]))

        self.assertEqual(report.support_count, 1)
        self.assertEqual(report.unique_support_count, 1)
        self.assertEqual(report.evidence_strength, EVIDENCE_LOW)
        self.assertIn("only one supporting review", report.evidence_limitations)

    def test_medium_evidence_report(self) -> None:
        report = calculate_evidence_report(_finding(review_ids=["r1", "r2"]))

        self.assertEqual(report.evidence_strength, EVIDENCE_MEDIUM)
        self.assertIn("limited sample size", report.evidence_limitations)

    def test_high_evidence_report(self) -> None:
        report = calculate_evidence_report(_finding(review_ids=["r1", "r2", "r3", "r4"]))

        self.assertEqual(report.evidence_strength, EVIDENCE_HIGH)

    def test_conflicting_evidence_report(self) -> None:
        report = calculate_evidence_report(_finding(review_ids=["r1", "r2"], conflicting_review_ids=["r3"]))

        self.assertEqual(report.conflicting_count, 1)
        self.assertIn("conflicting reviews exist", report.evidence_limitations)

    def test_duplicate_support_count_is_unique(self) -> None:
        report = calculate_evidence_report(_finding(review_ids=["r1", "r1", "r2"]))

        self.assertEqual(report.support_count, 2)
        self.assertEqual(report.unique_support_count, 2)

    def test_calculate_reports(self) -> None:
        reports = calculate_evidence_reports([_finding(finding_id="FINDING-001")])

        self.assertEqual(len(reports), 1)


def _finding(**overrides) -> dict:
    finding = {
        "finding_id": "FINDING-001",
        "review_ids": ["r1"],
        "conflicting_review_ids": [],
    }
    finding.update(overrides)
    return finding


if __name__ == "__main__":
    unittest.main()
