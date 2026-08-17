"""Deterministic validation for roadmap and version planning output."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from app.requirement_schema import VALID_PRIORITIES
from app.version_schema import VALID_VERSION_IDS, Version


STATUS_SUCCESS = "Success"
STATUS_INVALID_JSON = "Invalid JSON"
STATUS_SCHEMA_VALIDATION_FAILED = "Schema Validation Failed"
STATUS_REQUIREMENT_VALIDATION_FAILED = "Requirement Validation Failed"
STATUS_UNKNOWN_REQUIREMENT_ID = "Unknown Requirement ID"
STATUS_UNKNOWN_VERSION_ID = "Unknown Version ID"
STATUS_DUPLICATE_REQUIREMENT_ID = "Duplicate Requirement ID"
STATUS_UNASSIGNED_REQUIREMENT = "Unassigned Requirement"
STATUS_PRIORITY_MISMATCH = "Priority Mismatch"
STATUS_SELF_DEPENDENCY = "Self Dependency"
STATUS_CIRCULAR_DEPENDENCY = "Circular Dependency"
STATUS_VERSION_ORDER_INVALID = "Version Order Invalid"
STATUS_VERSION_REQUIREMENT_MISMATCH = "Version Requirement Mismatch"

VERSION_ORDER = {"V1": 1, "V2": 2, "V3": 3, "Deferred": 4}


@dataclass
class RoadmapValidationResult:
    status: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    versions: list[Version] = field(default_factory=list)
    roadmap_items: list[dict[str, Any]] = field(default_factory=list)
    deferred_requirement_ids: list[str] = field(default_factory=list)
    unknown_requirement_ids: list[str] = field(default_factory=list)
    unknown_version_ids: list[str] = field(default_factory=list)
    duplicate_requirement_ids: list[str] = field(default_factory=list)
    unassigned_requirement_ids: list[str] = field(default_factory=list)
    priority_mismatches: list[str] = field(default_factory=list)
    dependency_errors: list[str] = field(default_factory=list)
    version_requirement_mismatches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["versions"] = [asdict(version) for version in self.versions]
        return payload


def validate_roadmap_output(
    raw_text: str,
    *,
    requirements_by_id: dict[str, dict[str, Any]],
    requirement_validation_passed: bool,
    priority_by_requirement_id: dict[str, str],
) -> RoadmapValidationResult:
    if not requirement_validation_passed:
        return RoadmapValidationResult(
            status=STATUS_REQUIREMENT_VALIDATION_FAILED,
            passed=False,
            errors=["requirement validation is not PASS"],
        )
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return RoadmapValidationResult(
            status=STATUS_INVALID_JSON,
            passed=False,
            errors=[f"Invalid JSON: {exc.msg}"],
        )
    return validate_roadmap_payload(
        payload,
        requirements_by_id=requirements_by_id,
        priority_by_requirement_id=priority_by_requirement_id,
    )


def validate_roadmap_payload(
    payload: Any,
    *,
    requirements_by_id: dict[str, dict[str, Any]],
    priority_by_requirement_id: dict[str, str],
) -> RoadmapValidationResult:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: root must be an object"])
    raw_versions = payload.get("versions")
    raw_items = payload.get("roadmap_items")
    if not isinstance(raw_versions, list):
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: versions must be a list"])
    if not isinstance(raw_items, list):
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: roadmap_items must be a list"])

    versions, version_errors = _parse_versions(raw_versions)
    errors.extend(version_errors)
    if errors:
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, errors)

    version_ids = {version.version_id for version in versions}
    roadmap_items, item_errors = _parse_roadmap_items(raw_items)
    errors.extend(item_errors)
    if errors:
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, errors)

    unknown_requirement_ids: set[str] = set()
    unknown_version_ids: set[str] = set()
    duplicate_requirement_ids: set[str] = set()
    unassigned_requirement_ids: set[str] = set()
    priority_mismatches: list[str] = []
    dependency_errors: list[str] = []
    version_requirement_mismatches: list[str] = []

    seen_requirements: set[str] = set()
    assigned_requirements: set[str] = set()
    item_by_requirement: dict[str, dict[str, Any]] = {}
    for item in roadmap_items:
        requirement_id = item["requirement_id"]
        if requirement_id in seen_requirements:
            duplicate_requirement_ids.add(requirement_id)
        seen_requirements.add(requirement_id)
        assigned_requirements.add(requirement_id)
        item_by_requirement[requirement_id] = item
        if requirement_id not in requirements_by_id:
            unknown_requirement_ids.add(requirement_id)
        if item["version_id"] not in version_ids:
            unknown_version_ids.add(item["version_id"])
        expected_priority = _requirement_priority(requirement_id, requirements_by_id, priority_by_requirement_id)
        if expected_priority and item["priority"] != expected_priority:
            priority_mismatches.append(
                f"{requirement_id}: roadmap priority {item['priority']} != requirement priority {expected_priority}"
            )
        for dependency_id in item["dependencies"]:
            if dependency_id not in requirements_by_id:
                unknown_requirement_ids.add(dependency_id)
                dependency_errors.append(f"{requirement_id}: unknown dependency {dependency_id}")
            if dependency_id == requirement_id:
                dependency_errors.append(f"{requirement_id}: cannot depend on itself")

    for requirement_id in requirements_by_id:
        if requirement_id not in assigned_requirements:
            unassigned_requirement_ids.add(requirement_id)

    version_requirement_ids = _version_requirement_ids(versions)
    roadmap_requirement_ids = {item["requirement_id"] for item in roadmap_items}
    if version_requirement_ids != roadmap_requirement_ids:
        missing_in_versions = sorted(roadmap_requirement_ids - version_requirement_ids)
        missing_in_roadmap = sorted(version_requirement_ids - roadmap_requirement_ids)
        if missing_in_versions:
            version_requirement_mismatches.append(
                f"roadmap item requirements missing from versions: {missing_in_versions}"
            )
        if missing_in_roadmap:
            version_requirement_mismatches.append(
                f"version requirements missing from roadmap_items: {missing_in_roadmap}"
            )

    if duplicate_requirement_ids:
        return _fail(
            STATUS_DUPLICATE_REQUIREMENT_ID,
            [f"duplicate requirement id {item}" for item in sorted(duplicate_requirement_ids)],
            duplicate_requirement_ids=sorted(duplicate_requirement_ids),
        )
    if unknown_requirement_ids:
        return _fail(
            STATUS_UNKNOWN_REQUIREMENT_ID,
            [f"unknown requirement id {item}" for item in sorted(unknown_requirement_ids)],
            unknown_requirement_ids=sorted(unknown_requirement_ids),
            dependency_errors=dependency_errors,
        )
    if unknown_version_ids:
        return _fail(
            STATUS_UNKNOWN_VERSION_ID,
            [f"unknown version id {item}" for item in sorted(unknown_version_ids)],
            unknown_version_ids=sorted(unknown_version_ids),
        )
    if unassigned_requirement_ids:
        return _fail(
            STATUS_UNASSIGNED_REQUIREMENT,
            [f"unassigned requirement id {item}" for item in sorted(unassigned_requirement_ids)],
            unassigned_requirement_ids=sorted(unassigned_requirement_ids),
        )
    if priority_mismatches:
        return _fail(STATUS_PRIORITY_MISMATCH, priority_mismatches, priority_mismatches=priority_mismatches)
    if any("cannot depend on itself" in error for error in dependency_errors):
        return _fail(STATUS_SELF_DEPENDENCY, dependency_errors, dependency_errors=dependency_errors)

    cycle_errors = _cycle_errors(roadmap_items)
    if cycle_errors:
        return _fail(STATUS_CIRCULAR_DEPENDENCY, cycle_errors, dependency_errors=cycle_errors)

    order_errors = _version_order_errors(roadmap_items)
    if order_errors:
        return _fail(STATUS_VERSION_ORDER_INVALID, order_errors, dependency_errors=order_errors)

    if version_requirement_mismatches:
        return _fail(
            STATUS_VERSION_REQUIREMENT_MISMATCH,
            version_requirement_mismatches,
            version_requirement_mismatches=version_requirement_mismatches,
        )

    deferred = sorted(item["requirement_id"] for item in roadmap_items if item["version_id"] == "Deferred")
    return RoadmapValidationResult(
        status=STATUS_SUCCESS,
        passed=True,
        versions=versions,
        roadmap_items=roadmap_items,
        deferred_requirement_ids=deferred,
    )


def _parse_versions(raw_versions: list[Any]) -> tuple[list[Version], list[str]]:
    versions: list[Version] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, raw_version in enumerate(raw_versions):
        prefix = f"versions[{index}]"
        if not isinstance(raw_version, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        version_id = _text(raw_version.get("version_id"))
        name = _text(raw_version.get("name"))
        goal = _text(raw_version.get("goal"))
        requirement_ids = _text_list(raw_version.get("requirement_ids"), f"{prefix}.requirement_ids", errors)
        rationale = _text(raw_version.get("rationale"))
        risks = _text_list(raw_version.get("risks"), f"{prefix}.risks", errors)
        success_metrics = _text_list(raw_version.get("success_metrics"), f"{prefix}.success_metrics", errors)
        if not version_id:
            errors.append(f"{prefix}.version_id: required")
        elif version_id in seen:
            errors.append(f"{prefix}.version_id: duplicate {version_id}")
        elif version_id not in VALID_VERSION_IDS:
            errors.append(f"{prefix}.version_id: invalid {version_id}")
        else:
            seen.add(version_id)
        if not name:
            errors.append(f"{prefix}.name: required")
        if not goal:
            errors.append(f"{prefix}.goal: required")
        if not rationale:
            errors.append(f"{prefix}.rationale: required")
        versions.append(
            Version(
                version_id=version_id,
                name=name,
                goal=goal,
                requirement_ids=requirement_ids,
                rationale=rationale,
                risks=risks,
                success_metrics=success_metrics,
            )
        )
    return versions, errors


def _parse_roadmap_items(raw_items: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, raw_item in enumerate(raw_items):
        prefix = f"roadmap_items[{index}]"
        if not isinstance(raw_item, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        requirement_id = _text(raw_item.get("requirement_id"))
        version_id = _text(raw_item.get("version_id"))
        priority = _text(raw_item.get("priority"))
        rationale = _text(raw_item.get("rationale"))
        dependencies = _text_list(raw_item.get("dependencies"), f"{prefix}.dependencies", errors)
        if not requirement_id:
            errors.append(f"{prefix}.requirement_id: required")
        if not version_id:
            errors.append(f"{prefix}.version_id: required")
        if priority not in VALID_PRIORITIES:
            errors.append(f"{prefix}.priority: invalid {priority!r}")
        if not rationale:
            errors.append(f"{prefix}.rationale: required")
        items.append(
            {
                "requirement_id": requirement_id,
                "version_id": version_id,
                "priority": priority,
                "rationale": rationale,
                "dependencies": dependencies,
            }
        )
    return items, errors


def _requirement_priority(
    requirement_id: str,
    requirements_by_id: dict[str, dict[str, Any]],
    priority_by_requirement_id: dict[str, str],
) -> str:
    return priority_by_requirement_id.get(requirement_id) or _text(requirements_by_id.get(requirement_id, {}).get("priority"))


def _version_requirement_ids(versions: list[Version]) -> set[str]:
    result: set[str] = set()
    for version in versions:
        result.update(version.requirement_ids)
    return result


def _cycle_errors(roadmap_items: list[dict[str, Any]]) -> list[str]:
    graph = {item["requirement_id"]: list(item["dependencies"]) for item in roadmap_items}
    visiting: set[str] = set()
    visited: set[str] = set()
    errors: list[str] = []

    def visit(node: str, path: list[str]) -> None:
        if node in visiting:
            cycle_start = path.index(node) if node in path else 0
            errors.append(f"circular dependency: {' -> '.join(path[cycle_start:] + [node])}")
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, []):
            if dependency in graph:
                visit(dependency, path + [dependency])
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node, [node])
    return errors


def _version_order_errors(roadmap_items: list[dict[str, Any]]) -> list[str]:
    item_by_requirement = {item["requirement_id"]: item for item in roadmap_items}
    errors: list[str] = []
    for item in roadmap_items:
        current_order = VERSION_ORDER[item["version_id"]]
        for dependency_id in item["dependencies"]:
            dependency_item = item_by_requirement.get(dependency_id)
            if not dependency_item:
                continue
            dependency_order = VERSION_ORDER[dependency_item["version_id"]]
            if dependency_order > current_order:
                errors.append(
                    f"{item['requirement_id']}: dependency {dependency_id} is scheduled later "
                    f"({dependency_item['version_id']} > {item['version_id']})"
                )
    return errors


def _fail(
    status: str,
    errors: list[str],
    *,
    unknown_requirement_ids: list[str] | None = None,
    unknown_version_ids: list[str] | None = None,
    duplicate_requirement_ids: list[str] | None = None,
    unassigned_requirement_ids: list[str] | None = None,
    priority_mismatches: list[str] | None = None,
    dependency_errors: list[str] | None = None,
    version_requirement_mismatches: list[str] | None = None,
) -> RoadmapValidationResult:
    return RoadmapValidationResult(
        status=status,
        passed=False,
        errors=errors,
        unknown_requirement_ids=unknown_requirement_ids or [],
        unknown_version_ids=unknown_version_ids or [],
        duplicate_requirement_ids=duplicate_requirement_ids or [],
        unassigned_requirement_ids=unassigned_requirement_ids or [],
        priority_mismatches=priority_mismatches or [],
        dependency_errors=dependency_errors or [],
        version_requirement_mismatches=version_requirement_mismatches or [],
    )


def _text_list(value: Any, field_name: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{field_name}: must be a list")
        return []
    normalized = [_text(item) for item in value]
    for item in normalized:
        if not item:
            errors.append(f"{field_name}: empty item")
    return normalized


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
