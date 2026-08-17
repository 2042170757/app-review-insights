import json
import unittest

from app.test_case_validator import STATUS_SCOPE_OVERREACH, STATUS_SUCCESS, validate_test_case_output


class TestCaseScopeOverreachTests(unittest.TestCase):
    def test_acceptance_criteria_aligned_test_passes(self) -> None:
        result = _validate(_payload("Open support settings.", "Support contact options are visible."))

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_coupon_overreach_fails(self) -> None:
        result = _validate(_payload("Apply a coupon at checkout.", "Coupon discount is applied."))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCOPE_OVERREACH)
        self.assertIn("coupon", result.scope_overreach_errors[0])

    def test_discount_overreach_fails(self) -> None:
        result = _validate(_payload("Open the discount screen.", "A discount is displayed."))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCOPE_OVERREACH)
        self.assertIn("discount", result.scope_overreach_errors[0])

    def test_refund_overreach_fails(self) -> None:
        result = _validate(_payload("Request a refund.", "A refund is issued."))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCOPE_OVERREACH)
        self.assertIn("refund", result.scope_overreach_errors[0])

    def test_api_implementation_overreach_fails(self) -> None:
        result = _validate(_payload("Call the support API endpoint.", "The endpoint returns support data."))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCOPE_OVERREACH)
        self.assertIn("technical_api", result.scope_overreach_errors[0])

    def test_new_feature_overreach_fails(self) -> None:
        result = _validate(_payload("Open the AI chatbot.", "The AI chatbot answers support questions."))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCOPE_OVERREACH)
        self.assertIn("ai_chatbot", result.scope_overreach_errors[0])

    def test_legitimate_product_term_passes_when_in_requirement(self) -> None:
        result = _validate(
            _payload("Open the support contact option.", "Support contact option is available."),
            requirements=_support_requirements(),
        )

        self.assertTrue(result.passed)

    def test_positive_requirement_stays_within_preservation_scope(self) -> None:
        result = _validate(
            _payload("View the daily streak.", "The daily streak remains visible."),
            requirements=_positive_requirements(),
        )

        self.assertTrue(result.passed)

    def test_positive_requirement_coupon_overreach_fails(self) -> None:
        result = _validate(
            _payload("Apply a coupon after viewing the daily streak.", "Coupon is accepted."),
            requirements=_positive_requirements(),
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCOPE_OVERREACH)

    def test_mixed_requirement_allows_only_referenced_ac_scope(self) -> None:
        result = _validate(
            _payload("Adjust reminder frequency and verify support contact visibility.", "Reminder and support behavior match the criteria."),
            requirements=_mixed_requirements(),
            acceptance_criteria_ids=["REQ-001-AC-1", "REQ-001-AC-2"],
        )

        self.assertTrue(result.passed)

    def test_upstream_supported_coupon_passes(self) -> None:
        result = _validate(
            _payload("Review coupon eligibility.", "Coupon eligibility is displayed."),
            requirements=_coupon_requirements(),
        )

        self.assertTrue(result.passed)


def _validate(
    payload: dict,
    *,
    requirements: list[dict] | None = None,
    acceptance_criteria_ids: list[str] | None = None,
):
    if acceptance_criteria_ids:
        payload["test_cases"][0]["acceptance_criteria_ids"] = acceptance_criteria_ids
    return validate_test_case_output(
        json.dumps(payload),
        requirements=requirements or _support_requirements(),
        requirement_validation_passed=True,
        prd_validation_passed=True,
        findings_by_id={"FINDING-001": {"finding_id": "FINDING-001", "review_ids": ["review-001"]}},
        valid_review_ids={"review-001"},
    )


def _payload(step: str, expected_result: str) -> dict:
    return {
        "test_cases": [
            {
                "test_case_id": "TC-001",
                "requirement_id": "REQ-001",
                "acceptance_criteria_ids": ["REQ-001-AC-1"],
                "title": "Validate scoped behavior",
                "preconditions": [],
                "steps": [step],
                "expected_result": expected_result,
                "test_type": "functional",
                "priority": "P2",
                "source_review_ids": ["review-001"],
            }
        ]
    }


def _support_requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "title": "Improve support accessibility",
            "description": "Users can easily access support contact options.",
            "acceptance_criteria": ["Support contact options are visible."],
            "priority": "P2",
        }
    ]


def _positive_requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "requirement_type": "positive_feedback",
            "title": "Preserve daily streak",
            "description": "Maintain the daily streak experience users value.",
            "acceptance_criteria": ["The daily streak remains visible."],
            "priority": "P2",
        }
    ]


def _mixed_requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "title": "Improve reminders and support",
            "description": "Users need reminder controls and accessible support.",
            "acceptance_criteria": [
                "Users can adjust reminder frequency.",
                "Support contact options are visible.",
            ],
            "priority": "P2",
        }
    ]


def _coupon_requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "title": "Clarify coupon eligibility",
            "description": "Coupon eligibility should be visible before checkout.",
            "acceptance_criteria": ["Coupon eligibility is displayed."],
            "priority": "P2",
        }
    ]


if __name__ == "__main__":
    unittest.main()
