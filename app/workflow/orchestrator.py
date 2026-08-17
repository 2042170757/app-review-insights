"""In-memory workflow orchestration for Phase 9a UI shell."""

from __future__ import annotations

from urllib.parse import urlparse
from uuid import uuid4

from app.url_resolver import AppStoreUrlError, parse_app_store_url
from app.workflow.models import (
    AppStoreUrlValidation,
    RunState,
    WorkflowError,
    WorkflowRevision,
    WorkflowWarning,
    new_run_state,
    now_utc,
    normalize_analysis_goal,
)
from app.workflow.stages import (
    ERROR_INPUT,
    ERROR_UNKNOWN,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_RUNNING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    VALID_ERROR_TYPES,
    WORKFLOW_STAGE_IDS,
)


class WorkflowInputError(ValueError):
    """Raised when workflow input cannot create a valid run."""


class WorkflowRunNotFound(KeyError):
    """Raised when a run id does not exist in the in-memory store."""


class WorkflowStateError(ValueError):
    """Raised when a workflow state transition is invalid."""


class WorkflowOrchestrator:
    """Small in-memory orchestrator for UI workflow state.

    Phase 9a intentionally does not execute the full analysis pipeline. It creates
    real run state and stage records that future phases can connect to the
    existing backend modules.
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}

    def create_run(self, *, app_url: str, analysis_goal: str | None = None) -> RunState:
        validation = validate_app_store_url(app_url)
        if not validation.valid:
            raise WorkflowInputError(validation.error or "Invalid App Store URL")
        run = new_run_state(
            run_id=str(uuid4()),
            app_url=app_url.strip(),
            analysis_goal=normalize_analysis_goal(analysis_goal),
            storefront=validation.storefront or "",
            app_id=validation.app_id or "",
            is_mock=True,
        )
        self._runs[run.run_id] = run
        return run

    def get_run(self, run_id: str) -> RunState:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise WorkflowRunNotFound(run_id) from exc

    def list_stages(self, run_id: str) -> list[dict[str, object]]:
        return [stage.to_dict() for stage in self.get_run(run_id).stages]

    def start_run(self, run_id: str) -> RunState:
        run = self.get_run(run_id)
        if run.status == RUN_FAILED:
            raise WorkflowStateError("Cannot start a failed run")
        run.status = RUN_RUNNING
        run.touch()
        return run

    def mark_stage_running(self, run_id: str, stage_id: str) -> RunState:
        run = self.start_run(run_id)
        stage = _find_stage(run, stage_id)
        if stage.status not in {STATUS_PENDING, STATUS_RUNNING}:
            raise WorkflowStateError(f"Cannot run stage {stage_id} from status {stage.status}")
        stage.status = STATUS_RUNNING
        stage.started_at = stage.started_at or now_utc()
        run.current_stage = stage_id
        run.touch()
        return run

    def mark_stage_completed(self, run_id: str, stage_id: str) -> RunState:
        run = self.get_run(run_id)
        stage = _find_stage(run, stage_id)
        if stage.status == STATUS_SKIPPED:
            raise WorkflowStateError(f"Cannot complete skipped stage {stage_id}")
        stage.status = STATUS_COMPLETED
        stage.started_at = stage.started_at or now_utc()
        stage.completed_at = now_utc()
        if all(item.status == STATUS_COMPLETED for item in run.stages):
            run.status = RUN_COMPLETED
            run.current_stage = None
        else:
            run.status = RUN_RUNNING
            run.current_stage = _next_pending_stage(run)
        run.touch()
        return run

    def mark_stage_failed(
        self,
        run_id: str,
        stage_id: str,
        *,
        error_type: str = ERROR_UNKNOWN,
        message: str,
        recoverable: bool = True,
    ) -> RunState:
        run = self.get_run(run_id)
        stage = _find_stage(run, stage_id)
        stage.status = STATUS_FAILED
        stage.started_at = stage.started_at or now_utc()
        stage.completed_at = now_utc()
        run.status = RUN_FAILED
        run.current_stage = stage_id
        run.errors.append(
            WorkflowError(
                stage=stage_id,
                type=error_type if error_type in VALID_ERROR_TYPES else ERROR_UNKNOWN,
                message=message,
                recoverable=recoverable,
            )
        )
        _skip_stages_after(run, stage_id)
        run.touch()
        return run

    def add_error(
        self,
        run_id: str,
        *,
        stage: str | None,
        error_type: str,
        message: str,
        recoverable: bool,
    ) -> RunState:
        run = self.get_run(run_id)
        run.errors.append(
            WorkflowError(stage=stage, type=error_type, message=message, recoverable=recoverable)
        )
        run.touch()
        return run

    def add_warning(self, run_id: str, *, stage: str | None, warning_type: str, message: str) -> RunState:
        run = self.get_run(run_id)
        run.warnings.append(WorkflowWarning(stage=stage, type=warning_type, message=message))
        run.touch()
        return run

    def add_revision(self, run_id: str, *, stage: str, reason: str, status: str) -> RunState:
        run = self.get_run(run_id)
        run.revisions.append(
            WorkflowRevision(
                revision_id=str(uuid4()),
                stage=stage,
                reason=reason,
                status=status,
            )
        )
        run.touch()
        return run


def validate_app_store_url(url: str) -> AppStoreUrlValidation:
    if not isinstance(url, str) or not url.strip():
        return AppStoreUrlValidation(valid=False, error="Invalid App Store URL")
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        return AppStoreUrlValidation(valid=False, error="Invalid App Store URL")
    try:
        app_ref = parse_app_store_url(url)
    except AppStoreUrlError:
        return AppStoreUrlValidation(valid=False, error="Invalid App Store URL")
    return AppStoreUrlValidation(
        valid=True,
        storefront=app_ref.storefront,
        app_id=app_ref.apple_store_app_id,
    )


def _find_stage(run: RunState, stage_id: str):
    if stage_id not in WORKFLOW_STAGE_IDS:
        raise WorkflowStateError(f"Unknown workflow stage: {stage_id}")
    for stage in run.stages:
        if stage.stage == stage_id:
            return stage
    raise WorkflowStateError(f"Run {run.run_id} is missing stage {stage_id}")


def _next_pending_stage(run: RunState) -> str | None:
    for stage in run.stages:
        if stage.status in {STATUS_PENDING, STATUS_RUNNING}:
            return stage.stage
    return None


def _skip_stages_after(run: RunState, stage_id: str) -> None:
    should_skip = False
    for stage in run.stages:
        if should_skip and stage.status == STATUS_PENDING:
            stage.status = STATUS_SKIPPED
            stage.completed_at = now_utc()
        if stage.stage == stage_id:
            should_skip = True


def create_input_error(stage: str | None, message: str) -> WorkflowError:
    return WorkflowError(stage=stage, type=ERROR_INPUT, message=message, recoverable=True)
