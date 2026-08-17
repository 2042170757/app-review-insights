"""Offline cached demo run support."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.workflow.models import RunState, WorkflowStageState, new_run_state, now_utc
from app.workflow.stages import RUN_COMPLETED, STATUS_COMPLETED
from app.workflow.validation import VALIDATION_PASS, VALIDATION_PENDING


DEMO_CACHE_ROOT_ENV = "WORKFLOW_DEMO_CACHE_ROOT"
DEFAULT_DEMO_CACHE_ROOT = Path(__file__).resolve().parent / "demo_cache"
DEMO_RUN_ID_PREFIX = "demo-"
DEMO_APP_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"
DEMO_ANALYSIS_GOAL = "分析低评分用户对订阅和价格的主要问题"
DEMO_DATA_SOURCE = "cached_demo"
DEMO_DISPLAY_SOURCE = "Cached / Demo Data"

REQUIRED_STAGE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "collection": ("normalized_reviews.json", "dataset_metadata.json"),
    "processing": ("reviews.json", "statistics.json", "processing_report.json"),
    "topic_discovery": ("topics.json", "topic_validation.json", "topic_discovery_raw.json"),
    "issue_consolidation": (
        "issues.json",
        "issue_validation.json",
        "issue_classification.json",
        "finding_eligibility.json",
        "issue_consolidation_raw.json",
    ),
    "finding_generation": (
        "findings.json",
        "finding_validation.json",
        "evidence_report.json",
        "finding_generation_raw.json",
    ),
    "requirement_generation": (
        "requirements.json",
        "requirement_validation.json",
        "priority_report.json",
        "requirement_generation_raw.json",
    ),
    "roadmap": ("roadmap.json", "roadmap_validation.json", "roadmap_generation_raw.json"),
    "prd": ("prds.json", "prd_validation.json", "prd_generation_raw.json"),
    "test_cases": (
        "test_cases.json",
        "test_case_validation.json",
        "test_coverage.json",
        "test_case_generation_raw.json",
    ),
    "traceability": ("final_validation_report.json",),
}


class DemoCacheError(ValueError):
    """Raised when the offline demo cache is missing or invalid."""


@dataclass(frozen=True)
class DemoCache:
    root: Path
    metadata: dict[str, Any]
    stage_artifacts: dict[str, list[str]]


def demo_cache_root() -> Path:
    configured = os.environ.get(DEMO_CACHE_ROOT_ENV)
    return Path(configured) if configured else DEFAULT_DEMO_CACHE_ROOT


def load_demo_cache(root: Path | None = None) -> DemoCache:
    cache_root = root or demo_cache_root()
    metadata = _load_required_json(cache_root / "demo_metadata.json")
    _validate_demo_metadata(metadata)
    stage_artifacts: dict[str, list[str]] = {}
    for stage_id, filenames in REQUIRED_STAGE_ARTIFACTS.items():
        stage_paths = []
        for filename in filenames:
            path = cache_root / stage_id / filename
            _load_required_json(path)
            stage_paths.append(str(path))
        stage_artifacts[stage_id] = stage_paths
    _validate_demo_counts(cache_root, metadata)
    _validate_demo_traceability(cache_root)
    return DemoCache(root=cache_root, metadata=metadata, stage_artifacts=stage_artifacts)


def create_demo_run_state(*, run_id: str, cache: DemoCache | None = None) -> RunState:
    demo_cache = cache or load_demo_cache()
    run = new_run_state(
        run_id=run_id,
        app_url=DEMO_APP_URL,
        analysis_goal=DEMO_ANALYSIS_GOAL,
        storefront=str(demo_cache.metadata.get("territory") or "US"),
        app_id=str(demo_cache.metadata.get("app_id") or "839285684"),
        is_mock=False,
        source_type=DEMO_DATA_SOURCE,
        data_source=DEMO_DATA_SOURCE,
        import_metadata={},
        is_demo=True,
        demo_metadata=demo_cache.metadata,
    )
    timestamp = now_utc()
    run.status = RUN_COMPLETED
    run.current_stage = None
    run.runtime_validation_status = VALIDATION_PASS
    run.submission_validation_status = VALIDATION_PENDING
    run.progress = 100.0
    run.created_at = timestamp
    run.updated_at = timestamp
    for stage in run.stages:
        stage.status = STATUS_COMPLETED
        stage.started_at = timestamp
        stage.completed_at = timestamp
        stage.message = "Loaded from offline cached demo artifact."
        stage.artifacts = list(demo_cache.stage_artifacts.get(stage.stage, []))
        stage.summary = _demo_stage_summary(stage, demo_cache.metadata)
        stage.elapsed_seconds = 0.0
    return run


def validate_demo_cache(root: Path | None = None) -> dict[str, Any]:
    try:
        cache = load_demo_cache(root)
    except DemoCacheError as exc:
        return {"status": "FAIL", "errors": [str(exc)], "warnings": []}
    return {
        "status": "PASS",
        "errors": [],
        "warnings": [
            "Cached demo data is for offline presentation only and is not a live provider result."
        ],
        "metadata": cache.metadata,
        "stage_count": len(cache.stage_artifacts),
        "artifact_count": sum(len(paths) for paths in cache.stage_artifacts.values()),
    }


def _demo_stage_summary(stage: WorkflowStageState, metadata: dict[str, Any]) -> dict[str, Any]:
    if stage.stage == "collection":
        return {
            "provider": metadata.get("source_provider"),
            "territory": metadata.get("territory"),
            "app_id": metadata.get("app_id"),
            "requested_limit": metadata.get("review_count"),
            "actual_count": metadata.get("review_count"),
            "is_demo": True,
            "display_source": DEMO_DISPLAY_SOURCE,
            "limitations": [_demo_limitation()],
        }
    if stage.stage == "traceability":
        return {
            "runtime_validation_status": VALIDATION_PASS,
            "submission_validation_status": VALIDATION_PENDING,
            "is_demo": True,
        }
    return {"is_demo": True}


def _load_required_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise DemoCacheError(f"Missing demo cache artifact: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DemoCacheError(f"Invalid demo cache JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise DemoCacheError(f"Invalid demo cache artifact shape: {path.name}")
    _reject_secret_markers(path)
    return payload


def _validate_demo_metadata(metadata: dict[str, Any]) -> None:
    required = {
        "is_demo",
        "mode",
        "source_provider",
        "territory",
        "app_id",
        "review_count",
        "collected_at",
        "model_provider",
        "model",
        "description",
    }
    missing = sorted(key for key in required if metadata.get(key) in {None, ""})
    if missing:
        raise DemoCacheError(f"Demo metadata missing required fields: {', '.join(missing)}")
    if metadata.get("is_demo") is not True or metadata.get("mode") != DEMO_DATA_SOURCE:
        raise DemoCacheError("Demo metadata must be explicitly marked as cached_demo.")


def _validate_demo_counts(cache_root: Path, metadata: dict[str, Any]) -> None:
    reviews = _load_required_json(cache_root / "processing" / "reviews.json").get("reviews")
    if not isinstance(reviews, list):
        raise DemoCacheError("Demo processed reviews must contain a reviews list.")
    if len(reviews) != int(metadata.get("review_count") or 0):
        raise DemoCacheError("Demo review_count does not match processed reviews.")
    dataset = _load_required_json(cache_root / "collection" / "dataset_metadata.json")
    if dataset.get("provider") != metadata.get("source_provider"):
        raise DemoCacheError("Demo provider metadata mismatch.")
    if dataset.get("territory") != metadata.get("territory"):
        raise DemoCacheError("Demo territory metadata mismatch.")
    if str(dataset.get("app_id")) != str(metadata.get("app_id")):
        raise DemoCacheError("Demo app_id metadata mismatch.")
    if int(dataset.get("actual_count") or 0) != int(metadata.get("review_count") or 0):
        raise DemoCacheError("Demo actual_count metadata mismatch.")


def _validate_demo_traceability(cache_root: Path) -> None:
    validation = _load_required_json(cache_root / "traceability" / "final_validation_report.json")
    if str(validation.get("runtime_validation_status", "")).lower() != VALIDATION_PASS:
        raise DemoCacheError("Demo runtime validation must be pass.")
    if str(validation.get("submission_validation_status", "")).lower() != VALIDATION_PENDING:
        raise DemoCacheError("Demo submission validation must remain pending.")


def _reject_secret_markers(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    markers = ("DEEPSEEK_API_KEY=", "APIFY_API_TOKEN=", "OPENAI_API_KEY=", "Bearer ", "sk-")
    if any(marker in text for marker in markers):
        raise DemoCacheError(f"Demo cache artifact contains a secret-like marker: {path.name}")


def _demo_limitation() -> str:
    return "Cached demo result for offline interview presentation; not a live collection or model run."


def demo_cache_artifact_paths(root: Path | None = None) -> list[Path]:
    cache = load_demo_cache(root)
    return [Path(path) for paths in cache.stage_artifacts.values() for path in paths] + [cache.root / "demo_metadata.json"]
