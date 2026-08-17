import json
import unittest

from app.roadmap_validator import (
    STATUS_CIRCULAR_DEPENDENCY,
    STATUS_DUPLICATE_REQUIREMENT_ID,
    STATUS_EMPTY_VERSION,
    STATUS_INVALID_JSON,
    STATUS_PRIORITY_MISMATCH,
    STATUS_REQUIREMENT_VALIDATION_FAILED,
    STATUS_SCHEMA_VALIDATION_FAILED,
    STATUS_SELF_DEPENDENCY,
    STATUS_SUCCESS,
    STATUS_UNASSIGNED_REQUIREMENT,
    STATUS_UNKNOWN_REQUIREMENT_ID,
    STATUS_UNKNOWN_VERSION_ID,
    STATUS_DEFERRED_REASON_MISSING,
    STATUS_DEPENDENCY_CHANGED,
    STATUS_VERSION_ORDER_INVALID,
    STATUS_VERSION_GOAL_INCOHERENCE,
    STATUS_VERSION_REQUIREMENT_MISMATCH,
    validate_roadmap_output,
)


class RoadmapValidatorTests(unittest.TestCase):
    def test_valid_roadmap(self) -> None:
        result = _validate(_payload())

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(len(result.roadmap_items), 3)

    def test_invalid_json(self) -> None:
        result = _validate_raw("{not json")

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INVALID_JSON)

    def test_requirement_validation_failed(self) -> None:
        result = _validate(_payload(), requirement_validation_passed=False)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_REQUIREMENT_VALIDATION_FAILED)

    def test_unknown_requirement(self) -> None:
        payload = _payload(items=[_item("REQ-001"), _item("REQ-002"), _item("REQ-MISSING")])
        payload["versions"][0]["requirement_ids"] = ["REQ-001", "REQ-002", "REQ-MISSING"]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_REQUIREMENT_ID)
        self.assertIn("REQ-MISSING", result.unknown_requirement_ids)

    def test_unknown_version(self) -> None:
        result = _validate(_payload(items=[_item("REQ-001", version_id="V9"), _item("REQ-002"), _item("REQ-003")]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_VERSION_ID)

    def test_duplicate_requirement(self) -> None:
        result = _validate(_payload(items=[_item("REQ-001"), _item("REQ-001"), _item("REQ-002"), _item("REQ-003")]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_DUPLICATE_REQUIREMENT_ID)

    def test_unassigned_requirement(self) -> None:
        payload = _payload(items=[_item("REQ-001"), _item("REQ-002")])
        payload["versions"][0]["requirement_ids"] = ["REQ-001", "REQ-002"]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNASSIGNED_REQUIREMENT)
        self.assertEqual(result.unassigned_requirement_ids, ["REQ-003"])

    def test_deferred_requirement(self) -> None:
        payload = _payload(items=[_item("REQ-001"), _item("REQ-002")])
        payload["versions"][0]["requirement_ids"] = ["REQ-001", "REQ-002"]
        payload["deferred_requirement_ids"] = ["REQ-003"]
        payload["deferred_rationale"] = {"REQ-003": "Evidence is not strong enough for current versions."}
        result = _validate(payload)

        self.assertTrue(result.passed)
        self.assertEqual(result.deferred_requirement_ids, ["REQ-003"])
        self.assertEqual(
            result.deferred_rationale,
            {"REQ-003": "Evidence is not strong enough for current versions."},
        )

    def test_deferred_reason_missing(self) -> None:
        payload = _payload(items=[_item("REQ-001"), _item("REQ-002")])
        payload["versions"][0]["requirement_ids"] = ["REQ-001", "REQ-002"]
        payload["deferred_requirement_ids"] = ["REQ-003"]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_DEFERRED_REASON_MISSING)

    def test_priority_mismatch(self) -> None:
        result = _validate(_payload(items=[_item("REQ-001", priority="P3"), _item("REQ-002"), _item("REQ-003")]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_PRIORITY_MISMATCH)

    def test_self_dependency(self) -> None:
        result = _validate(_payload(items=[_item("REQ-001", dependencies=["REQ-001"]), _item("REQ-002"), _item("REQ-003")]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SELF_DEPENDENCY)

    def test_circular_dependency(self) -> None:
        result = _validate(
            _payload(
                items=[
                    _item("REQ-001", dependencies=["REQ-002"]),
                    _item("REQ-002", dependencies=["REQ-001"]),
                    _item("REQ-003"),
                ]
            )
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_CIRCULAR_DEPENDENCY)

    def test_version_dependency_order_error(self) -> None:
        payload = _payload(
            items=[
                _item("REQ-001", version_id="V2", dependencies=["REQ-002"]),
                _item("REQ-002", version_id="V3"),
                _item("REQ-003", version_id="V2"),
            ]
        )
        payload["versions"] = [
            {
                "version_id": "V2",
                "name": "Subscription and workout improvements",
                "goal": "Improve subscription and workout experience.",
                "requirement_ids": ["REQ-001", "REQ-003"],
                "rationale": "Non-empty V2.",
                "risks": [],
                "success_metrics": [],
            },
            {
                "version_id": "V3",
                "name": "Subscription dependency later",
                "goal": "Improve subscription dependency after dependent work.",
                "requirement_ids": ["REQ-002"],
                "rationale": "Non-empty V3.",
                "risks": [],
                "success_metrics": [],
            },
        ]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_VERSION_ORDER_INVALID)

    def test_multi_requirement_one_version(self) -> None:
        result = _validate(_payload())

        self.assertTrue(result.passed)
        self.assertEqual(result.versions[0].requirement_ids, ["REQ-001", "REQ-002"])

    def test_one_requirement_multiple_versions_is_rejected(self) -> None:
        payload = _payload(items=[_item("REQ-001", version_id="V1"), _item("REQ-001", version_id="V2"), _item("REQ-002"), _item("REQ-003")])
        payload["versions"][0]["requirement_ids"] = ["REQ-001", "REQ-002"]
        payload["versions"][1]["requirement_ids"] = ["REQ-001", "REQ-003"]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_DUPLICATE_REQUIREMENT_ID)

    def test_empty_roadmap_with_no_requirements(self) -> None:
        result = validate_roadmap_output(
            json.dumps({"versions": [], "roadmap_items": [], "deferred_requirement_ids": [], "deferred_rationale": {}}),
            requirements_by_id={},
            requirement_validation_passed=True,
            priority_by_requirement_id={},
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_version_requirement_mismatch(self) -> None:
        payload = _payload()
        payload["versions"][0]["requirement_ids"] = ["REQ-001"]
        result = _validate(payload, enforce_product_quality=False)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_VERSION_REQUIREMENT_MISMATCH)

    def test_empty_version(self) -> None:
        payload = _payload()
        payload["versions"].append(
            {
                "version_id": "V3",
                "name": "Empty version",
                "goal": "No assigned work.",
                "requirement_ids": [],
                "rationale": "No assigned work.",
                "risks": [],
                "success_metrics": [],
            }
        )
        result = _validate(payload, enforce_product_quality=False)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_EMPTY_VERSION)

    def test_version_goal_incoherence(self) -> None:
        payload = _payload()
        payload["versions"][0]["name"] = "Highest priority product corrections"
        payload["versions"][0]["goal"] = "Address highest-priority items first."
        payload["versions"][0]["rationale"] = "Priority bucket."
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_VERSION_GOAL_INCOHERENCE)

    def test_existing_dependency_cannot_change(self) -> None:
        payload = _payload(items=[_item("REQ-001"), _item("REQ-002", dependencies=["REQ-001"]), _item("REQ-003", version_id="V2")])
        result = _validate(
            payload,
            existing_dependencies_by_requirement_id={"REQ-001": [], "REQ-002": [], "REQ-003": []},
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_DEPENDENCY_CHANGED)

    def test_empty_name_fails_schema(self) -> None:
        payload = _payload()
        payload["versions"][0]["name"] = ""
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)


