import unittest

from app.finding_eligibility import evaluate_finding_eligibility, evaluate_finding_eligibilities
from app.issue_schema import (
    ISSUE_TYPE_MIXED,
    ISSUE_TYPE_NEUTRAL_OBSERVATION,
    ISSUE_TYPE_POSITIVE_FEEDBACK,
    ISSUE_TYPE_PROBLEM,
)


class FindingEligibilityTests(unittest.TestCase):
    def test_problem_is_eligible(self) -> None:
        result = evaluate_finding_eligibility("ISSUE-001", ISSUE_TYPE_PROBLEM)

        self.assertTrue(result.eligible_for_finding)

    def test_mixed_is_eligible(self) -> None:
        result = evaluate_finding_eligibility("ISSUE-001", ISSUE_TYPE_MIXED)

        self.assertTrue(result.eligible_for_finding)
        self.assertIn("problem portion", result.reason)

    def test_positive_feedback_is_ineligible(self) -> None:
        result = evaluate_finding_eligibility("ISSUE-007", ISSUE_TYPE_POSITIVE_FEEDBACK)

        self.assertFalse(result.eligible_for_finding)

    def test_neutral_observation_is_ineligible(self) -> None:
        result = evaluate_finding_eligibility("ISSUE-008", ISSUE_TYPE_NEUTRAL_OBSERVATION)

        self.assertFalse(result.eligible_for_finding)

    def test_invalid_issue_type(self) -> None:
        with self.assertRaises(ValueError):
            evaluate_finding_eligibility("ISSUE-001", "invalid")

    def test_input_cannot_override_eligibility(self) -> None:
        result = evaluate_finding_eligibilities(
            [
                {
                    "issue_id": "ISSUE-007",
                    "issue_type": ISSUE_TYPE_POSITIVE_FEEDBACK,
                    "eligible_for_finding": True,
                }
            ]
        )

        self.assertFalse(result[0].eligible_for_finding)


if __name__ == "__main__":
    unittest.main()
