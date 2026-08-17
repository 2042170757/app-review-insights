"""FastAPI server for Phase 9a workflow shell endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api import results
from app.workflow.orchestrator import (
    WorkflowActiveRunError,
    WorkflowInputError,
    WorkflowOrchestrator,
    WorkflowRunNotFound,
)


class CreateRunRequest(BaseModel):
    app_url: str
    analysis_goal: str | None = None


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
            run = workflow.create_and_start_run_async(app_url=request.app_url, analysis_goal=request.analysis_goal)
        except WorkflowInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except WorkflowActiveRunError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"run_id": run.run_id}

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


app = create_app()
