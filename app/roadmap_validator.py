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
STATUS_EMPTY_VERSION = "Empty Version"
STATUS_DEFERRED_REASON_MISSING = "Deferred Reason Missing"
STATUS_VERSION_GOAL_INCOHERENCE = "Version Goal Incoherence"
STATUS_DEPENDENCY_CHANGED = "Dependency Changed"

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
    empty_version_ids: list[str] = field(default_factory=list)
    deferred_reason_errors: list[str] = field(default_factory=list)
    deferred_rationale: dict[str, str] = field(default_factory=dict)
    version_goal_errors: list[str] = field(default_factory=list)

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
    enforce_product_quality: bool = True,
    existing_dependencies_by_requirement_id: dict[str, list[str]] | None = None,
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
        enforce_product_quality=enforce_product_quality,
        existing_dependencies_by_requirement_id=existing_dependencies_by_requirement_id,
    )


def validate_roadmap_payload(
    payload: Any,
    *,
    requirements_by_id: dict[str, dict[str, Any]],
    priority_by_requirement_id: dict[str, str],
    enforce_product_quality: bool = True,
    existing_dependencies_by_requirement_id: dict[str, list[str]] | None = None,
) -> RoadmapValidationResult:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: root must be an object"])
    raw_versions = payload.get("versions")
    raw_items = payload.get("roadmap_items")
    raw_deferred_ids = payload.get("deferred_requirement_ids", [])
    raw_deferred_rationale = payload.get("deferred_rationale", {})
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
    deferred_ids = _text_list(raw_deferred_ids, "deferred_requirement_ids", errors)
    if not isinstance(raw_deferred_rationale, dict):
        errors.append("deferred_rationale: must be an object")
        deferred_rationale: dict[str, str] = {}
    else:
        deferred_rationale = {
            _text(key): _text(value)
            for key, value in raw_deferred_rationale.items()
            if _text(key)
        }
        for key, value in deferred_rationale.items():
            if not value:
                errors.append(f"deferred_rationale.{key}: required")
    if errors:
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, errors)

    unknown_requirement_ids: set[str] = set()
    unknown_version_ids: set[str] = set()
    duplicate_requirement_ids: set[str] = set()
    unassigned_requirement_ids: set[str] = set()
    priority_mismatches: list[str] = []
    dependency_errors: list[str] = []
    dependency_change_errors: list[str] = []
    version_requirement_mismatches: list[str] = []
    deferred_reason_errors: list[str] = []

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
        has_existing_dependency_record = (
            existing_dependencies_by_requirement_id is not None
            and requirement_id in existing_dependencies_by_requirement_id
        )
        existing_dependencies = sorted((existing_dependencies_by_requirement_id or {}).get(requirement_id, []))
        if has_existing_dependency_record and sorted(item["dependencies"]) != existing_dependencies:
            dependency_change_errors.append(
                f"{requirement_id}: dependencies changed from {existing_dependencies} to {sorted(item['dependencies'])}"
            )

    deferred_item_ids = [
        item["requirement_id"]
        for item in roadmap_items
        if item["version_id"] == "Deferred"
    ]
    all_deferred_ids = sorted(set(deferred_ids + deferred_item_ids))
    for requirement_id in all_deferred_ids:
        assigned_requirements.add(requirement_id)
        if requirement_id not in requirements_by_id:
            unknown_requirement_ids.add(requirement_id)
        if not deferred_rationale.get(requirement_id):
            deferred_reason_errors.append(f"{requirement_id}: deferred_rationale is required")

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
    empty_version_ids = [version.version_id for version in versions if version.version_id != "Deferred" and not version.requirement_ids]
    goal_errors = _version_goal_errors(versions, requirements_by_id) if enforce_product_quality else []

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
    if deferred_reason_errors:
        return _fail(
            STATUS_DEFERRED_REASON_MISSING,
            deferred_reason_errors,
            deferred_reason_errors=deferred_reason_errors,
        )
    if priority_mismatches:
        return _fail(STATUS_PRIORITY_MISMATCH, priority_mismatches, priority_mismatches=priority_mismatches)
    if dependency_change_errors:
        return _fail(
            STATUS_DEPENDENCY_CHANGED,
            dependency_change_errors,
            dependency_errors=dependency_change_errors,
        )
    if any("cannot depend on itself" in error for error in dependency_errors):
        return _fail(STATUS_SELF_DEPENDENCY, dependency_errors, dependency_errors=dependency_errors)

    cycle_errors = _cycle_errors(roadmap_items)
    if cycle_errors:
        return _fail(STATUS_CIRCULAR_DEPENDENCY, cycle_errors, dependency_errors=cycle_errors)

    order_errors = _version_order_errors(roadmap_items)
    if order_errors:
        return _fail(STATUS_VERSION_ORDER_INVALID, order_errors, dependency_errors=order_errors)

    if empty_version_ids:
        return _fail(
            STATUS_EMPTY_VERSION,
            [f"empty version {version_id}" for version_id in empty_version_ids],
            empty_version_ids=empty_version_ids,
        )
    if goal_errors:
        return _fail(
            STATUS_VERSION_GOAL_INCOHERENCE,
            goal_errors,
            version_goal_errors=goal_errors,
        )

    if version_requirement_mismatches:
        return _fail(
            STATUS_VERSION_REQUIREMENT_MISMATCH,
            version_requirement_mismatches,
            version_requirement_mismatches=version_requirement_mismatches,
        )

    deferred = sorted(set(all_deferred_ids))
    return RoadmapValidationResult(
        status=STATUS_SUCCESS,
        passed=True,
        versions=versions,
        roadmap_items=roadmap_items,
        deferred_requirement_ids=deferred,
        deferred_rationale={
            requirement_id: deferred_rationale[requirement_id]
            for requirement_id in deferred
            if requirement_id in deferred_rationale
        },
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


def _version_goal_errors(versions: list[Version], requirements_by_id: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    generic_terms = {
        "highest-priority",
        "highest priority",
        "lower roadmap urgency",
        "remaining validated",
        "priority product corrections",
        "reserved",
    }
    domain_terms = {
        "subscription": {"subscription", "billing", "paywall", "free", "premium", "cancellation"},
        "content": {"workout", "content", "imagery", "customization", "freshness", "library"},
        "operations": {"support", "ads", "redirects", "account"},
    }
    for version in versions:
        if version.version_id == "Deferred" or not version.requirement_ids:
            continue
        goal_text = f"{version.name} {version.goal} {version.rationale}".lower()
        if any(term in goal_text for term in generic_terms):
            errors.append(f"{version.version_id}: version goal is too priority-bucket oriented")
            continue
        requirement_text = " ".join(
            f"{requirements_by_id.get(requirement_id, {}).get('title', '')} "
            f"{requirements_by_id.get(requirement_id, {}).get('description', '')}"
            for requirement_id in version.requirement_ids
        ).lower()
        if not requirement_text:
            continue
        matched_domains = [
            domain
            for domain, terms in domain_terms.items()
            if any(term in requirement_text for term in terms)
        ]
        if len(version.requirement_ids) > 1 and len(matched_domains) > 1:
            if not any(term in goal_text for domain in matched_domains for term in domain_terms[domain]):
                errors.append(
                    f"{version.version_id}: mixed requirement domains are not explained by the version goal"
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
    empty_version_ids: list[str] | None = None,
    deferred_reason_errors: list[str] | None = None,
    deferred_rationale: dict[str, str] | None = None,
    version_goal_errors: list[str] | None = None,
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
        empty_version_ids=empty_version_ids or [],
        deferred_reason_errors=deferred_reason_errors or [],
        deferred_rationale=deferred_rationale or {},
        version_goal_errors=version_goal_errors or [],
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
