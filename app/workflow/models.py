"""Workflow state data structures and deterministic progress calculation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.analysis_intent import DEFAULT_ANALYSIS_FOCUS, normalize_analysis_focus
from app.workflow.stages import (
    ERROR_UNKNOWN,
    RUN_QUEUED,
    STATUS_COMPLETED,
    STATUS_PENDING,
    VALID_ERROR_TYPES,
    VALID_REVISION_STATUSES,
    VALID_RUN_STATUSES,
    VALID_STAGE_STATUSES,
    WORKFLOW_STAGES,
)


DEFAULT_ANALYSIS_GOAL = "分析用户评论中的主要产品问题、用户体验问题和改进机会。"


@dataclass
class WorkflowStageState:
    stage: str
    label_zh: str
    label_en: str
    order: int
    status: str = STATUS_PENDING
    message: str | None = None
    artifacts: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float | None = None
    started_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowError:
    stage: str | None
    type: str
    message: str
    recoverable: bool

    def __post_init__(self) -> None:
        if self.type not in VALID_ERROR_TYPES:
            self.type = ERROR_UNKNOWN
        self.message = redact_secret_text(self.message)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowWarning:
    stage: str | None
    type: str
    message: str

    def __post_init__(self) -> None:
        self.message = redact_secret_text(self.message)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowRevision:
    revision_id: str
    stage: str
    reason: str
    status: str

    def __post_init__(self) -> None:
        if self.status not in VALID_REVISION_STATUSES:
            raise ValueError(f"Invalid revision status: {self.status}")
        self.reason = redact_secret_text(self.reason)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AppStoreUrlValidation:
    valid: bool
    storefront: str | None = None
    app_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunState:
    run_id: str
    status: str
    current_stage: str | None
    progress: float
    app_url: str
    analysis_goal: str
    stages: list[WorkflowStageState]
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS
    errors: list[WorkflowError] = field(default_factory=list)
    warnings: list[WorkflowWarning] = field(default_factory=list)
    revisions: list[WorkflowRevision] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: now_utc())
    updated_at: str = field(default_factory=lambda: now_utc())
    is_mock: bool = True
    source_type: str = "app_store"
    data_source: str = "app_store"
    import_metadata: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    is_demo: bool = False
    demo_metadata: dict[str, Any] = field(default_factory=dict)
    storefront: str | None = None
    app_id: str | None = None
    total_elapsed_seconds: float | None = None
    runtime_validation_status: str = "pending"
    submission_validation_status: str = "pending"

    def __post_init__(self) -> None:
        if self.status not in VALID_RUN_STATUSES:
            raise ValueError(f"Invalid run status: {self.status}")
        for stage in self.stages:
            if stage.status not in VALID_STAGE_STATUSES:
                raise ValueError(f"Invalid stage status: {stage.status}")
        self.progress = calculate_progress(self.stages)
        self.analysis_goal = normalize_analysis_goal(self.analysis_goal)
        self.analysis_focus = normalize_analysis_focus(self.analysis_focus)

    def touch(self) -> None:
        self.updated_at = now_utc()
        self.progress = calculate_progress(self.stages)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["stages"] = [stage.to_dict() for stage in self.stages]
        payload["errors"] = [error.to_dict() for error in self.errors]
        payload["warnings"] = [warning.to_dict() for warning in self.warnings]
        payload["revisions"] = [revision.to_dict() for revision in self.revisions]
        return payload


def initialize_stage_states() -> list[WorkflowStageState]:
    return [
        WorkflowStageState(
            stage=definition.stage,
            label_zh=definition.label_zh,
            label_en=definition.label_en,
            order=definition.order,
        )
        for definition in WORKFLOW_STAGES
    ]


def calculate_progress(stages: list[WorkflowStageState]) -> float:
    if not stages:
        return 0.0
    completed = sum(1 for stage in stages if stage.status == STATUS_COMPLETED)
    return round((completed / len(stages)) * 100, 1)


def normalize_analysis_goal(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        return DEFAULT_ANALYSIS_GOAL
    return value.strip()


def new_run_state(
    *,
    run_id: str,
    app_url: str,
    analysis_goal: str | None,
    storefront: str,
    app_id: str,
    analysis_focus: str | None = DEFAULT_ANALYSIS_FOCUS,
    is_mock: bool = True,
    source_type: str = "app_store",
    data_source: str | None = None,
    import_metadata: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
    is_demo: bool = False,
    demo_metadata: dict[str, Any] | None = None,
) -> RunState:
    timestamp = now_utc()
    return RunState(
        run_id=run_id,
        status=RUN_QUEUED,
        current_stage=None,
        progress=0.0,
        app_url=app_url,
        analysis_goal=normalize_analysis_goal(analysis_goal),
        analysis_focus=normalize_analysis_focus(analysis_focus),
        stages=initialize_stage_states(),
        created_at=timestamp,
        updated_at=timestamp,
        is_mock=is_mock,
        source_type=source_type,
        data_source=data_source or source_type,
        import_metadata=dict(import_metadata or {}),
        constraints=dict(constraints or {}),
        is_demo=is_demo,
        demo_metadata=dict(demo_metadata or {}),
        storefront=storefront,
        app_id=app_id,
    )


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redact_secret_text(value: str) -> str:
    redacted = value
    secret_markers = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "APIFY_API_TOKEN", "APPSTORE_PRIVATE_KEY")
    for marker in secret_markers:
        redacted = redacted.replace(marker, f"{marker}=<redacted>")
    return redacted
