"""FastAPI server for Phase 9a workflow shell endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api import results
from app.demo import DemoCacheError, validate_demo_cache
from app.imports import ImportValidationError, create_import_dataset, max_import_bytes
from app.workflow.orchestrator import (
    WorkflowActiveRunError,
    WorkflowInputError,
    WorkflowOrchestrator,
    WorkflowRunNotFound,
    validate_app_store_url,
)


class CreateRunRequest(BaseModel):
    app_url: str
    analysis_goal: str | None = None
    constraints: dict[str, Any] | None = None


class CreateImportRunRequest(BaseModel):
    import_id: str
    app_url: str
    analysis_goal: str | None = None
    constraints: dict[str, Any] | None = None


def create_app(orchestrator: WorkflowOrchestrator | None = None) -> FastAPI:
    workflow = orchestrator or WorkflowOrchestrator()
    api = FastAPI(title="App Review Insights Workflow API", version="0.9.0")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    api.state.workflow_orchestrator = workflow

    @api.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.post("/api/runs")
    def create_run(request: CreateRunRequest) -> dict[str, str]:
        try:
            run = workflow.create_and_start_run_async(
                app_url=request.app_url,
                analysis_goal=request.analysis_goal,
                constraints=request.constraints,
            )
        except WorkflowInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except WorkflowActiveRunError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"run_id": run.run_id}

    @api.post("/api/runs/import")
    def create_import_run(request: CreateImportRunRequest) -> dict[str, str]:
        try:
            run = workflow.create_and_start_import_run_async(
                app_url=request.app_url,
                analysis_goal=request.analysis_goal,
                import_id=request.import_id,
                constraints=request.constraints,
            )
        except WorkflowInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except WorkflowActiveRunError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"run_id": run.run_id}

    @api.post("/api/import/json")
    async def import_json(file: UploadFile = File(...), app_url: str = Form("")) -> dict[str, Any]:
        return await _import_preview(workflow, source_type="json", file=file, app_url=app_url)

    @api.post("/api/import/csv")
    async def import_csv(file: UploadFile = File(...), app_url: str = Form("")) -> dict[str, Any]:
        return await _import_preview(workflow, source_type="csv", file=file, app_url=app_url)

    @api.get("/api/demo/metadata")
    def get_demo_metadata() -> dict[str, Any]:
        validation = validate_demo_cache()
        if validation["status"] != "PASS":
            raise HTTPException(status_code=500, detail={"type": "Invalid Demo Cache", "message": validation["errors"][0]})
        return validation

    @api.get("/api/demo/run")
    def get_demo_run() -> dict[str, Any]:
        try:
            return workflow.create_demo_run().to_dict()
        except DemoCacheError as exc:
            raise HTTPException(status_code=500, detail={"type": "Invalid Demo Cache", "message": str(exc)}) from exc

    @api.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        try:
            return workflow.get_run(run_id).to_dict()
        except WorkflowRunNotFound as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @api.get("/api/runs/{run_id}/stages")
    def get_run_stages(run_id: str) -> dict[str, Any]:
        try:
            return {"stages": workflow.list_stages(run_id)}
        except WorkflowRunNotFound as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @api.get("/api/runs/{run_id}/reviews")
    def get_reviews(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.reviews_payload)

    @api.get("/api/runs/{run_id}/topics")
    def get_topics(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.topics_payload)

    @api.get("/api/runs/{run_id}/issues")
    def get_issues(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.issues_payload)

    @api.get("/api/runs/{run_id}/findings")
    def get_findings(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.findings_payload)

    @api.get("/api/runs/{run_id}/requirements")
    def get_requirements(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.requirements_payload)

    @api.get("/api/runs/{run_id}/roadmap")
    def get_roadmap(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.roadmap_payload)

    @api.get("/api/runs/{run_id}/prd")
    def get_prd(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.prd_payload)

    @api.get("/api/runs/{run_id}/test-cases")
    def get_test_cases(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.test_cases_payload)

    @api.get("/api/runs/{run_id}/traceability")
    def get_traceability(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.traceability_payload)

    @api.get("/api/runs/{run_id}/validation")
    def get_validation(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.validation_payload)

    @api.get("/api/runs/{run_id}/errors")
    def get_errors(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.errors_payload)

    @api.get("/api/runs/{run_id}/warnings")
    def get_warnings(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.warnings_payload)

    @api.get("/api/runs/{run_id}/revisions")
    def get_revisions(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.revisions_payload)

    @api.get("/api/runs/{run_id}/metadata")
    def get_metadata(run_id: str) -> dict[str, Any]:
        return _result_payload(workflow, run_id, results.metadata_payload)

    return api


def _result_payload(workflow: WorkflowOrchestrator, run_id: str, adapter) -> dict[str, Any]:
    try:
        return adapter(workflow.get_run(run_id))
    except WorkflowRunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


async def _import_preview(
    workflow: WorkflowOrchestrator,
    *,
    source_type: str,
    file: UploadFile,
    app_url: str,
) -> dict[str, Any]:
    app_id = ""
    if app_url:
        validation = validate_app_store_url(app_url)
        if not validation.valid:
            raise HTTPException(status_code=400, detail={"type": "Invalid App Context", "message": validation.error})
        app_id = validation.app_id or ""
    try:
        content = await file.read(max_import_bytes() + 1)
        dataset = create_import_dataset(
            source_type=source_type,
            filename=file.filename or "",
            content=content,
            app_id=app_id,
        )
    except ImportValidationError as exc:
        raise HTTPException(status_code=400, detail={"type": exc.error_type, "message": exc.message}) from exc
    workflow.register_import(dataset)
    return {
        "import_id": dataset.import_id,
        "source_type": dataset.source_type,
        "filename": dataset.filename,
        "metadata": dataset.metadata,
        "warnings": dataset.metadata.get("limitations", []),
    }


app = create_app()
