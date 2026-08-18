"""Static registry of semantic model usage and deterministic boundaries."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from app.requirement_generation import DEEPSEEK_REQUIREMENT_MAX_TOKENS, DEFAULT_REQUIREMENT_MAX_TOKENS


DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = "deepseek-v4-flash"


@dataclass(frozen=True)
class ModelTaskRegistration:
    task: str
    provider: str
    model: str
    configuration: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MODEL_DRIVEN_TASKS = [
    "Topic Discovery",
    "Issue Consolidation",
    "Finding Generation",
    "Requirement Generation",
    "Roadmap Planning",
    "PRD Generation",
    "Test Case Generation",
]

DETERMINISTIC_TASKS = [
    "Review Schema Validation",
    "Review Normalization",
    "Review Cleaning",
    "Language Detection",
    "Exact Deduplication",
    "Near Duplicate Candidate Marking",
    "Statistics",
    "Issue Type Classification",
    "Finding Eligibility Gate",
    "Priority Scoring",
    "Schema Validation",
    "Evidence ID Validation",
    "Coverage Calculation",
    "Traceability Validation",
    "Final Consistency Validation",
]

FAILURE_STATES = [
    "Missing API Key",
    "Authentication Error",
    "Timeout",
    "Rate Limit",
    "Invalid JSON",
    "Validation Failed",
    "SKIPPED",
    "Empty Dataset",
    "Evidence Insufficient",
]


def build_model_registry(
    *,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
) -> list[ModelTaskRegistration]:
    default_configuration = {
        "thinking": {"type": "disabled"},
        "max_tokens": 3000,
        "temperature": 0.2,
        "stream": False,
        "timeout_seconds": 60,
        "response_format": {"type": "json_object"},
    }
    registrations: list[ModelTaskRegistration] = []
    for task in MODEL_DRIVEN_TASKS:
        configuration = dict(default_configuration)
        if task == "Requirement Generation":
            configuration["max_tokens"] = _requirement_max_tokens()
            configuration["default_max_tokens"] = default_configuration["max_tokens"]
        registrations.append(
            ModelTaskRegistration(
                task=task,
                provider=provider,
                model=model,
                configuration=configuration,
            )
        )
    return registrations


def _requirement_max_tokens() -> int:
    raw_value = os.environ.get(DEEPSEEK_REQUIREMENT_MAX_TOKENS)
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_REQUIREMENT_MAX_TOKENS
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_REQUIREMENT_MAX_TOKENS
    return value if value > 0 else DEFAULT_REQUIREMENT_MAX_TOKENS


def audit_ai_deterministic_boundary() -> dict[str, Any]:
    model_tasks = set(MODEL_DRIVEN_TASKS)
    deterministic_tasks = set(DETERMINISTIC_TASKS)
    overlap = sorted(model_tasks.intersection(deterministic_tasks))
    missing_semantic_tasks = [
        task
        for task in MODEL_DRIVEN_TASKS
        if task not in model_tasks
    ]
    return {
        "status": "PASS" if not overlap and not missing_semantic_tasks else "FAIL",
        "deterministic_tasks": DETERMINISTIC_TASKS,
        "model_driven_tasks": MODEL_DRIVEN_TASKS,
        "overlap": overlap,
        "missing_semantic_tasks": missing_semantic_tasks,
    }


def audit_failure_state_registry() -> dict[str, Any]:
    required = {
        "Missing API Key",
        "Authentication Error",
        "Timeout",
        "Rate Limit",
        "Invalid JSON",
        "Validation Failed",
        "SKIPPED",
        "Empty Dataset",
        "Evidence Insufficient",
    }
    present = set(FAILURE_STATES)
    missing = sorted(required - present)
    return {
        "status": "PASS" if not missing else "FAIL",
        "failure_states": FAILURE_STATES,
        "missing": missing,
        "skipped_semantics": "Precondition/provider failures skip downstream validation instead of marking it failed.",
    }
