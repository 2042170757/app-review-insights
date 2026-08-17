"""In-memory workflow orchestration for UI-triggered backend runs."""

from __future__ import annotations

import threading
import time
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
from app.workflow.artifacts import snapshot_stage_artifacts
from app.workflow.pipeline import BackendPipelineRunner, WorkflowStageExecutionError
from app.workflow.stages import (
    ERROR_INPUT,
    ERROR_UNKNOWN,
    RUN_COMPLETED,
    RUN_QUEUED,
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
from app.workflow.validation import VALIDATION_FAIL


class WorkflowInputError(ValueError):
    """Raised when workflow input cannot create a valid run."""


class WorkflowRunNotFound(KeyError):
    """Raised when a run id does not exist in the in-memory store."""


class WorkflowStateError(ValueError):
    """Raised when a workflow state transition is invalid."""


class WorkflowActiveRunError(RuntimeError):
    """Raised when another run is already executing fixed-path artifacts."""


class WorkflowOrchestrator:
    """Small in-memory orchestrator for UI workflow state.

    Runs are process-local because Phase 9b still writes fixed artifact paths.
    A single active run is allowed to prevent overlapping artifact writes.
    """

    def __init__(self, *, pipeline_runner: BackendPipelineRunner | None = None) -> None:
        self._runs: dict[str, RunState] = {}
        self._runner = pipeline_runner or BackendPipelineRunner()
        self._active_run_id: str | None = None
        self._lock = threading.RLock()

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
            is_mock=False,
        )
        with self._lock:
            self._runs[run.run_id] = run
        return run

    def get_run(self, run_id: str) -> RunState:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise WorkflowRunNotFound(run_id) from exc

    def list_stages(self, run_id: str) -> list[dict[str, object]]:
        return [stage.to_dict() for stage in self.get_run(run_id).stages]

    def start_run(self, run_id: str) -> RunState:
        with self._lock:
            run = self.get_run(run_id)
            if run.status == RUN_FAILED:
                raise WorkflowStateError("Cannot start a failed run")
            run.status = RUN_RUNNING
            run.touch()
            return run

    def start_run_async(self, run_id: str) -> RunState:
        with self._lock:
            run = self.get_run(run_id)
            if run.status not in {RUN_QUEUED, RUN_RUNNING}:
                raise WorkflowStateError(f"Cannot start run from status {run.status}")
            if self._active_run_id and self._active_run_id != run_id:
                raise WorkflowActiveRunError("已有分析任务正在运行")
            self._active_run_id = run_id
            run.status = RUN_RUNNING
            run.current_stage = _next_pending_stage(run)
            run.touch()
        thread = threading.Thread(target=self._run_pipeline, args=(run_id,), daemon=True)
        thread.start()
        return run

    def create_and_start_run_async(self, *, app_url: str, analysis_goal: str | None = None) -> RunState:
        with self._lock:
            if self._active_run_id:
                raise WorkflowActiveRunError("已有分析任务正在运行")
            run = self.create_run(app_url=app_url, analysis_goal=analysis_goal)
            self._active_run_id = run.run_id
            run.status = RUN_RUNNING
            run.current_stage = _next_pending_stage(run)
            run.touch()
        thread = threading.Thread(target=self._run_pipeline, args=(run.run_id,), daemon=True)
        thread.start()
        return run

    def run_pipeline_sync(self, run_id: str) -> RunState:
        with self._lock:
            if self._active_run_id and self._active_run_id != run_id:
                raise WorkflowActiveRunError("已有分析任务正在运行")
            self._active_run_id = run_id
        try:
            self._run_pipeline(run_id)
        finally:
            with self._lock:
                if self._active_run_id == run_id:
                    self._active_run_id = None
        return self.get_run(run_id)

    def mark_stage_running(self, run_id: str, stage_id: str) -> RunState:
        with self._lock:
            run = self.start_run(run_id)
            stage = _find_stage(run, stage_id)
            if stage.status not in {STATUS_PENDING, STATUS_RUNNING}:
                raise WorkflowStateError(f"Cannot run stage {stage_id} from status {stage.status}")
            stage.status = STATUS_RUNNING
            stage.started_at = stage.started_at or now_utc()
            stage.message = "Running"
            run.current_stage = stage_id
            run.touch()
            return run

    def mark_stage_completed(
        self,
        run_id: str,
        stage_id: str,
        *,
        message: str | None = None,
        artifacts: list[str] | None = None,
        warnings: list[str] | None = None,
        summary: dict[str, object] | None = None,
        elapsed_seconds: float | None = None,
    ) -> RunState:
        with self._lock:
            run = self.get_run(run_id)
            stage = _find_stage(run, stage_id)
            if stage.status == STATUS_SKIPPED:
                raise WorkflowStateError(f"Cannot complete skipped stage {stage_id}")
            stage.status = STATUS_COMPLETED
            stage.started_at = stage.started_at or now_utc()
            stage.completed_at = now_utc()
            stage.message = message or "Completed"
            requested_artifacts = list(artifacts or stage.artifacts)
            stage.artifacts = snapshot_stage_artifacts(run_id, stage_id, requested_artifacts) or requested_artifacts
            stage.warnings = list(warnings or [])
            stage.summary = dict(summary or {})
            stage.elapsed_seconds = elapsed_seconds
            _apply_validation_summary(run, stage.summary)
            for warning in stage.warnings:
                run.warnings.append(WorkflowWarning(stage=stage_id, type="stage_warning", message=warning))
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
        with self._lock:
            run = self.get_run(run_id)
            stage = _find_stage(run, stage_id)
            stage.status = STATUS_FAILED
            stage.started_at = stage.started_at or now_utc()
            stage.completed_at = now_utc()
            stage.message = message
            stage.errors = [
                {
                    "stage": stage_id,
                    "type": error_type if error_type in VALID_ERROR_TYPES else ERROR_UNKNOWN,
                    "message": message,
                    "recoverable": recoverable,
                }
            ]
            run.status = RUN_FAILED
            run.runtime_validation_status = VALIDATION_FAIL
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
            if self._active_run_id == run_id:
                self._active_run_id = None
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
        with self._lock:
            run = self.get_run(run_id)
            run.errors.append(
                WorkflowError(stage=stage, type=error_type, message=message, recoverable=recoverable)
            )
            run.touch()
            return run

    def add_warning(self, run_id: str, *, stage: str | None, warning_type: str, message: str) -> RunState:
        with self._lock:
            run = self.get_run(run_id)
            run.warnings.append(WorkflowWarning(stage=stage, type=warning_type, message=message))
            run.touch()
            return run

    def add_revision(self, run_id: str, *, stage: str, reason: str, status: str) -> RunState:
        with self._lock:
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

    def _run_pipeline(self, run_id: str) -> None:
        started = time.perf_counter()
        try:
            for stage_id in WORKFLOW_STAGE_IDS:
                run = self.get_run(run_id)
                if run.status == RUN_FAILED:
                    break
                self.mark_stage_running(run_id, stage_id)
                context = self._context_for_run(run_id)
                try:
                    result = self._runner.run_stage(stage=stage_id, context=context)
                except WorkflowStageExecutionError as exc:
                    self.mark_stage_failed(
                        run_id,
                        stage_id,
                        error_type=exc.error_type,
                        message=exc.message,
                        recoverable=True,
                    )
                    with self._lock:
                        failed_stage = _find_stage(self.get_run(run_id), stage_id)
                        failed_stage.artifacts = (
                            snapshot_stage_artifacts(run_id, stage_id, exc.artifacts) or exc.artifacts
                        )
                        failed_stage.warnings = exc.warnings
                        failed_stage.summary = exc.summary
                        _apply_validation_summary(self.get_run(run_id), failed_stage.summary)
                    break
                except Exception as exc:
                    self.mark_stage_failed(
                        run_id,
                        stage_id,
                        error_type=ERROR_UNKNOWN,
                        message=f"Unexpected workflow error: {exc!r}",
                        recoverable=True,
                    )
                    break
                self.mark_stage_completed(
                    run_id,
                    stage_id,
                    message=result.message,
                    artifacts=result.artifacts,
                    warnings=result.warnings,
                    summary=result.summary,
                    elapsed_seconds=result.elapsed_seconds,
                )
            with self._lock:
                run = self.get_run(run_id)
                if run.status != RUN_FAILED and all(stage.status == STATUS_COMPLETED for stage in run.stages):
                    run.status = RUN_COMPLETED
                    run.current_stage = None
                    run.touch()
                if self._active_run_id == run_id:
                    self._active_run_id = None
        finally:
            with self._lock:
                run = self._runs.get(run_id)
                if run:
                    run.total_elapsed_seconds = round(time.perf_counter() - started, 3)
                    run.touch()
                if self._active_run_id == run_id:
                    self._active_run_id = None

    def _context_for_run(self, run_id: str) -> dict[str, str]:
        run = self.get_run(run_id)
        return {
            "run_id": run.run_id,
            "app_url": run.app_url,
            "analysis_goal": run.analysis_goal,
            "storefront": run.storefront or "",
            "app_id": run.app_id or "",
            "review_territory": "US",
        }


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


def _apply_validation_summary(run: RunState, summary: dict[str, object]) -> None:
    runtime_status = summary.get("runtime_validation_status")
    submission_status = summary.get("submission_validation_status")
    if isinstance(runtime_status, str) and runtime_status:
        run.runtime_validation_status = runtime_status
    if isinstance(submission_status, str) and submission_status:
        run.submission_validation_status = submission_status


def create_input_error(stage: str | None, message: str) -> WorkflowError:
    return WorkflowError(stage=stage, type=ERROR_INPUT, message=message, recoverable=True)
