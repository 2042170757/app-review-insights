"""FastAPI server for Phase 9a workflow shell endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

    return api


app = create_app()
