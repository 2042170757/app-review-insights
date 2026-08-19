"""Read-only diagnostics for Topic Discovery review_id reference failures."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.topic_discovery import build_topic_request, find_unknown_topic_review_ids


DEFAULT_OUTPUT_PATH = Path("artifacts/final_validation/topic_review_reference_diagnosis.json")


def diagnose_topic_review_references(
    *,
    run_dir: Path,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    artifact_root: Path = Path("artifacts"),
) -> dict[str, Any]:
    processing_dir = run_dir / "processing"
    topic_dir = run_dir / "topic_discovery"

    reviews_all = _load_reviews(processing_dir / "reviews_all.json")
    processed_reviews = _load_reviews(processing_dir / "reviews.json")
    selected_reviews = _load_reviews(processing_dir / "selected_reviews.json")
    topic_raw = _load_json(topic_dir / "topic_discovery_raw.json")
    topics = _load_json(topic_dir / "topics.json")
    validation = _load_json(topic_dir / "topic_validation.json")
    scope_report = _load_json(processing_dir / "scope_report.json")
    collection_metadata = _load_json(run_dir / "collection" / "dataset_metadata.json")

    input_reviews = selected_reviews or processed_reviews
    input_review_ids = _review_ids(input_reviews)
    validator_review_ids = _review_ids(processed_reviews)
    unknown_review_ids = _unknown_review_ids(topic_raw, validation, set(validator_review_ids))
    prompt_check = _prompt_check(input_reviews, topic_raw.get("analysis_goal") or "")
    previous_artifacts = _previous_artifact_scan(
        artifact_root=artifact_root,
        run_dir=run_dir,
        unknown_review_ids=unknown_review_ids,
        output_path=output_path,
    )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run_dir.name,
        "artifact_paths": {
            "run_dir": str(run_dir),
            "reviews_all": str(processing_dir / "reviews_all.json"),
            "processed_reviews": str(processing_dir / "reviews.json"),
            "selected_reviews": str(processing_dir / "selected_reviews.json"),
            "topic_raw": str(topic_dir / "topic_discovery_raw.json"),
            "topics": str(topic_dir / "topics.json"),
            "topic_validation": str(topic_dir / "topic_validation.json"),
        },
        "analysis_goal": topic_raw.get("analysis_goal"),
        "analysis_focus": scope_report.get("analysis_focus") or collection_metadata.get("analysis_focus"),
        "constraints": scope_report.get("constraints") or scope_report.get("constraint") or {},
        "provider": topic_raw.get("provider"),
        "model": topic_raw.get("model"),
        "input_review_count": len(input_review_ids),
        "reviews_all_count": len(_review_ids(reviews_all)),
        "processed_review_count": len(_review_ids(processed_reviews)),
        "selected_review_count": len(_review_ids(selected_reviews)),
        "validator_review_count": len(validator_review_ids),
        "review_id_sets_match": set(input_review_ids) == set(validator_review_ids),
        "unknown_review_ids": unknown_review_ids,
        "unknown_ids_exist_in_reviews_all": _all_in(unknown_review_ids, set(_review_ids(reviews_all))),
        "unknown_ids_exist_in_processed_reviews": _all_in(unknown_review_ids, set(_review_ids(processed_reviews))),
        "unknown_ids_exist_in_selected_reviews": _all_in(unknown_review_ids, set(_review_ids(selected_reviews))),
        "unknown_ids_exist_in_previous_artifacts": previous_artifacts["exists_as_text"],
        "unknown_ids_exist_as_valid_reviews_in_previous_artifacts": previous_artifacts["exists_as_valid_review_id"],
        "prompt_contains_allowed_review_ids": prompt_check["contains_allowed_review_ids"],
        "prompt_valid_review_id_count": prompt_check["valid_review_id_count"],
        "prompt_contains_unknown_review_ids": any(
            unknown_review_id in prompt_check["prompt_text"] for unknown_review_id in unknown_review_ids
        ),
        "artifact_isolation_ok": set(input_review_ids) == set(validator_review_ids)
        and not _any_in(unknown_review_ids, set(input_review_ids)),
        "topic_validation_status": validation.get("status"),
        "topic_validation_errors": validation.get("errors", []),
        "topic_count_written": len(topics.get("topics", [])) if isinstance(topics, dict) else None,
        "suspected_root_cause": (
            "model_reference_hallucination"
            if unknown_review_ids and not _any_in(unknown_review_ids, set(input_review_ids))
            else "artifact_or_scope_mismatch"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _unknown_review_ids(
    topic_raw: dict[str, Any],
    validation: dict[str, Any],
    valid_review_ids: set[str],
) -> list[str]:
    extracted_json = topic_raw.get("extracted_json")
    if isinstance(extracted_json, str):
        unknown = find_unknown_topic_review_ids(extracted_json, valid_review_ids)
        if unknown:
            return unknown
    unknown: list[str] = []
    seen: set[str] = set()
    for error in validation.get("errors", []):
        if not isinstance(error, str):
            continue
        match = re.search(r"unknown review id\s+(\S+)", error)
        if match:
            review_id = match.group(1)
            if review_id not in seen:
                seen.add(review_id)
                unknown.append(review_id)
    return unknown


def _prompt_check(reviews: list[dict[str, Any]], analysis_goal: str) -> dict[str, Any]:
    request = build_topic_request(reviews, analysis_goal=analysis_goal)
    prompt_text = request.system_prompt + "\n" + request.user_prompt
    try:
        payload = json.loads(request.user_prompt)
    except json.JSONDecodeError:
        payload = {}
    valid_review_ids = payload.get("valid_review_ids") if isinstance(payload, dict) else None
    return {
        "contains_allowed_review_ids": "VALID REVIEW IDS" in request.system_prompt
        and isinstance(valid_review_ids, list)
        and bool(valid_review_ids),
        "valid_review_id_count": len(valid_review_ids) if isinstance(valid_review_ids, list) else 0,
        "prompt_text": prompt_text,
    }


def _previous_artifact_scan(
    *,
    artifact_root: Path,
    run_dir: Path,
    unknown_review_ids: list[str],
    output_path: Path,
) -> dict[str, bool]:
    exists_as_text = False
    exists_as_valid_review_id = False
    if not unknown_review_ids or not artifact_root.exists():
        return {"exists_as_text": exists_as_text, "exists_as_valid_review_id": exists_as_valid_review_id}
    unknown_set = set(unknown_review_ids)
    for path in artifact_root.rglob("*.json"):
        if _is_relative_to(path, run_dir) or path == output_path:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(review_id in text for review_id in unknown_set):
            exists_as_text = True
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if _any_in(unknown_review_ids, set(_extract_review_ids(payload))):
            exists_as_valid_review_id = True
    return {"exists_as_text": exists_as_text, "exists_as_valid_review_id": exists_as_valid_review_id}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_reviews(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    reviews = payload.get("reviews")
    return list(reviews) if isinstance(reviews, list) else []


def _review_ids(reviews: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for review in reviews:
        value = review.get("id")
        if isinstance(value, str) and value.strip():
            ids.append(value.strip())
    return ids


def _extract_review_ids(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        value = payload.get("id")
        if isinstance(value, str):
            found.append(value)
        for item in payload.values():
            found.extend(_extract_review_ids(item))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_extract_review_ids(item))
    return found


def _all_in(values: list[str], candidates: set[str]) -> bool:
    return bool(values) and all(value in candidates for value in values)


def _any_in(values: list[str], candidates: set[str]) -> bool:
    return any(value in candidates for value in values)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Topic Discovery review_id reference integrity.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    report = diagnose_topic_review_references(run_dir=args.run_dir, output_path=args.output)
    print("Topic Reference Diagnosis: PASS")
    print(f"Run ID: {report['run_id']}")
    print(f"Unknown Review IDs: {', '.join(report['unknown_review_ids']) or 'none'}")
    print(f"Suspected Root Cause: {report['suspected_root_cause']}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
