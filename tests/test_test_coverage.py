import unittest

from app.test_coverage import build_acceptance_criteria_index, calculate_test_coverage, make_acceptance_criteria_id


class TestCoverageTests(unittest.TestCase):
    def test_acceptance_criteria_ids_are_stable(self) -> None:
        self.assertEqual(make_acceptance_criteria_id("REQ-003", 2), "REQ-003-AC-2")

    def test_build_acceptance_criteria_index(self) -> None:
        index = build_acceptance_criteria_index(_requirements())

        self.assertEqual(index["REQ-001-AC-1"]["requirement_id"], "REQ-001")
        self.assertEqual(index["REQ-002-AC-2"]["index"], 2)

    def test_requirement_and_acceptance_criteria_coverage_are_separate(self) -> None:
        report = calculate_test_coverage(
            requirements=_requirements(),
            test_cases=[
                {"requirement_id": "REQ-001", "acceptance_criteria_ids": ["REQ-001-AC-1"]},
                {"requirement_id": "REQ-002", "acceptance_criteria_ids": ["REQ-002-AC-1", "REQ-002-AC-1"]},
            ],
        )

        self.assertEqual(report.total_requirements, 2)
        self.assertEqual(report.covered_requirements, 2)
        self.assertEqual(report.requirement_coverage, 100.0)
        self.assertEqual(report.total_acceptance_criteria, 4)
        self.assertEqual(report.covered_acceptance_criteria, 2)
        self.assertEqual(report.acceptance_criteria_coverage, 50.0)
        self.assertEqual(report.uncovered_acceptance_criteria_ids, ["REQ-001-AC-2", "REQ-002-AC-2"])

    def test_requirement_without_test_coverage(self) -> None:
        report = calculate_test_coverage(
            requirements=_requirements(),
            test_cases=[{"requirement_id": "REQ-001", "acceptance_criteria_ids": ["REQ-001-AC-1"]}],
        )

        self.assertEqual(report.covered_requirements, 1)
        self.assertEqual(report.uncovered_requirement_ids, ["REQ-002"])


def _requirements() -> list[dict]:
    return [
        {"requirement_id": "REQ-001", "acceptance_criteria": ["A", "B"]},
        {"requirement_id": "REQ-002", "acceptance_criteria": ["C", "D"]},
    ]


if __name__ == "__main__":
    unittest.main()
