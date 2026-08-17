"""Read-only workflow result adapters for the analysis dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.demo import DEMO_DISPLAY_SOURCE
from app.workflow.artifacts import find_run_artifact
from app.workflow.models import RunState


def reviews_payload(run: RunState) -> dict[str, Any]:
    reviews = _load_json(run, "reviews.json").get("reviews", [])
    all_reviews = _load_json(run, "reviews_all.json").get("reviews", [])
    normalized = _load_json(run, "normalized_reviews.json").get("reviews", [])
    return {
        **_base(run, bool(reviews)),
        "reviews": reviews,
        "all_reviews": all_reviews,
        "raw_reviews": normalized,
        "statistics": _load_json(run, "statistics.json"),
        "statistics_all": _load_json(run, "statistics_all.json"),
        "processing_report": _load_json(run, "processing_report.json"),
        "processing_report_all": _load_json(run, "processing_report_all.json"),
        "scope_report": _load_json(run, "scope_report.json"),
        "scope_validation": _load_json(run, "scope_validation.json"),
        "selected_reviews": _load_json(run, "selected_reviews.json").get("reviews", []),
        "dataset_metadata": _load_json(run, "dataset_metadata.json"),
    }


def topics_payload(run: RunState) -> dict[str, Any]:
    topics = _load_json(run, "topics.json").get("topics", [])
    return {
        **_base(run, bool(topics)),
        "topics": topics,
        "validation": _load_json(run, "topic_validation.json"),
        "raw": _raw_metadata(_load_json(run, "topic_discovery_raw.json")),
    }


def issues_payload(run: RunState) -> dict[str, Any]:
    payload = _load_json(run, "issues.json")
    classifications = _load_json(run, "issue_classification.json").get("classifications", [])
    eligibility = _load_json(run, "finding_eligibility.json").get("eligibility", [])
    issues = _decorate_issues(payload.get("issues", []), classifications, eligibility)
    return {
        **_base(run, bool(issues)),
        "issues": issues,
        "unmerged_topic_ids": payload.get("unmerged_topic_ids", []),
        "classifications": classifications,
        "eligibility": eligibility,
        "validation": _load_json(run, "issue_validation.json"),
        "raw": _raw_metadata(_load_json(run, "issue_consolidation_raw.json")),
    }


def findings_payload(run: RunState) -> dict[str, Any]:
    findings = _load_json(run, "findings.json").get("findings", [])
    evidence_reports = _load_json(run, "evidence_report.json").get("evidence_reports", [])
    return {
        **_base(run, bool(findings)),
        "findings": findings,
        "evidence_reports": evidence_reports,
        "validation": _load_json(run, "finding_validation.json"),
        "raw": _raw_metadata(_load_json(run, "finding_generation_raw.json")),
    }


def requirements_payload(run: RunState) -> dict[str, Any]:
    requirements = _load_json(run, "requirements.json").get("requirements", [])
    return {
        **_base(run, bool(requirements)),
        "requirements": requirements,
        "validation": _load_json(run, "requirement_validation.json"),
        "priority_report": _load_json(run, "priority_report.json").get("priority_report", []),
        "raw": _raw_metadata(_load_json(run, "requirement_generation_raw.json")),
    }


def roadmap_payload(run: RunState) -> dict[str, Any]:
    roadmap = _load_json(run, "roadmap.json")
    versions = roadmap.get("versions", [])
    return {
        **_base(run, bool(versions)),
        "versions": versions,
        "roadmap_items": roadmap.get("roadmap_items", []),
        "deferred": roadmap.get("deferred", []),
        "validation": _load_json(run, "roadmap_validation.json"),
        "raw": _raw_metadata(_load_json(run, "roadmap_generation_raw.json")),
    }


def prd_payload(run: RunState) -> dict[str, Any]:
    prds = _load_json(run, "prds.json").get("prds", [])
    return {
        **_base(run, bool(prds)),
        "prds": prds,
        "validation": _load_json(run, "prd_validation.json"),
        "raw": _raw_metadata(_load_json(run, "prd_generation_raw.json")),
    }


def test_cases_payload(run: RunState) -> dict[str, Any]:
    test_cases = _load_json(run, "test_cases.json").get("test_cases", [])
    return {
        **_base(run, bool(test_cases)),
        "test_cases": test_cases,
        "validation": _load_json(run, "test_case_validation.json"),
        "coverage": _load_json(run, "test_coverage.json"),
        "raw": _raw_metadata(_load_json(run, "test_case_generation_raw.json")),
    }


def traceability_payload(run: RunState) -> dict[str, Any]:
    reviews = reviews_payload(run).get("reviews", [])
    topics = topics_payload(run).get("topics", [])
    issues = issues_payload(run).get("issues", [])
    findings = findings_payload(run).get("findings", [])
    requirements = requirements_payload(run).get("requirements", [])
    roadmap = roadmap_payload(run)
    prds = prd_payload(run).get("prds", [])
    test_cases = test_cases_payload(run).get("test_cases", [])
    validation = _load_json(run, "final_validation_report.json")
    graph = _traceability_graph(
        reviews=reviews,
        topics=topics,
        issues=issues,
        findings=findings,
        requirements=requirements,
        versions=roadmap.get("versions", []),
        prds=prds,
        test_cases=test_cases,
    )
    return {
        **_base(run, bool(validation)),
        "validation": validation,
        "graph": graph,
        "metadata": _model_metadata(validation),
    }


def validation_payload(run: RunState) -> dict[str, Any]:
    traceability = traceability_payload(run)
    validation = traceability.get("validation", {})
    return {
        **_base(run, bool(validation)),
        "runtime_validation_status": validation.get("runtime_validation_status", run.runtime_validation_status),
        "submission_validation_status": validation.get("submission_validation_status", run.submission_validation_status),
        "submission_blockers": validation.get("submission_blockers", []),
        "validation": validation,
        "metadata": traceability.get("metadata", {}),
    }


def errors_payload(run: RunState) -> dict[str, Any]:
    errors = [_diagnostic_error(run, error.to_dict()) for error in run.errors]
    return {
        **_base(run, bool(errors)),
        "errors": errors,
        "failure_propagation": _failure_propagation(run),
    }


def warnings_payload(run: RunState) -> dict[str, Any]:
    warnings = [_diagnostic_warning(run, warning.to_dict()) for warning in run.warnings]
    return {
        **_base(run, bool(warnings)),
        "warnings": warnings,
    }


def revisions_payload(run: RunState) -> dict[str, Any]:
    revisions = [_diagnostic_revision(run, revision.to_dict()) for revision in run.revisions]
    return {
        **_base(run, bool(revisions)),
        "revisions": revisions,
    }


def metadata_payload(run: RunState) -> dict[str, Any]:
    review_payload = reviews_payload(run)
    dataset = review_payload.get("dataset_metadata", {})
    scope_report = review_payload.get("scope_report", {})
    scope_constraint = scope_report.get("constraint") if isinstance(scope_report, dict) else {}
    validation = validation_payload(run)
    collection = _stage_by_id(run, "collection")
    import_metadata = run.import_metadata or {}
    imported = run.source_type in {"json", "csv"}
    demo_metadata = run.demo_metadata or {}
    is_demo = run.is_demo or run.data_source == "cached_demo"
    display_source = (
        (DEMO_DISPLAY_SOURCE if is_demo else None)
        or
        import_metadata.get("display_source")
        or dataset.get("display_source")
        or ("Imported JSON" if run.source_type == "json" else "Imported CSV" if run.source_type == "csv" else None)
    )
    return {
        **_base(run, True),
        "data": {
            "source_type": run.data_source or run.source_type,
            "display_source": display_source or dataset.get("provider") or _summary_value(collection, "provider"),
            "review_source": display_source or dataset.get("provider") or _summary_value(collection, "provider"),
            "app_context": run.app_url,
            "artifact_source": "Built-in Demo Cache" if is_demo else dataset.get("artifact_source") or ("Uploaded File" if imported else "Run Artifact Snapshot"),
            "cached_label": DEMO_DISPLAY_SOURCE if is_demo else dataset.get("cached_label") or (None if imported else "Cached for this Run"),
            "provider": dataset.get("provider") or demo_metadata.get("source_provider") or _summary_value(collection, "provider"),
            "filename": dataset.get("filename") or import_metadata.get("filename"),
            "territory": dataset.get("territory") or import_metadata.get("territory") or demo_metadata.get("territory") or _summary_value(collection, "territory") or (run.storefront if not imported else None),
            "app_id": dataset.get("app_id") or demo_metadata.get("app_id") or _summary_value(collection, "app_id") or run.app_id,
            "collection_time": dataset.get("retrieved_at") or demo_metadata.get("collected_at") or dataset.get("imported_at") or (collection.completed_at if collection else None),
            "imported_at": dataset.get("imported_at") or import_metadata.get("imported_at"),
            "requested_limit": dataset.get("requested_limit") or _summary_value(collection, "requested_limit"),
            "record_count": dataset.get("record_count") or import_metadata.get("record_count"),
            "valid_count": dataset.get("valid_count") or import_metadata.get("valid_count"),
            "invalid_count": dataset.get("invalid_count") or import_metadata.get("invalid_count"),
            "actual_count": dataset.get("actual_count") or demo_metadata.get("review_count") or _summary_value(collection, "actual_count"),
            "analysis_constraints": run.constraints or scope_constraint or {},
            "reviews_collected": dataset.get("actual_count") or demo_metadata.get("review_count") or _summary_value(collection, "actual_count") or scope_report.get("input_count"),
            "reviews_in_scope": scope_report.get("selected_count"),
            "reviews_excluded_by_constraint": scope_report.get("excluded_count"),
            "scope_validation": review_payload.get("scope_validation", {}),
            "limitations": _demo_limitations(demo_metadata) if is_demo else dataset.get("limitations") or import_metadata.get("limitations") or _summary_value(collection, "limitations") or [],
            "is_demo": is_demo,
            "mode": demo_metadata.get("mode") if is_demo else None,
        },
        "model": validation.get("metadata", {}),
        "validation": {
            "runtime_validation_status": validation.get("runtime_validation_status"),
            "submission_validation_status": validation.get("submission_validation_status"),
            "submission_blockers": validation.get("submission_blockers", []),
        },
    }


def _base(run: RunState, available: bool) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "available": available,
        "source": "cached_demo" if run.is_demo else "run_artifact_snapshot",
        "run_status": run.status,
        "is_demo": run.is_demo,
    }


def _diagnostic_error(run: RunState, error: dict[str, Any]) -> dict[str, Any]:
    stage = _stage_by_id(run, error.get("stage"))
    return {
        "category": "Error",
        "stage": error.get("stage"),
        "type": error.get("type"),
        "message": error.get("message"),
        "recoverable": error.get("recoverable"),
        "timestamp": _stage_timestamp(stage) or run.updated_at,
    }


def _diagnostic_warning(run: RunState, warning: dict[str, Any]) -> dict[str, Any]:
    stage = _stage_by_id(run, warning.get("stage"))
    return {
        "category": "Warning",
        "stage": warning.get("stage"),
        "type": warning.get("type"),
        "message": warning.get("message"),
        "blocking": False,
        "timestamp": _stage_timestamp(stage) or run.updated_at,
    }


def _diagnostic_revision(run: RunState, revision: dict[str, Any]) -> dict[str, Any]:
    stage = _stage_by_id(run, revision.get("stage"))
    return {
        "category": "Revision",
        "revision_id": revision.get("revision_id"),
        "stage": revision.get("stage"),
        "reason": revision.get("reason"),
        "status": revision.get("status"),
        "timestamp": _stage_timestamp(stage) or run.updated_at,
    }


def _failure_propagation(run: RunState) -> dict[str, Any]:
    failed_stage = next((stage for stage in run.stages if stage.status == "failed"), None)
    skipped = [stage.stage for stage in run.stages if stage.status == "skipped"]
    if not failed_stage:
        return {
            "has_failure": False,
            "failed_stage": None,
            "skipped_stages": skipped,
            "message": None,
        }
    return {
        "has_failure": True,
        "failed_stage": failed_stage.stage,
        "skipped_stages": skipped,
        "message": f"由于 {failed_stage.label_en} 阶段失败，后续阶段未执行。",
    }


def _stage_by_id(run: RunState, stage_id: Any):
    if not isinstance(stage_id, str):
        return None
    return next((stage for stage in run.stages if stage.stage == stage_id), None)


def _stage_timestamp(stage) -> str | None:
    if not stage:
        return None
    return stage.completed_at or stage.started_at


def _summary_value(stage, key: str) -> Any:
    if not stage:
        return None
    return stage.summary.get(key)


def _load_json(run: RunState, filename: str) -> dict[str, Any]:
    artifact_paths = [artifact for stage in run.stages for artifact in stage.artifacts]
    path = find_run_artifact(run.run_id, artifact_paths, filename)
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _raw_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key
        in {
            "generated_at",
            "retrieved_at",
            "provider",
            "model",
            "phase",
            "is_mock",
            "analysis_goal",
            "generation_status",
            "status",
            "response_metadata",
        }
    }


def _decorate_issues(
    issues: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
    eligibility: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    types = {item.get("issue_id"): item.get("issue_type") for item in classifications}
    eligible = {item.get("issue_id"): item.get("eligible_for_finding") for item in eligibility}
    decorated = []
    for issue in issues:
        issue_id = issue.get("issue_id")
        decorated.append(
            {
                **issue,
                "issue_type": issue.get("issue_type") or types.get(issue_id),
                "eligible_for_finding": eligible.get(issue_id),
            }
        )
    return decorated


def _traceability_graph(
    *,
    reviews: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    versions: list[dict[str, Any]],
    prds: list[dict[str, Any]],
    test_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    review_ids = [_text(review.get("id")) for review in reviews if _text(review.get("id"))]
    topic_to_reviews = {_text(topic.get("topic_id")): _list_text(topic.get("review_ids")) for topic in topics}
    issue_to_topics = {_text(issue.get("issue_id")): _list_text(issue.get("topic_ids")) for issue in issues}
    issue_to_reviews = {_text(issue.get("issue_id")): _list_text(issue.get("review_ids")) for issue in issues}
    finding_to_issues = {
        _text(finding.get("finding_id")): _list_text(finding.get("issue_ids")) for finding in findings
    }
    finding_to_reviews = {
        _text(finding.get("finding_id")): _list_text(finding.get("review_ids")) for finding in findings
    }
    requirement_to_findings = {
        _text(requirement.get("requirement_id")): _list_text(requirement.get("finding_ids"))
        for requirement in requirements
    }
    version_to_requirements = {
        _text(version.get("version_id")): _list_text(version.get("requirement_ids")) for version in versions
    }
    prd_to_requirements = {_text(prd.get("prd_id")): _list_text(prd.get("requirement_ids")) for prd in prds}
    test_case_to_requirement = {
        _text(test_case.get("test_case_id")): _text(test_case.get("requirement_id")) for test_case in test_cases
    }
    test_case_to_reviews = {
        _text(test_case.get("test_case_id")): _list_text(test_case.get("source_review_ids")) for test_case in test_cases
    }
    return {
        "review_ids": review_ids,
        "topic_to_reviews": topic_to_reviews,
        "issue_to_topics": issue_to_topics,
        "issue_to_reviews": issue_to_reviews,
        "finding_to_issues": finding_to_issues,
        "finding_to_reviews": finding_to_reviews,
        "requirement_to_findings": requirement_to_findings,
        "version_to_requirements": version_to_requirements,
        "prd_to_requirements": prd_to_requirements,
        "test_case_to_requirement": test_case_to_requirement,
        "test_case_to_reviews": test_case_to_reviews,
        "review_to_topics": _invert_many(topic_to_reviews),
        "topic_to_issues": _invert_many(issue_to_topics),
        "issue_to_findings": _invert_many(finding_to_issues),
        "finding_to_requirements": _invert_many(requirement_to_findings),
        "requirement_to_versions": _invert_many(version_to_requirements),
        "requirement_to_prds": _invert_many(prd_to_requirements),
        "requirement_to_test_cases": _invert_one(test_case_to_requirement),
        "review_to_test_cases": _invert_many(test_case_to_reviews),
    }


def _model_metadata(validation: dict[str, Any]) -> dict[str, Any]:
    registry = validation.get("model_registry")
    if not isinstance(registry, list):
        return {}
    models = []
    for item in registry:
        if not isinstance(item, dict):
            continue
        configuration = item.get("configuration") if isinstance(item.get("configuration"), dict) else {}
        thinking = configuration.get("thinking")
        if isinstance(thinking, dict):
            thinking_value = thinking.get("type")
        else:
            thinking_value = thinking
        models.append(
            {
                "task": item.get("task"),
                "provider": item.get("provider"),
                "model": item.get("model"),
                "thinking": thinking_value,
                "max_tokens": configuration.get("max_tokens"),
                "temperature": configuration.get("temperature"),
                "stream": configuration.get("stream"),
                "timeout_seconds": configuration.get("timeout_seconds"),
                "response_format": configuration.get("response_format"),
            }
        )
    return {"model_registry": models}


def _invert_many(mapping: dict[str, list[str]]) -> dict[str, list[str]]:
    inverted: dict[str, list[str]] = {}
    for parent, children in mapping.items():
        for child in children:
            inverted.setdefault(child, []).append(parent)
    return inverted


def _invert_one(mapping: dict[str, str]) -> dict[str, list[str]]:
    inverted: dict[str, list[str]] = {}
    for parent, child in mapping.items():
        if child:
            inverted.setdefault(child, []).append(parent)
    return inverted


def _list_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _demo_limitations(metadata: dict[str, Any]) -> list[str]:
    limitations = [
        "Cached demo result for offline interview presentation; not a live collection or model run.",
        "Live Analysis must be selected to process a new app, new review file, or new analysis goal.",
    ]
    description = metadata.get("description")
    if isinstance(description, str) and description and description not in limitations:
        limitations.append(description)
    return limitations
