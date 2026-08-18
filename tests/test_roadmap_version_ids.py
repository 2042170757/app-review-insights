import json
import unittest

from app.roadmap_planner import build_roadmap_request
from app.roadmap_validator import (
    ALLOWED_VERSION_IDS,
    STATUS_SCHEMA_VALIDATION_FAILED,
    STATUS_SUCCESS,
    validate_roadmap_output,
)


class RoadmapVersionIDTests(unittest.TestCase):
    def test_v1_is_valid(self) -> None:
        result = _validate(_payload([("REQ-001", "V1")]))

        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertTrue(result.passed)

    def test_v2_is_valid(self) -> None:
        result = _validate(_payload([("REQ-001", "V2")]))

        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertTrue(result.passed)

    def test_v3_is_valid(self) -> None:
        result = _validate(_payload([("REQ-001", "V3")]))

        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertTrue(result.passed)

    def test_deferred_is_allowed_only_through_deferred_fields(self) -> None:
        payload = _payload([("REQ-001", "V1")], deferred=["REQ-002"])
        result = _validate(payload)

        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(result.deferred_requirement_ids, ["REQ-002"])
        self.assertIn("Deferred", ALLOWED_VERSION_IDS)

    def test_v4_is_invalid(self) -> None:
        result = _validate(_payload([("REQ-001", "V4")]))

        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)
        self.assertIn("versions[0].version_id: invalid V4", result.errors)

    def test_v5_is_invalid(self) -> None:
        result = _validate(_payload([("REQ-001", "V5")]))

        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)
        self.assertIn("versions[0].version_id: invalid V5", result.errors)

    def test_arbitrary_version_is_invalid(self) -> None:
        result = _validate(_payload([("REQ-001", "Future")]))

        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)
        self.assertIn("versions[0].version_id: invalid Future", result.errors)

    def test_one_scheduled_version_is_valid(self) -> None:
        result = _validate(_payload([("REQ-001", "V1")]))

        self.assertTrue(result.passed)
        self.assertEqual([version.version_id for version in result.versions], ["V1"])

    def test_two_scheduled_versions_are_valid(self) -> None:
        result = _validate(_payload([("REQ-001", "V1"), ("REQ-002", "V2")]))

        self.assertTrue(result.passed)
        self.assertEqual([version.version_id for version in result.versions], ["V1", "V2"])

    def test_three_scheduled_versions_are_valid(self) -> None:
        result = _validate(_payload([("REQ-001", "V1"), ("REQ-002", "V2"), ("REQ-003", "V3")]))

        self.assertTrue(result.passed)
        self.assertEqual([version.version_id for version in result.versions], ["V1", "V2", "V3"])

    def test_scheduled_plus_deferred_is_valid(self) -> None:
        result = _validate(_payload([("REQ-001", "V1"), ("REQ-002", "V2")], deferred=["REQ-003"]))

        self.assertTrue(result.passed)
        self.assertEqual(result.deferred_requirement_ids, ["REQ-003"])

    def test_duplicate_version_id_is_invalid(self) -> None:
        payload = _payload([("REQ-001", "V1"), ("REQ-002", "V2")])
        payload["versions"].append(
            {
                "version_id": "V1",
                "name": "Duplicate version",
                "goal": "Duplicate goal.",
                "requirement_ids": ["REQ-003"],
                "rationale": "Duplicate version id should fail.",
                "risks": [],
                "success_metrics": [],
            }
        )
        payload["roadmap_items"].append(_item("REQ-003", "V1"))
        result = _validate(payload)

        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)
        self.assertIn("versions[2].version_id: duplicate V1", result.errors)

    def test_deferred_version_object_is_invalid(self) -> None:
        payload = _payload([("REQ-001", "V1")], deferred=["REQ-002"])
        payload["versions"].append(
            {
                "version_id": "Deferred",
                "name": "Deferred",
                "goal": "Deferred requirements are not scheduled.",
                "requirement_ids": ["REQ-002"],
                "rationale": "Deferred must be represented through deferred_requirement_ids.",
                "risks": [],
                "success_metrics": [],
            }
        )
        result = _validate(payload)

        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)
        self.assertIn(
            "versions[1].version_id: Deferred must be represented with deferred_requirement_ids, not versions[]",
            result.errors,
        )

    def test_prompt_contains_version_id_contract(self) -> None:
        request = build_roadmap_request(
            requirements=list(_requirements_by_id().values()),
            priority_report={"priority_report": [{"requirement_id": "REQ-001", "final_priority": "P1"}]},
            evidence_report={"evidence_reports": []},
            existing_dependencies_by_requirement_id={},
            analysis_goal="goal",
        )
        payload = json.loads(request.user_prompt)
        contract = payload["version_id_contract"]

        self.assertEqual(contract["scheduled_version_ids"], ["V1", "V2", "V3"])
        self.assertEqual(contract["max_scheduled_version_count"], 3)
        self.assertEqual(contract["deferred_version_id"], "Deferred")
        self.assertIn("V4", payload["version_id_contract"]["rules"][2])
        self.assertIn("at most 3 scheduled Versions", request.system_prompt)


def _validate(payload: dict):
    requirements_by_id = _requirements_for_payload(payload)
    return validate_roadmap_output(
        json.dumps(payload),
        requirements_by_id=requirements_by_id,
        requirement_validation_passed=True,
        priority_by_requirement_id={
            requirement_id: requirement["priority"]
            for requirement_id, requirement in requirements_by_id.items()
        },
        enforce_product_quality=False,
    )


def _payload(assignments: list[tuple[str, str]], *, deferred: list[str] | None = None) -> dict:
    deferred = deferred or []
    versions = []
    for version_id in _unique([version_id for _, version_id in assignments]):
        versions.append(
            {
                "version_id": version_id,
                "name": f"{version_id} product goal",
                "goal": f"Deliver {version_id} product goal.",
                "requirement_ids": [requirement_id for requirement_id, assigned_version in assignments if assigned_version == version_id],
                "rationale": f"{version_id} groups related requirements.",
                "risks": [],
                "success_metrics": [],
            }
        )
    return {
        "versions": versions,
        "roadmap_items": [_item(requirement_id, version_id) for requirement_id, version_id in assignments],
        "deferred_requirement_ids": deferred,
        "deferred_rationale": {requirement_id: "Deferred with explicit rationale." for requirement_id in deferred},
    }


def _item(requirement_id: str, version_id: str) -> dict:
    return {
        "requirement_id": requirement_id,
        "version_id": version_id,
        "priority": _requirements_by_id()[requirement_id]["priority"],
        "rationale": "Validated assignment.",
        "dependencies": [],
    }


def _requirements_by_id() -> dict[str, dict]:
    return {
        "REQ-001": {"requirement_id": "REQ-001", "priority": "P1", "title": "Requirement one"},
        "REQ-002": {"requirement_id": "REQ-002", "priority": "P2", "title": "Requirement two"},
        "REQ-003": {"requirement_id": "REQ-003", "priority": "P3", "title": "Requirement three"},
    }


def _requirements_for_payload(payload: dict) -> dict[str, dict]:
    requirement_ids = {
        item["requirement_id"]
        for item in payload.get("roadmap_items", [])
        if isinstance(item, dict) and isinstance(item.get("requirement_id"), str)
    }
    requirement_ids.update(
        item
        for item in payload.get("deferred_requirement_ids", [])
        if isinstance(item, str)
    )
    all_requirements = _requirements_by_id()
    return {
        requirement_id: all_requirements[requirement_id]
        for requirement_id in sorted(requirement_ids)
    }


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


if __name__ == "__main__":
    unittest.main()
