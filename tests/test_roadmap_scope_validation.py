import json
import unittest

from app.roadmap_validator import (
    STATUS_SUCCESS,
    STATUS_UNSUPPORTED_PRODUCT_DIRECTION,
    STATUS_VERSION_GOAL_INCOHERENCE,
    validate_roadmap_output,
)


class RoadmapScopeValidationTests(unittest.TestCase):
    def test_requirement_supported_goal_passes(self) -> None:
        result = _validate(
            _payload(
                "Improve support accessibility and notification control.",
                requirements=["REQ-001", "REQ-002"],
            )
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_priority_only_goal_fails(self) -> None:
        payload = _payload("Address highest-priority items first.")
        payload["versions"][0]["name"] = "Highest priority product corrections"
        payload["versions"][0]["rationale"] = "Priority bucket."

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_VERSION_GOAL_INCOHERENCE)

    def test_product_goal_with_priority_rationale_passes(self) -> None:
        payload = _payload("Improve PDF export reliability.", requirements=["REQ-003"])
        payload["versions"][0]["rationale"] = "REQ-003 is highest priority due to export freezes."

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_unsupported_product_direction_fails(self) -> None:
        result = _validate(_payload("Launch a coupon system for subscription concerns."))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNSUPPORTED_PRODUCT_DIRECTION)
        self.assertIn("coupon", result.unsupported_scope_errors[0])

    def test_new_feature_invention_fails(self) -> None:
        result = _validate(_payload("Launch an AI chatbot to improve support accessibility."))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNSUPPORTED_PRODUCT_DIRECTION)
        self.assertIn("ai_chatbot", result.unsupported_scope_errors[0])

    def test_new_business_model_invention_fails(self) -> None:
        result = _validate(_payload("Create a loyalty program and reward system for users."))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNSUPPORTED_PRODUCT_DIRECTION)
        self.assertIn("loyalty_program", " ".join(result.unsupported_scope_errors))
        self.assertIn("reward_system", " ".join(result.unsupported_scope_errors))

    def test_mixed_requirements_pass_when_goal_covers_existing_scope(self) -> None:
        result = _validate(
            _payload(
                "Improve support accessibility and reminder notification control.",
                requirements=["REQ-001", "REQ-002"],
            )
        )

        self.assertTrue(result.passed)

    def test_imported_dataset_scope_passes_without_fixed_app_domain(self) -> None:
        result = _validate(
            _payload("Improve PDF export reliability and note synchronization.", requirements=["REQ-003", "REQ-004"])
        )

        self.assertTrue(result.passed)

    def test_unknown_app_scope_passes_without_workout_domain(self) -> None:
        result = _validate(_payload("Improve article offline reading and saved page access.", requirements=["REQ-005"]))

        self.assertTrue(result.passed)

    def test_unknown_app_mixed_core_usability_goal_passes(self) -> None:
        result = _validate(
            _payload(
                "Improve the reliability and usability of core app features including search, performance, and UI/UX.",
                requirements=["REQ-007", "REQ-008", "REQ-009"],
            )
        )

        self.assertTrue(result.passed)

    def test_mixed_goal_without_requirement_overlap_fails(self) -> None:
        result = _validate(
            _payload(
                "Improve the onboarding dashboard experience.",
                requirements=["REQ-007", "REQ-008", "REQ-009"],
            )
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_VERSION_GOAL_INCOHERENCE)

    def test_upstream_supported_coupon_goal_passes(self) -> None:
        result = _validate(_payload("Clarify coupon eligibility.", requirements=["REQ-006"]))

        self.assertTrue(result.passed)


def _validate(payload: dict):
    return validate_roadmap_output(
        json.dumps(payload),
        requirements_by_id=_requirements_by_id(),
        requirement_validation_passed=True,
        priority_by_requirement_id={requirement_id: "P2" for requirement_id in _requirements_by_id()},
    )


def _payload(goal: str, *, requirements: list[str] | None = None) -> dict:
    requirements = requirements or ["REQ-001"]
    return {
        "versions": [
            {
                "version_id": "V1",
                "name": goal,
                "goal": goal,
                "requirement_ids": requirements,
                "rationale": goal,
                "risks": [],
                "success_metrics": [],
            }
        ],
        "roadmap_items": [
            {
                "requirement_id": requirement_id,
                "version_id": "V1",
                "priority": "P2",
                "rationale": "Validated assignment.",
                "dependencies": [],
            }
            for requirement_id in requirements
        ],
        "deferred_requirement_ids": [
            requirement_id
            for requirement_id in _requirements_by_id()
            if requirement_id not in requirements
        ],
        "deferred_rationale": {
            requirement_id: "Deferred in this fixture."
            for requirement_id in _requirements_by_id()
            if requirement_id not in requirements
        },
    }


def _requirements_by_id() -> dict[str, dict]:
    return {
        "REQ-001": {
            "requirement_id": "REQ-001",
            "priority": "P2",
            "title": "Improve support accessibility",
            "description": "Users should easily access support contact options.",
        },
        "REQ-002": {
            "requirement_id": "REQ-002",
            "priority": "P2",
            "title": "Allow reminder notification control",
            "description": "Users can control reminder frequency and quiet hours.",
        },
        "REQ-003": {
            "requirement_id": "REQ-003",
            "priority": "P2",
            "title": "PDF export is slow and can freeze",
            "description": "The product should provide reliable PDF export.",
        },
        "REQ-004": {
            "requirement_id": "REQ-004",
            "priority": "P2",
            "title": "Notes do not sync reliably",
            "description": "Notes should sync between devices without data loss.",
        },
        "REQ-005": {
            "requirement_id": "REQ-005",
            "priority": "P2",
            "title": "Improve offline saved article access",
            "description": "Saved articles should remain available for offline reading.",
        },
        "REQ-006": {
            "requirement_id": "REQ-006",
            "priority": "P2",
            "title": "Clarify coupon eligibility",
            "description": "Coupon terms should be visible before checkout.",
        },
        "REQ-007": {
            "requirement_id": "REQ-007",
            "priority": "P2",
            "title": "Search and find capability is unreliable",
            "description": "Users need reliable search and find behavior.",
        },
        "REQ-008": {
            "requirement_id": "REQ-008",
            "priority": "P2",
            "title": "App performance and stability are inadequate",
            "description": "Users experience freezes, slowness, and battery drain.",
        },
        "REQ-009": {
            "requirement_id": "REQ-009",
            "priority": "P2",
            "title": "UI/UX design is not user-friendly",
            "description": "Users find layout and navigation clunky.",
        },
    }


if __name__ == "__main__":
    unittest.main()
