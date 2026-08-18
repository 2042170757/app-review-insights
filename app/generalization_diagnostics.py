"""Read-only diagnostics for Phase 10c generalization pipeline failures."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.finding_generation import build_finding_request
from app.prd_generator import SYSTEM_PROMPT as PRD_SYSTEM_PROMPT
from app.prd_generator import build_prd_request
from app.prd_validator import _is_measurable_metric
from app.roadmap_planner import SYSTEM_PROMPT as ROADMAP_SYSTEM_PROMPT
from app.roadmap_planner import build_roadmap_request
from app.topic_discovery import extract_json_text
from app.version_schema import VALID_VERSION_IDS


DEFAULT_OUTPUT_DIR = Path("artifacts/final_validation")


def diagnose_unknown_app_roadmap(run_root: Path) -> dict[str, Any]:
    requirements = _load_items(run_root / "requirement_generation" / "requirements.json", "requirements")
    priority_report = _load_json(run_root / "requirement_generation" / "priority_report.json")
    evidence_report = _load_json(run_root / "finding_generation" / "evidence_report.json")
    raw = _load_json(run_root / "roadmap" / "roadmap_generation_raw.json")
    validation = _load_json(run_root / "roadmap" / "roadmap_validation.json")
    raw_payload = _parse_stage_payload(raw)
    generated_versions = raw_payload.get("versions") if isinstance(raw_payload, dict) else []
    generated_version_ids = [
        item.get("version_id")
        for item in generated_versions
        if isinstance(item, dict) and isinstance(item.get("version_id"), str)
    ]
    generated_invalid_version_ids = [
        version_id for version_id in generated_version_ids if version_id not in VALID_VERSION_IDS
    ]
    request = build_roadmap_request(
        requirements=requirements,
        priority_report=priority_report,
        evidence_report=evidence_report,
        existing_dependencies_by_requirement_id={},
        analysis_goal=_text(raw.get("analysis_goal")),
    )
    prompt_payload = _loads_object(request.user_prompt)
    prompt_text = f"{request.system_prompt}\n{request.user_prompt}"
    prompt_mentions_allowed_ids = all(version_id in prompt_text for version_id in ["V1", "V2", "V3"])
    prompt_mentions_max_count = bool(re.search(r"max(?:imum)?\s+3|at most\s+3|最多\s*3", prompt_text, re.IGNORECASE))
    prompt_has_explicit_version_rule = prompt_mentions_allowed_ids and prompt_mentions_max_count
    expected_version_ids = sorted(version_id for version_id in VALID_VERSION_IDS if version_id != "Deferred")
    expected_version_count = len(expected_version_ids)
    schema_rule = (
        "Version.version_id must be one of "
        f"{sorted(VALID_VERSION_IDS)}; scheduled versions are expected to use {expected_version_ids}."
    )
    if generated_invalid_version_ids:
        root_cause = (
            "Roadmap model output included version IDs outside the Version schema. "
            "The validator is aligned with schema; the prompt does not explicitly enumerate the max scheduled "
            "version count and valid version_id enum strongly enough."
        )
        classification = "Prompt Context Issue"
    else:
        root_cause = "No invalid version ID was found in the Roadmap model output."
        classification = "Expected Limitation"
    return {
        "generated_at": _now(),
        "run_root": str(run_root),
        "version_schema_rule": schema_rule,
        "version_schema_allows_v4": "V4" in VALID_VERSION_IDS,
        "roadmap_planner_has_max_version_limit": prompt_has_explicit_version_rule,
        "expected_version_count": expected_version_count,
        "expected_version_count_source": "app.version_schema.VALID_VERSION_IDS excluding Deferred",
        "roadmap_input_requirement_ids": [item.get("requirement_id") for item in requirements],
        "requirements_count": len(requirements),
        "generated_version_ids": generated_version_ids,
        "generated_invalid_version_ids": generated_invalid_version_ids,
        "generated_version_count": len(generated_version_ids),
        "validator_error": "; ".join(_list_text(validation.get("errors"))),
        "validator_status": validation.get("status"),
        "roadmap_prompt_constraints": _roadmap_prompt_constraints(prompt_payload, prompt_has_explicit_version_rule),
        "roadmap_prompt_explicitly_defines_version_ids": prompt_mentions_allowed_ids,
        "roadmap_prompt_explicitly_defines_max_version_count": prompt_mentions_max_count,
        "generator_or_validator": "Generator/prompt issue; Validator correctly rejects V4 against schema."
        if generated_invalid_version_ids
        else "No schema mismatch found.",
        "diagnosis_category": classification,
        "suspected_root_cause": root_cause,
    }


def diagnose_json_prd_metric(run_root: Path, *, problem_focus_run_root: Path | None = None) -> dict[str, Any]:
    requirements = _load_items(run_root / "requirement_generation" / "requirements.json", "requirements")
    roadmap = _load_json(run_root / "roadmap" / "roadmap.json")
    findings = _load_items(run_root / "finding_generation" / "findings.json", "findings")
    evidence_report = _load_json(run_root / "finding_generation" / "evidence_report.json")
    raw = _load_json(run_root / "prd" / "prd_generation_raw.json")
    validation = _load_json(run_root / "prd" / "prd_validation.json")
    raw_payload = _parse_stage_payload(raw)
    prds = raw_payload.get("prds") if isinstance(raw_payload, dict) else []
    invalid_metrics = _invalid_metrics_from_validation(prds, validation)
    request = build_prd_request(
        requirements=requirements,
        roadmap=roadmap,
        findings=findings,
        evidence_report=evidence_report,
        analysis_goal=_text(raw.get("analysis_goal")),
    )
    prompt_text = f"{PRD_SYSTEM_PROMPT}\n{request.user_prompt}"
    prompt_warns_about_invalid_metrics = any(metric["metric"] in prompt_text for metric in invalid_metrics)
    baseline = _problem_focus_prd_baseline(problem_focus_run_root)
    if invalid_metrics and all(not metric["is_measurable_by_validator"] for metric in invalid_metrics):
        root_cause = (
            "PRD model generated vague success metric wording that the validator rejects as non-measurable. "
            "The metric is not supported as a concrete rate/count/score/rating/survey signal."
        )
        classification = "Generator Bug"
        diagnosis_choice = "A. Generator still generated vague metric"
    elif invalid_metrics:
        root_cause = "PRD validator rejected a metric that appears measurable by the current metric heuristic."
        classification = "Validator Bug"
        diagnosis_choice = "B. Validator may be misclassifying a measurement concept"
    else:
        root_cause = "No invalid success metric was found in the PRD raw payload."
        classification = "Expected Limitation"
        diagnosis_choice = "C. No metric failure found in this run"
    return {
        "generated_at": _now(),
        "run_root": str(run_root),
        "analysis_goal": raw.get("analysis_goal"),
        "analysis_focus": _infer_analysis_focus(requirements, findings),
        "requirement_ids": [item.get("requirement_id") for item in requirements],
        "requirement_summaries": [
            {
                "requirement_id": item.get("requirement_id"),
                "title": item.get("title"),
                "acceptance_criteria_count": len(_list_text(item.get("acceptance_criteria"))),
                "success_metrics": _list_text(item.get("success_metrics")),
            }
            for item in requirements
        ],
        "roadmap_versions": [
            {
                "version_id": item.get("version_id"),
                "goal": item.get("goal"),
                "requirement_ids": _list_text(item.get("requirement_ids")),
            }
            for item in roadmap.get("versions", [])
            if isinstance(item, dict)
        ],
        "prd_success_metrics": [
            {
                "prd_id": item.get("prd_id"),
                "version_id": item.get("version_id"),
                "success_metrics": _list_text(item.get("success_metrics")),
            }
            for item in prds
            if isinstance(item, dict)
        ],
        "invalid_metrics": invalid_metrics,
        "prd_validator_status": validation.get("status"),
        "prd_validator_errors": _list_text(validation.get("errors")),
        "prompt_contains_success_metric_rule": "success_metric_rule" in request.user_prompt,
        "prompt_warns_about_invalid_metric_text": prompt_warns_about_invalid_metrics,
        "problem_focus_baseline": baseline,
        "diagnosis_choice": diagnosis_choice,
        "diagnosis_category": classification,
        "suspected_root_cause": root_cause,
    }


def diagnose_csv_finding(run_root: Path) -> dict[str, Any]:
    processing = _load_json(run_root / "processing" / "statistics.json")
    scope = _load_json(run_root / "processing" / "scope_report.json")
    topics = _load_items(run_root / "topic_discovery" / "topics.json", "topics")
    issues = _load_items(run_root / "issue_consolidation" / "issues.json", "issues")
    classification_payload = _load_json(run_root / "issue_consolidation" / "issue_classification.json")
    eligibility_payload = _load_json(run_root / "issue_consolidation" / "finding_eligibility.json")
    classifications = classification_payload.get("classifications", [])
    eligibility = eligibility_payload.get("eligibility", [])
    raw = _load_json(run_root / "finding_generation" / "finding_generation_raw.json")
    raw_payload = _parse_stage_payload(raw)
    raw_findings = raw_payload.get("findings") if isinstance(raw_payload, dict) else []
    findings = _load_items(run_root / "finding_generation" / "findings.json", "findings")
    evidence_report = _load_items(run_root / "finding_generation" / "evidence_report.json", "evidence_reports")
    validation = _load_json(run_root / "finding_generation" / "finding_validation.json")
    issue_type_distribution = dict(Counter(_text(item.get("issue_type")) for item in classifications if isinstance(item, dict)))
    eligible_items = [item for item in eligibility if isinstance(item, dict) and item.get("eligible_for_finding") is True]
    ineligible_items = [item for item in eligibility if isinstance(item, dict) and item.get("eligible_for_finding") is not True]
    analysis_focus = _text(classification_payload.get("analysis_focus") or eligibility_payload.get("analysis_focus") or raw.get("analysis_focus"))
    positive_text_issue_ids = _positive_text_issue_ids(issues)
    request = build_finding_request(
        reviews=[],
        issues=issues,
        classifications=classifications if isinstance(classifications, list) else [],
        eligibility=eligibility if isinstance(eligibility, list) else [],
        analysis_goal=_text(raw.get("analysis_goal")),
        analysis_focus=analysis_focus or "problem_analysis",
    )
    if analysis_focus == "positive_feedback_analysis" and not issue_type_distribution.get("positive_feedback") and positive_text_issue_ids:
        root_cause = (
            "Issue descriptions contain positive feedback language, but deterministic issue classification produced "
            "no positive_feedback issues. Finding eligibility therefore had zero eligible issues and the generator "
            "returned an empty finding list."
        )
        classification = "Expected Limitation"
    elif not eligible_items and raw_findings == []:
        root_cause = "No eligible issues reached Finding Generation; empty findings are an expected downstream result."
        classification = "Data Insufficiency"
    elif raw_findings and not findings:
        root_cause = "Finding Generator returned findings, but Finding Validator rejected them."
        classification = "Validator Bug"
    else:
        root_cause = "Finding stage did not show an eligibility or validation mismatch."
        classification = "Expected Limitation"
    return {
        "generated_at": _now(),
        "run_root": str(run_root),
        "analysis_goal": raw.get("analysis_goal"),
        "analysis_focus": analysis_focus,
        "review_count": _first_number(processing, ["total", "input_count"]) or scope.get("input_count"),
        "in_scope_count": scope.get("selected_count") or processing.get("total"),
        "topic_count": len(topics),
        "issue_count": len(issues),
        "issue_type_distribution": issue_type_distribution,
        "eligible_issue_count": len(eligible_items),
        "ineligible_issue_count": len(ineligible_items),
        "finding_raw_count": len(raw_findings) if isinstance(raw_findings, list) else 0,
        "finding_valid_count": len(findings),
        "evidence_report_count": len(evidence_report),
        "finding_validation_status": validation.get("status"),
        "finding_validation_errors": _list_text(validation.get("errors")),
        "all_issues_positive_feedback": bool(issue_type_distribution)
        and set(issue_type_distribution) == {"positive_feedback"},
        "all_issues_neutral_observation": bool(issue_type_distribution)
        and set(issue_type_distribution) == {"neutral_observation"},
        "problem_issues_exist_but_ineligible_by_focus": bool(issue_type_distribution.get("problem"))
        and analysis_focus == "positive_feedback_analysis",
        "finding_generator_returned_empty": raw_findings == [],
        "finding_generator_returned_rejected_results": bool(raw_findings) and not findings,
        "evidence_empty": not evidence_report,
        "support_count_anomaly": _support_count_anomaly(raw_findings, evidence_report),
        "positive_feedback_issue_ids": [
            item.get("issue_id")
            for item in classifications
            if isinstance(item, dict) and item.get("issue_type") == "positive_feedback"
        ],
        "positive_text_issue_ids": positive_text_issue_ids,
        "finding_prompt_eligible_issue_count": len(_loads_object(request.user_prompt).get("eligible_issues", [])),
        "diagnosis_category": classification,
        "suspected_root_cause": root_cause,
    }


def write_diagnostic_reports(
    *,
    unknown_app_run_root: Path,
    json_run_root: Path,
    csv_run_root: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    problem_focus_run_root: Path | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = {
        "unknown_app_roadmap": diagnose_unknown_app_roadmap(unknown_app_run_root),
        "json_prd_metric": diagnose_json_prd_metric(json_run_root, problem_focus_run_root=problem_focus_run_root),
        "csv_finding": diagnose_csv_finding(csv_run_root),
    }
    paths = {
        "unknown_app_roadmap": output_dir / "unknown_app_roadmap_diagnosis.json",
        "json_prd_metric": output_dir / "json_prd_metric_diagnosis.json",
        "csv_finding": output_dir / "csv_finding_diagnosis.json",
    }
    for key, path in paths.items():
        path.write_text(json.dumps(reports[key], ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 10c.5d read-only diagnostic reports.")
    parser.add_argument("--unknown-app-run", type=Path, default=_latest_run("unknown_app_compact_retry"))
    parser.add_argument("--json-run", type=Path, default=_latest_run("json_import_final"))
    parser.add_argument("--csv-run", type=Path, default=_latest_run("csv_import_final"))
    parser.add_argument("--problem-focus-run", type=Path, default=_latest_problem_focus_run())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    paths = write_diagnostic_reports(
        unknown_app_run_root=args.unknown_app_run,
        json_run_root=args.json_run,
        csv_run_root=args.csv_run,
        output_dir=args.output_dir,
        problem_focus_run_root=args.problem_focus_run,
    )
    print("Generalization Diagnostics: PASS")
    for key, path in paths.items():
        print(f"{key}: {path}")
    return 0


def _latest_run(category: str) -> Path:
    parent = Path("artifacts/final_validation/phase10c5c_runs") / category
    candidates = [path for path in parent.iterdir() if path.is_dir()] if parent.exists() else []
    if not candidates:
        return parent
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _latest_problem_focus_run() -> Path | None:
    parent = Path("artifacts/final_validation/phase10c5a_runs/problem_focus")
    candidates = [path for path in parent.iterdir() if path.is_dir()] if parent.exists() else []
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _roadmap_prompt_constraints(prompt_payload: dict[str, Any], explicit_version_rule: bool) -> list[str]:
    constraints = [
        "System prompt requires product-goal grouping, no new Requirements, no empty Versions.",
        "System prompt does not create a numeric max-version rule by itself.",
    ]
    schema = prompt_payload.get("required_output_schema", {})
    version_example = None
    if isinstance(schema, dict):
        versions = schema.get("versions")
        if isinstance(versions, list) and versions and isinstance(versions[0], dict):
            version_example = versions[0].get("version_id")
    if version_example:
        constraints.append(f"Prompt schema example includes version_id={version_example!r}.")
    if explicit_version_rule:
        constraints.append("Prompt explicitly enumerates V1/V2/V3 and max version count.")
    else:
        constraints.append("Prompt does not explicitly enumerate allowed scheduled Version IDs and max count.")
    if "product goals" in ROADMAP_SYSTEM_PROMPT.lower():
        constraints.append("Prompt says Roadmap should be organized by product goals rather than priority buckets.")
    return constraints


def _invalid_metrics_from_validation(prds: Any, validation: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(prds, list):
        return []
    results = []
    for error in _list_text(validation.get("success_metric_errors") or validation.get("errors")):
        match = re.search(r"prds\[(\d+)\]\.success_metrics\[(\d+)\]", error)
        if not match:
            continue
        prd_index = int(match.group(1))
        metric_index = int(match.group(2))
        metric = ""
        if prd_index < len(prds) and isinstance(prds[prd_index], dict):
            metrics = _list_text(prds[prd_index].get("success_metrics"))
            if metric_index < len(metrics):
                metric = metrics[metric_index]
        results.append(
            {
                "prd_index": prd_index,
                "metric_index": metric_index,
                "metric": metric,
                "validator_error": error,
                "is_measurable_by_validator": _is_measurable_metric(metric) if metric else False,
            }
        )
    return results


def _problem_focus_prd_baseline(run_root: Path | None) -> dict[str, Any]:
    if not run_root:
        return {"available": False}
    validation_path = run_root / "prd" / "prd_validation.json"
    raw_path = run_root / "prd" / "prd_generation_raw.json"
    if not validation_path.exists() or not raw_path.exists():
        return {"available": False, "run_root": str(run_root)}
    validation = _load_json(validation_path)
    raw_payload = _parse_stage_payload(_load_json(raw_path))
    prds = raw_payload.get("prds") if isinstance(raw_payload, dict) else []
    return {
        "available": True,
        "run_root": str(run_root),
        "validation_status": validation.get("status"),
        "validation_passed": validation.get("passed"),
        "prd_count": len(prds) if isinstance(prds, list) else 0,
        "success_metric_error_count": len(_list_text(validation.get("success_metric_errors"))),
    }


def _parse_stage_payload(raw: dict[str, Any]) -> dict[str, Any]:
    text = _text(raw.get("extracted_json")) or _text(raw.get("raw_output")) or _text(raw.get("raw_response"))
    if not text:
        return {}
    try:
        extracted = extract_json_text(text)
        payload = json.loads(extracted)
    except (json.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _positive_text_issue_ids(issues: list[dict[str, Any]]) -> list[str]:
    positive_terms = ("value", "appreciate", "helpful", "motivator", "useful", "enjoy", "love", "worth")
    result = []
    for issue in issues:
        text = " ".join(
            [
                _text(issue.get("name")),
                _text(issue.get("description")),
                _text(issue.get("merge_rationale")),
            ]
        ).lower()
        if any(term in text for term in positive_terms):
            result.append(_text(issue.get("issue_id")))
    return [item for item in result if item]


def _support_count_anomaly(raw_findings: Any, evidence_reports: list[dict[str, Any]]) -> bool:
    if isinstance(raw_findings, list):
        for finding in raw_findings:
            if not isinstance(finding, dict):
                continue
            review_ids = _list_text(finding.get("review_ids"))
            support_count = finding.get("support_count")
            if isinstance(support_count, int) and support_count != len(set(review_ids)):
                return True
    for report in evidence_reports:
        support_count = report.get("support_count")
        unique_support_count = report.get("unique_support_count")
        if isinstance(support_count, int) and isinstance(unique_support_count, int):
            if support_count < unique_support_count:
                return True
    return False


def _infer_analysis_focus(requirements: list[dict[str, Any]], findings: list[dict[str, Any]]) -> str:
    types = {
        _text(item.get("requirement_type"))
        for item in requirements
        if isinstance(item, dict) and _text(item.get("requirement_type"))
    }
    finding_types = {
        _text(item.get("finding_type"))
        for item in findings
        if isinstance(item, dict) and _text(item.get("finding_type"))
    }
    if types == {"positive_feedback"} or finding_types == {"positive_feedback"}:
        return "positive_feedback_analysis"
    if "positive_feedback" in types or "positive_feedback" in finding_types:
        return "mixed_analysis"
    return "problem_analysis"


def _first_number(payload: dict[str, Any], keys: list[str]) -> int | float | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def _loads_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_items(path: Path, key: str) -> list[dict[str, Any]]:
    payload = _load_json(path)
    items = payload.get(key)
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _list_text(value: Any) -> list[str]:
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
