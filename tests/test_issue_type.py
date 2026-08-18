import unittest

from app.issue_schema import (
    CLASSIFIED_ISSUE_JSON_SCHEMA,
    ISSUE_TYPE_MIXED,
    ISSUE_TYPE_NEUTRAL_OBSERVATION,
    ISSUE_TYPE_POSITIVE_FEEDBACK,
    ISSUE_TYPE_PROBLEM,
)
from app.issue_type import classify_issue, classify_issues, validate_issue_type


class IssueTypeTests(unittest.TestCase):
    def test_valid_issue_type(self) -> None:
        self.assertTrue(validate_issue_type(ISSUE_TYPE_PROBLEM))
        self.assertTrue(validate_issue_type(ISSUE_TYPE_MIXED))
        self.assertTrue(validate_issue_type(ISSUE_TYPE_POSITIVE_FEEDBACK))
        self.assertTrue(validate_issue_type(ISSUE_TYPE_NEUTRAL_OBSERVATION))

    def test_invalid_issue_type(self) -> None:
        self.assertFalse(validate_issue_type("bug"))

    def test_classified_issue_schema_requires_issue_type(self) -> None:
        self.assertIn("issue_type", CLASSIFIED_ISSUE_JSON_SCHEMA["required"])
        self.assertIn(ISSUE_TYPE_POSITIVE_FEEDBACK, CLASSIFIED_ISSUE_JSON_SCHEMA["properties"]["issue_type"]["enum"])

    def test_problem_classification(self) -> None:
        result = classify_issue(
            _issue(
                name="Subscription billing issues",
                description="Users report hidden charges and difficulty canceling.",
                merge_rationale="The issue describes billing problems.",
            )
        )

        self.assertEqual(result.issue_type, ISSUE_TYPE_PROBLEM)

    def test_mixed_classification(self) -> None:
        result = classify_issue(
            _issue(
                name="Effective workouts but subscription issue",
                description="Users enjoy effective workouts but mention paywall frustration.",
                merge_rationale="The issue contains positive experience and problem signals.",
            )
        )

        self.assertEqual(result.issue_type, ISSUE_TYPE_MIXED)

    def test_positive_feedback_classification(self) -> None:
        result = classify_issue(
            _issue(
                issue_id="ISSUE-007",
                name="Positive workout experience and effectiveness",
                description="Users express positive feedback about workouts and motivation.",
                merge_rationale="All reviews express positive feedback about the app's workouts.",
            )
        )

        self.assertEqual(result.issue_id, "ISSUE-007")
        self.assertEqual(result.issue_type, ISSUE_TYPE_POSITIVE_FEEDBACK)

    def test_not_a_product_problem_positive_feedback_is_not_mixed(self) -> None:
        result = classify_issue(
            _issue(
                issue_id="ISSUE-012",
                name="Positive feedback and appreciation",
                description="Users express overall satisfaction with the app, praising its usefulness and content.",
                merge_rationale=(
                    "All reviews in this topic are positive feedback and appreciation for the app. "
                    "This is not a product problem but is preserved for deterministic classification."
                ),
                uncertainty="High confidence as many reviews are clearly positive.",
            )
        )

        self.assertEqual(result.issue_type, ISSUE_TYPE_POSITIVE_FEEDBACK)

    def test_no_issue_here_is_neutral_not_problem(self) -> None:
        result = classify_issue(
            _issue(
                name="No issue context",
                description="There is no issue here; the review only describes normal use.",
                merge_rationale="This is an observation without user friction.",
                uncertainty="Neutral observation.",
            )
        )

        self.assertEqual(result.issue_type, ISSUE_TYPE_NEUTRAL_OBSERVATION)

    def test_not_complaining_positive_feedback_is_positive(self) -> None:
        result = classify_issue(
            _issue(
                name="Positive resource feedback",
                description="The user is not complaining and says this is a great resource.",
                merge_rationale="Positive feedback without a product problem.",
                uncertainty="Clear positive sentiment.",
            )
        )

        self.assertEqual(result.issue_type, ISSUE_TYPE_POSITIVE_FEEDBACK)

    def test_real_problem_context_still_classifies_as_problem(self) -> None:
        result = classify_issue(
            _issue(
                name="Cancellation problem",
                description="I have a problem cancelling and billing keeps failing.",
                merge_rationale="The issue describes cancellation and billing failure.",
            )
        )

        self.assertEqual(result.issue_type, ISSUE_TYPE_PROBLEM)

    def test_crash_context_still_classifies_as_problem(self) -> None:
        result = classify_issue(
            _issue(
                name="App crashes",
                description="The app crashes during article browsing.",
                merge_rationale="The issue describes a real stability failure.",
            )
        )

        self.assertEqual(result.issue_type, ISSUE_TYPE_PROBLEM)

    def test_lack_of_targeted_results_is_problem_not_positive_feedback(self) -> None:
        result = classify_issue(
            _issue(
                issue_id="ISSUE-012",
                name="Lack of targeted results",
                description=(
                    "A user reports not feeling the workout in the intended area, "
                    "suggesting a potential gap in effectiveness for specific goals."
                ),
                merge_rationale="Single topic representing a distinct concern about lack of targeted results.",
            )
        )

        self.assertEqual(result.issue_type, ISSUE_TYPE_PROBLEM)

    def test_neutral_observation_classification(self) -> None:
        result = classify_issue(
            _issue(
                name="Workout categories mentioned",
                description="This issue describes how users mention workout categories.",
                merge_rationale="The reviews are observations without clear user friction.",
                uncertainty="Neutral observation.",
            )
        )

        self.assertEqual(result.issue_type, ISSUE_TYPE_NEUTRAL_OBSERVATION)

    def test_unknown_issue_id(self) -> None:
        issue = _issue()
        issue["issue_id"] = ""

        with self.assertRaises(ValueError):
            classify_issue(issue)

    def test_classify_issues(self) -> None:
        results = classify_issues([_issue(issue_id="ISSUE-001"), _issue(issue_id="ISSUE-002")])

        self.assertEqual(len(results), 2)


def _issue(**overrides) -> dict:
    issue = {
        "issue_id": "ISSUE-001",
        "name": "Paywall problem",
        "description": "Users report paywall frustration.",
        "topic_ids": ["TOPIC-001"],
        "review_ids": ["r1"],
        "merge_rationale": "The issue describes a product problem.",
        "confidence": 0.9,
        "uncertainty": "",
    }
    issue.update(overrides)
    return issue


if __name__ == "__main__":
    unittest.main()
