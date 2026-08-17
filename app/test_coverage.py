"""Deterministic coverage calculations for generated test cases."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TestCoverageReport:
    total_requirements: int
    covered_requirements: int
    requirement_coverage: float
    total_acceptance_criteria: int
    covered_acceptance_criteria: int
    acceptance_criteria_coverage: float
    uncovered_requirement_ids: list[str]
    uncovered_acceptance_criteria_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_test_coverage(
    *,
    requirements: list[dict[str, Any]],
    test_cases: list[dict[str, Any]],
) -> TestCoverageReport:
    requirement_ids = [
        requirement["requirement_id"]
        for requirement in requirements
        if isinstance(requirement, dict) and isinstance(requirement.get("requirement_id"), str)
    ]
    acceptance_criteria_ids = sorted(build_acceptance_criteria_index(requirements))
    covered_requirement_ids = {
        test_case.get("requirement_id")
        for test_case in test_cases
        if isinstance(test_case, dict) and isinstance(test_case.get("requirement_id"), str)
    }
    covered_acceptance_criteria_ids = {
        acceptance_criteria_id
        for test_case in test_cases
        if isinstance(test_case, dict)
        for acceptance_criteria_id in _list_text(test_case.get("acceptance_criteria_ids"))
    }
    valid_requirement_ids = set(requirement_ids)
    valid_acceptance_criteria_ids = set(acceptance_criteria_ids)
    covered_requirements = sorted(valid_requirement_ids.intersection(covered_requirement_ids))
    covered_acceptance_criteria = sorted(valid_acceptance_criteria_ids.intersection(covered_acceptance_criteria_ids))
    return TestCoverageReport(
        total_requirements=len(requirement_ids),
        covered_requirements=len(covered_requirements),
        requirement_coverage=_percentage(len(covered_requirements), len(requirement_ids)),
        total_acceptance_criteria=len(acceptance_criteria_ids),
        covered_acceptance_criteria=len(covered_acceptance_criteria),
        acceptance_criteria_coverage=_percentage(len(covered_acceptance_criteria), len(acceptance_criteria_ids)),
        uncovered_requirement_ids=sorted(valid_requirement_ids - set(covered_requirements)),
        uncovered_acceptance_criteria_ids=sorted(valid_acceptance_criteria_ids - set(covered_acceptance_criteria)),
    )


def build_acceptance_criteria_index(requirements: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        requirement_id = requirement.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id:
            continue
        acceptance_criteria = requirement.get("acceptance_criteria")
        if not isinstance(acceptance_criteria, list):
            continue
        for offset, criterion in enumerate(acceptance_criteria, start=1):
            if isinstance(criterion, str) and criterion.strip():
                acceptance_criteria_id = make_acceptance_criteria_id(requirement_id, offset)
                index[acceptance_criteria_id] = {
                    "acceptance_criteria_id": acceptance_criteria_id,
                    "requirement_id": requirement_id,
                    "index": offset,
                    "text": criterion.strip(),
                }
    return index


def make_acceptance_criteria_id(requirement_id: str, index: int) -> str:
    return f"{requirement_id}-AC-{index}"


def _percentage(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 100.0
    return round((numerator / denominator) * 100, 1)


def _list_text(value: Any) -> list[str]:
    return [item.strip() for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []
