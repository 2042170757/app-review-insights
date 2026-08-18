"""Read-only diagnostics for the final Phase 10c failure scenarios."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.topic_discovery import extract_json_text


DEFAULT_MATRIX_PATH = Path("artifacts/final_validation/generalization_matrix_final_v2.json")
DEFAULT_RUNS_ROOT = Path("artifacts/final_validation/phase10c_final_stabilization_runs")
DEFAULT_OUTPUT_PATH = Path("artifacts/final_validation/final_failure_diagnosis.json")

ALLOWED_CATEGORIES = {
    "Generator Bug",
    "Validator Bug",
    "Prompt Context Issue",
    "Artifact Isolation Bug",
    "ID Normalization Bug",
    "Scope Propagation Bug",
    "Model Reference Hallucination",
    "Provider Failure",
    "Data Insufficiency",
    "Expected Limitation",
    "Unknown",
}

LEGACY_OPEN_QUESTION_TERMS = {
    "REQ-001": ["proportion", "threshold", "free access", "free tier", "library"],
    "REQ-007": ["cadence", "frequency", "refresh", "update", "monthly"],
    "REQ-008": ["support channel", "channel", "email", "chat", "support"],
}

CONTEXTUAL_OPEN_QUESTION_TERMS = {
    "crash": ["crash", "large file", "large files"],
    "large file": ["crash", "large file", "large files"],
    "export": ["export", "format"],
    "notification": ["notification", "reminder", "on time", "duplicate"],
    "support": ["support", "channel"],
}


def diagnose_final_failures(
    *,
    matrix_path: Path = DEFAULT_MATRIX_PATH,
    runs_root: Path = DEFAULT_RUNS_ROOT,
    output_path: Path | None = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    matrix = _load_json(matrix_path)
    tests = matrix.get("tests") if isinstance(matrix.get("tests"), list) else []
    json_entry = _matrix_entry(tests, "json_import_generalization")
    mixed_entry = _matrix_entry(tests, "mixed_focus_regression")
    report = {
        "generated_at": _now(),
        "source_matrix": str(matrix_path),
        "matrix_summary": {
            "pass": sum(1 for item in tests if isinstance(item, dict) and item.get("status") == "PASS"),
            "fail": sum(1 for item in tests if isinstance(item, dict) and item.get("status") == "FAIL"),
        },
        "json_import": diagnose_json_import_failure(
            _run_root(runs_root, _text(json_entry.get("run_id"))),
            retry_run_root=_run_root(runs_root, _text(json_entry.get("retry_run_id"))),
        ),
        "mixed_focus": diagnose_mixed_focus_failure(
            _run_root(runs_root, _text(mixed_entry.get("run_id"))),
            retry_run_root=_run_root(runs_root, _text(mixed_entry.get("retry_run_id"))),
        ),
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def diagnose_json_import_failure(initial_run_root: Path, *, retry_run_root: Path | None = None) -> dict[str, Any]:
    initial = _load_json_import_run(initial_run_root)
    retry = _load_json_import_run(retry_run_root) if retry_run_root else None
    artifact_isolation = _json_artifact_isolation(initial)
    goal_findings = _goal_alignment_findings(initial)
    retry_missing_open_questions = _missing_open_question_findings(retry) if retry else []

    category = "Unknown"
    root_cause = "Unable to classify JSON Import failure from available artifacts."
    if not artifact_isolation["passed"]:
        category = "Artifact Isolation Bug"
        root_cause = "JSON Import artifacts appear to be mixed with another run or source."
    elif any(item["validator_rejected_despite_first_goal_match"] for item in goal_findings):
        category = "Validator Bug"
        root_cause = (
            "PRD validation rejected a PRD for goal incoherence even though goals[0] exactly matched "
            "the Roadmap Version goal."
        )
    elif any(item["contextual_question_present"] and not item["legacy_question_present"] for item in retry_missing_open_questions):
        category = "Validator Bug"
        root_cause = (
            "PRD validation applies context-insensitive requirement-id open-question rules. In the JSON run, "
            "REQ-007 describes large-file crashes, but the validator expects the legacy content refresh cadence terms."
        )
    elif initial["prd_validation_status"] in {"Goal Incoherence", "Missing Open Question"}:
        category = "Prompt Context Issue"
        root_cause = "The PRD output did not satisfy the validator's goal or open-question context requirements."

    evidence = [
        f"initial_run={initial['run_id']}",
        f"initial_prd_validation={initial['prd_validation_status']}: {'; '.join(initial['prd_validation_errors'])}",
        f"source_type={artifact_isolation['source_type']}, display_source={artifact_isolation['display_source']}, selected_count={artifact_isolation['selected_count']}",
    ]
    for item in goal_findings:
        evidence.append(
            f"{item['prd_id']} {item['version_id']}: goals[0]_matches_version_goal={item['first_goal_matches']}"
        )
    if retry:
        evidence.append(
            f"retry_run={retry['run_id']}; retry_prd_validation={retry['prd_validation_status']}: "
            f"{'; '.join(retry['prd_validation_errors'])}"
        )
    for item in retry_missing_open_questions:
        evidence.append(
            f"{item['requirement_id']} title={item['requirement_title']!r}; "
            f"contextual_question_present={item['contextual_question_present']}; "
            f"legacy_question_present={item['legacy_question_present']}"
        )
    if artifact_isolation["hardcoded_terms"]:
        evidence.append(
            "PRD raw output contains app-specific terms not tied to import metadata: "
            + ", ".join(artifact_isolation["hardcoded_terms"])
        )

    return {
        "root_cause": root_cause,
        "stage": "prd",
        "category": _safe_category(category),
        "evidence": evidence,
        "recommendation": (
            "Keep PRD validation strict, but in a fix phase make PRD goal validation honor the explicit "
            "goals[0] contract and replace global REQ-001/REQ-007/REQ-008 semantic assumptions with "
            "context-derived product-decision requirements."
        ),
        "is_production_bug": category in {"Validator Bug", "Prompt Context Issue", "Artifact Isolation Bug"},
        "needs_final_fix": category in {"Validator Bug", "Prompt Context Issue", "Artifact Isolation Bug"},
        "input_context_hash": _hash_payload(initial["input_context"]),
        "prompt_context_hash": _hash_payload(initial["prompt_context"], (retry or {}).get("prompt_context", {})),
        "artifact_context_hash": _hash_payload(initial["artifact_context"], (retry or {}).get("artifact_context", {})),
        "artifact_isolation": artifact_isolation,
        "goal_alignment": goal_findings,
        "missing_open_questions": retry_missing_open_questions,
    }


def diagnose_mixed_focus_failure(initial_run_root: Path, *, retry_run_root: Path | None = None) -> dict[str, Any]:
    initial = _load_mixed_topic_failure(initial_run_root)
    retry = _load_mixed_requirement_failure(retry_run_root) if retry_run_root else None
    latest_category = "Unknown"
    latest_stage = "topic_discovery"
    root_cause = "Unable to classify Mixed Focus failure from available artifacts."
    if retry and retry["requirement_generation_status"] == "Invalid JSON":
        latest_stage = "requirement_generation"
        if retry["finish_reason"] == "length":
            latest_category = "Generator Bug"
            root_cause = (
                "Requirement generation exhausted the configured completion budget and returned a truncated JSON "
                "object. Retry and JSON Recovery both ran, but no complete JSON object existed to recover."
            )
        elif retry["retry_attempted"] and not retry["retry_success"]:
            latest_category = "Generator Bug"
            root_cause = "Requirement generation retry ran with the same context, but the model still returned invalid JSON."
        else:
            latest_category = "Prompt Context Issue"
            root_cause = "Requirement generation returned invalid JSON and retry metadata is incomplete."
    elif initial["unknown_review_ids"]:
        latest_category = "Model Reference Hallucination"
        root_cause = "Topic Discovery raw model output referenced review IDs that were not present in processed reviews."

    secondary = []
    if initial["unknown_review_ids"]:
        secondary.append(
            {
                "stage": "topic_discovery",
                "category": "Model Reference Hallucination",
                "root_cause": "Model output introduced review IDs absent from processed and selected review IDs.",
                "unknown_review_ids": initial["unknown_review_ids"],
            }
        )

    evidence = [
        f"initial_run={initial['run_id']}",
        f"initial_topic_validation={initial['topic_validation_status']}: {'; '.join(initial['topic_validation_errors'])}",
        f"unknown_review_ids={', '.join(initial['unknown_review_ids']) or 'none'}",
    ]
    for item in initial["unknown_review_details"]:
        evidence.append(
            f"{item['review_id']}: in_processed={item['in_processed_reviews']}, "
            f"in_selected={item['in_selected_reviews']}, raw_contains={item['raw_contains']}"
        )
    if retry:
        evidence.extend(
            [
                f"retry_run={retry['run_id']}",
                f"requirement_generation={retry['requirement_generation_status']}; validation={retry['requirement_validation_status']}",
                f"finish_reason={retry['finish_reason']}; completion_tokens={retry['completion_tokens']}; raw_length={retry['raw_output_length']}",
                f"retry_attempted={retry['retry_attempted']}; retry_success={retry['retry_success']}; retry_error={retry['retry_error']}",
                f"finding_type_distribution={retry['finding_type_distribution']}",
            ]
        )

    return {
        "root_cause": root_cause,
        "stage": latest_stage,
        "category": _safe_category(latest_category),
        "evidence": evidence,
        "recommendation": (
            "Do not auto-replace Review IDs or relax validators. In a fix phase, address Mixed Focus reliability "
            "with bounded output-size control or targeted format retry, and keep evidence ID rejection strict."
        ),
        "is_production_bug": latest_category in {"Generator Bug", "Prompt Context Issue", "Provider Failure"},
        "needs_final_fix": True,
        "input_context_hash": _hash_payload(initial["input_context"], (retry or {}).get("input_context", {})),
        "prompt_context_hash": _hash_payload(initial["prompt_context"], (retry or {}).get("prompt_context", {})),
        "artifact_context_hash": _hash_payload(initial["artifact_context"], (retry or {}).get("artifact_context", {})),
        "topic_unknown_review_id": initial,
        "requirement_invalid_json": retry,
        "secondary_failures": secondary,
        "problem_positive_separation": (retry or {}).get("problem_positive_separation", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 10c.6 final failure diagnosis.")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    report = diagnose_final_failures(matrix_path=args.matrix, runs_root=args.runs_root, output_path=args.output)
    print("Final Failure Diagnostics: PASS")
    print(f"JSON Import: {report['json_import']['category']} / {report['json_import']['stage']}")
    print(f"Mixed Focus: {report['mixed_focus']['category']} / {report['mixed_focus']['stage']}")
    print(f"Output: {args.output}")
    return 0


def _load_json_import_run(run_root: Path | None) -> dict[str, Any]:
    run_root = run_root or Path()
    collection = _load_json(run_root / "collection" / "dataset_metadata.json")
    import_validation = _load_json(run_root / "collection" / "import_validation.json")
    scope = _load_json(run_root / "processing" / "scope_report.json")
    reviews = _load_items(run_root / "processing" / "reviews.json", "reviews")
    requirements = _load_items(run_root / "requirement_generation" / "requirements.json", "requirements")
    roadmap = _load_json(run_root / "roadmap" / "roadmap.json")
    prd_raw = _load_json(run_root / "prd" / "prd_generation_raw.json")
    prd_payload = _parse_stage_payload(prd_raw)
    prd_validation = _load_json(run_root / "prd" / "prd_validation.json")
    return {
        "run_id": run_root.name,
        "collection": collection,
        "import_validation": import_validation,
        "scope": scope,
        "review_ids": _review_ids(reviews),
        "requirements": requirements,
        "roadmap": roadmap,
        "prds": prd_payload.get("prds") if isinstance(prd_payload.get("prds"), list) else [],
        "prd_raw": prd_raw,
        "prd_validation_status": _text(prd_validation.get("status")),
        "prd_validation_errors": _list_text(prd_validation.get("errors")),
        "input_context": {
            "collection": _collection_summary(collection),
            "scope": scope,
            "review_ids": _review_ids(reviews),
        },
        "prompt_context": {
            "analysis_goal": prd_raw.get("analysis_goal"),
            "provider": prd_raw.get("provider"),
            "model": prd_raw.get("model"),
            "requirement_ids": [_text(item.get("requirement_id")) for item in requirements],
            "version_ids": [_text(item.get("version_id")) for item in _list_dicts(roadmap.get("versions"))],
        },
        "artifact_context": {
            "prd_validation_status": prd_validation.get("status"),
            "prd_validation_errors": _list_text(prd_validation.get("errors")),
            "roadmap": roadmap,
            "requirement_titles": {
                _text(item.get("requirement_id")): _text(item.get("title")) for item in requirements
            },
        },
    }


def _load_mixed_topic_failure(run_root: Path | None) -> dict[str, Any]:
    run_root = run_root or Path()
    collection = _load_json(run_root / "collection" / "dataset_metadata.json")
    scope = _load_json(run_root / "processing" / "scope_report.json")
    reviews = _load_items(run_root / "processing" / "reviews.json", "reviews")
    selected_reviews = _load_items(run_root / "processing" / "selected_reviews.json", "reviews")
    topic_raw = _load_json(run_root / "topic_discovery" / "topic_discovery_raw.json")
    topic_validation = _load_json(run_root / "topic_discovery" / "topic_validation.json")
    processed_ids = set(_review_ids(reviews))
    selected_ids = set(_review_ids(selected_reviews)) or processed_ids
    unknown_ids = _unknown_review_ids(_list_text(topic_validation.get("errors")))
    raw_output = _text(topic_raw.get("raw_output"))
    details = [
        {
            "review_id": review_id,
            "in_processed_reviews": review_id in processed_ids,
            "in_selected_reviews": review_id in selected_ids,
            "raw_contains": review_id in raw_output,
            "raw_excerpt": _snippet_around(raw_output, review_id),
        }
        for review_id in unknown_ids
    ]
    return {
        "run_id": run_root.name,
        "analysis_goal": topic_raw.get("analysis_goal"),
        "analysis_focus": topic_raw.get("analysis_focus"),
        "provider": topic_raw.get("provider"),
        "model": topic_raw.get("model"),
        "collection_source_type": collection.get("source_type") or collection.get("provider"),
        "review_source_type": collection.get("provider"),
        "processed_review_count": len(processed_ids),
        "selected_review_count": len(selected_ids),
        "topic_validation_status": _text(topic_validation.get("status")),
        "topic_validation_errors": _list_text(topic_validation.get("errors")),
        "unknown_review_ids": unknown_ids,
        "unknown_review_details": details,
        "input_context": {
            "collection": _collection_summary(collection),
            "scope": scope,
            "processed_review_ids": sorted(processed_ids),
            "selected_review_ids": sorted(selected_ids),
        },
        "prompt_context": {
            "analysis_goal": topic_raw.get("analysis_goal"),
            "analysis_focus": topic_raw.get("analysis_focus"),
            "provider": topic_raw.get("provider"),
            "model": topic_raw.get("model"),
        },
        "artifact_context": {
            "topic_validation_status": topic_validation.get("status"),
            "topic_validation_errors": _list_text(topic_validation.get("errors")),
        },
    }


def _load_mixed_requirement_failure(run_root: Path | None) -> dict[str, Any]:
    run_root = run_root or Path()
    requirement_raw = _load_json(run_root / "requirement_generation" / "requirement_generation_raw.json")
    requirement_validation = _load_json(run_root / "requirement_generation" / "requirement_validation.json")
    findings = _load_items(run_root / "finding_generation" / "findings.json", "findings")
    recovery = requirement_raw.get("json_recovery") if isinstance(requirement_raw.get("json_recovery"), dict) else {}
    provider_response = _nested_dict(requirement_raw, ["response_metadata", "provider_response"])
    usage = provider_response.get("usage") if isinstance(provider_response.get("usage"), dict) else {}
    choices = provider_response.get("choices") if isinstance(provider_response.get("choices"), list) else []
    first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    distribution = dict(Counter(_text(item.get("finding_type")) for item in findings if _text(item.get("finding_type"))))
    problem_count = distribution.get("product_problem", 0)
    positive_count = distribution.get("positive_feedback", 0)
    return {
        "run_id": run_root.name,
        "provider": requirement_raw.get("provider"),
        "model": requirement_raw.get("model"),
        "analysis_goal": requirement_raw.get("analysis_goal"),
        "analysis_focus": requirement_raw.get("analysis_focus"),
        "requirement_generation_status": _text(requirement_raw.get("generation_status")),
        "requirement_validation_status": _text(requirement_validation.get("status")),
        "requirement_validation_errors": _list_text(requirement_validation.get("errors")),
        "raw_output_length": len(_text(requirement_raw.get("raw_output"))),
        "raw_output_start": _text(requirement_raw.get("raw_output"))[:240],
        "raw_output_end": _text(requirement_raw.get("raw_output"))[-360:],
        "finish_reason": _text(first_choice.get("finish_reason")),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "retry_attempted": recovery.get("retry_attempted") is True,
        "retry_reason": recovery.get("retry_reason"),
        "retry_success": recovery.get("retry_success") is True,
        "retry_error": recovery.get("retry_error"),
        "json_recovery": recovery,
        "finding_type_distribution": distribution,
        "problem_positive_separation": {
            "problem_finding_count": problem_count,
            "positive_feedback_finding_count": positive_count,
            "both_types_present": problem_count > 0 and positive_count > 0,
            "separation_status": "PASS" if problem_count > 0 and positive_count > 0 else "FAIL",
        },
        "input_context": {
            "finding_ids": [_text(item.get("finding_id")) for item in findings],
            "finding_types": distribution,
        },
        "prompt_context": {
            "analysis_goal": requirement_raw.get("analysis_goal"),
            "analysis_focus": requirement_raw.get("analysis_focus"),
            "provider": requirement_raw.get("provider"),
            "model": requirement_raw.get("model"),
        },
        "artifact_context": {
            "requirement_generation_status": requirement_raw.get("generation_status"),
            "requirement_validation_status": requirement_validation.get("status"),
            "requirement_validation_errors": _list_text(requirement_validation.get("errors")),
            "json_recovery": recovery,
        },
    }


def _json_artifact_isolation(run: dict[str, Any]) -> dict[str, Any]:
    collection = run["collection"]
    source_type = _text(collection.get("source_type"))
    display_source = _text(collection.get("display_source"))
    provider = _text(collection.get("provider"))
    selected_count = run["scope"].get("selected_count")
    hardcoded_terms = []
    raw_text = _text(run["prd_raw"].get("raw_output")).lower()
    for term in ["workout for women", "839285684", "workout library"]:
        if term in raw_text:
            hardcoded_terms.append(term)
    passed = (
        source_type == "json"
        and display_source == "Imported JSON"
        and provider == "json_import"
        and bool(run["review_ids"])
    )
    return {
        "passed": passed,
        "source_type": source_type,
        "display_source": display_source,
        "provider": provider,
        "selected_count": selected_count,
        "review_count": len(run["review_ids"]),
        "hardcoded_terms": hardcoded_terms,
    }


def _goal_alignment_findings(run: dict[str, Any]) -> list[dict[str, Any]]:
    versions = {
        _text(item.get("version_id")): item
        for item in _list_dicts(run["roadmap"].get("versions"))
        if _text(item.get("version_id"))
    }
    has_goal_error = any("goals" in error and "version goal" in error for error in run["prd_validation_errors"])
    findings = []
    for index, prd in enumerate(_list_dicts(run["prds"])):
        version_id = _text(prd.get("version_id"))
        version_goal = _text((versions.get(version_id) or {}).get("goal"))
        goals = _list_text(prd.get("goals"))
        first_goal = goals[0] if goals else ""
        first_goal_matches = bool(version_goal and first_goal == version_goal)
        findings.append(
            {
                "index": index,
                "prd_id": _text(prd.get("prd_id")),
                "version_id": version_id,
                "version_goal": version_goal,
                "first_goal": first_goal,
                "first_goal_matches": first_goal_matches,
                "goal_count": len(goals),
                "validator_rejected_despite_first_goal_match": has_goal_error
                and first_goal_matches
                and any(f"prds[{index}].goals" in error for error in run["prd_validation_errors"]),
            }
        )
    return findings


def _missing_open_question_findings(run: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not run:
        return []
    requirements = {
        _text(item.get("requirement_id")): item
        for item in _list_dicts(run["requirements"])
        if _text(item.get("requirement_id"))
    }
    findings = []
    for error in run["prd_validation_errors"]:
        match = re.search(r"missing product decision question for (REQ-\d+)", error)
        if not match:
            continue
        requirement_id = match.group(1)
        prd = _prd_for_requirement(run["prds"], requirement_id)
        open_question_text = " ".join(_list_text((prd or {}).get("open_questions"))).lower()
        requirement = requirements.get(requirement_id, {})
        requirement_text = " ".join([_text(requirement.get("title")), _text(requirement.get("description"))]).lower()
        contextual_terms = _contextual_terms(requirement_text)
        legacy_terms = LEGACY_OPEN_QUESTION_TERMS.get(requirement_id, [])
        findings.append(
            {
                "requirement_id": requirement_id,
                "requirement_title": _text(requirement.get("title")),
                "prd_id": _text((prd or {}).get("prd_id")),
                "open_questions": _list_text((prd or {}).get("open_questions")),
                "contextual_terms": contextual_terms,
                "legacy_terms": legacy_terms,
                "contextual_question_present": bool(contextual_terms)
                and any(term in open_question_text for term in contextual_terms),
                "legacy_question_present": bool(legacy_terms)
                and any(term in open_question_text for term in legacy_terms),
                "validator_error": error,
            }
        )
    return findings


def _contextual_terms(requirement_text: str) -> list[str]:
    terms: list[str] = []
    for trigger, candidates in CONTEXTUAL_OPEN_QUESTION_TERMS.items():
        if trigger in requirement_text:
            terms.extend(candidates)
    return sorted(set(terms))


def _prd_for_requirement(prds: Any, requirement_id: str) -> dict[str, Any] | None:
    for prd in _list_dicts(prds):
        if requirement_id in _list_text(prd.get("requirement_ids")):
            return prd
    return None


def _unknown_review_ids(errors: list[str]) -> list[str]:
    ids = []
    for error in errors:
        match = re.search(r"unknown review id ([^\s]+)", error)
        if match:
            ids.append(match.group(1))
    return ids


def _parse_stage_payload(raw: dict[str, Any]) -> dict[str, Any]:
    text = _text(raw.get("extracted_json")) or _text(raw.get("extracted_response")) or _text(raw.get("raw_output")) or _text(raw.get("raw_response"))
    if not text:
        return {}
    try:
        payload = json.loads(extract_json_text(text))
    except (json.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _collection_summary(collection: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": collection.get("source_type"),
        "display_source": collection.get("display_source"),
        "provider": collection.get("provider"),
        "app_id": collection.get("app_id"),
        "territory": collection.get("territory"),
        "record_count": collection.get("record_count") or collection.get("actual_count"),
        "valid_count": collection.get("valid_count"),
    }


def _matrix_entry(tests: list[Any], test_id: str) -> dict[str, Any]:
    for item in tests:
        if isinstance(item, dict) and item.get("id") == test_id:
            return item
    return {}


def _run_root(runs_root: Path, run_id: str) -> Path | None:
    if not run_id:
        return None
    return runs_root / run_id


def _hash_payload(*payloads: Any) -> str:
    encoded = json.dumps(payloads, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _snippet_around(text: str, needle: str, *, radius: int = 160) -> str:
    if not text or not needle:
        return ""
    index = text.find(needle)
    if index < 0:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return text[start:end]


def _nested_dict(payload: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _safe_category(category: str) -> str:
    return category if category in ALLOWED_CATEGORIES else "Unknown"


def _load_items(path: Path, key: str) -> list[dict[str, Any]]:
    payload = _load_json(path)
    items = payload.get(key)
    return _list_dicts(items)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _list_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _review_ids(reviews: list[dict[str, Any]]) -> list[str]:
    return [_text(review.get("id")) for review in reviews if _text(review.get("id"))]


def _list_text(value: Any) -> list[str]:
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
