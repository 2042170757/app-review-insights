"""Run-scoped workflow artifact snapshots for read-only UI result APIs."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


RUN_ARTIFACT_ROOT_ENV = "WORKFLOW_RUN_ARTIFACT_ROOT"
DEFAULT_RUN_ARTIFACT_ROOT = Path("artifacts/runs")


def run_artifact_root() -> Path:
    configured = os.environ.get(RUN_ARTIFACT_ROOT_ENV)
    return Path(configured) if configured else DEFAULT_RUN_ARTIFACT_ROOT


def snapshot_stage_artifacts(run_id: str, stage_id: str, artifact_paths: list[str]) -> list[str]:
    """Copy existing stage artifacts into a run-specific directory.

    The pipeline still writes its canonical Phase 1-8 artifact files. This
    snapshot only preserves read-only evidence for later UI/API access by run_id.
    """
    copied: list[str] = []
    target_dir = run_artifact_root() / run_id / stage_id
    for artifact_path in artifact_paths:
        source = Path(artifact_path)
        if not source.exists() or not source.is_file():
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copy2(source, target)
        copied.append(str(target))
    return copied


def find_run_artifact(run_id: str, artifact_paths: list[str], filename: str) -> Path | None:
    for artifact_path in artifact_paths:
        path = Path(artifact_path)
        if path.name == filename and path.exists() and path.is_file():
            return path

    root = run_artifact_root() / run_id
    if not root.exists():
        return None
    matches = sorted(root.glob(f"**/{filename}"))
    for match in matches:
        if match.is_file():
            return match
    return None