def _validate(
    payload: dict,
    *,
    requirement_validation_passed: bool = True,
    enforce_product_quality: bool = True,
    existing_dependencies_by_requirement_id: dict[str, list[str]] | None = None,
):
    return _validate_raw(
        json.dumps(payload),
        requirement_validation_passed=requirement_validation_passed,
        enforce_product_quality=enforce_product_quality,
        existing_dependencies_by_requirement_id=existing_dependencies_by_requirement_id,
    )


def _validate_raw(
    raw_text: str,
    *,
    requirement_validation_passed: bool = True,
    enforce_product_quality: bool = True,
    existing_dependencies_by_requirement_id: dict[str, list[str]] | None = None,
):
    return validate_roadmap_output(
        raw_text,
        requirements_by_id=_requirements_by_id(),
        requirement_validation_passed=requirement_validation_passed,
        priority_by_requirement_id={"REQ-001": "P1", "REQ-002": "P1", "REQ-003": "P2"},
        enforce_product_quality=enforce_product_quality,
        existing_dependencies_by_requirement_id=existing_dependencies_by_requirement_id,
    )


def _payload(items: list[dict] | None = None) -> dict:
    items = items or [_item("REQ-001"), _item("REQ-002"), _item("REQ-003", version_id="V2")]
    versions = _versions()
    versions[0]["requirement_ids"] = [item["requirement_id"] for item in items if item["version_id"] == "V1"]
    versions[1]["requirement_ids"] = [item["requirement_id"] for item in items if item["version_id"] == "V2"]
    return {
        "versions": [version for version in versions if version["requirement_ids"]],
        "roadmap_items": items,
        "deferred_requirement_ids": [],
        "deferred_rationale": {},
    }


def _versions(*, empty: bool = False) -> list[dict]:
    return [
        {
            "version_id": "V1",
            "name": "Subscription access and billing clarity",
            "goal": "Improve subscription pricing, access, and billing transparency.",
            "requirement_ids": [] if empty else ["REQ-001", "REQ-002"],
            "rationale": "These requirements share the subscription and billing product goal.",
            "risks": [],
            "success_metrics": [],
        },
        {
            "version_id": "V2",
            "name": "Workout content quality",
            "goal": "Improve workout content quality and relevance.",
            "requirement_ids": [] if empty else ["REQ-003"],
            "rationale": "This version focuses on workout experience improvements.",
            "risks": [],
            "success_metrics": [],
        },
    ]


def _item(requirement_id: str, *, version_id: str = "V1", priority: str | None = None, dependencies: list[str] | None = None) -> dict:
    priority = priority or {"REQ-001": "P1", "REQ-002": "P1", "REQ-003": "P2"}.get(requirement_id, "P1")
    return {
        "requirement_id": requirement_id,
        "version_id": version_id,
        "priority": priority,
        "rationale": "Validated roadmap assignment.",
        "dependencies": dependencies or [],
    }


def _requirements_by_id() -> dict[str, dict]:
    return {
        "REQ-001": {"requirement_id": "REQ-001", "priority": "P1", "title": "Clarify subscription pricing"},
        "REQ-002": {"requirement_id": "REQ-002", "priority": "P1", "title": "Simplify subscription cancellation"},
        "REQ-003": {"requirement_id": "REQ-003", "priority": "P2", "title": "Improve workout content"},
    }


if __name__ == "__main__":
    unittest.main()
