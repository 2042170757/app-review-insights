"""Read-only diagnosis for main-sample PRD success metric failures."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.prd_generator import build_prd_request
from app.prd_validator import _is_measurable_metric


DEFAULT_ANALYSIS_DIR = Path("artifacts/analysis")
DEFAULT_OUTPUT_PATH = Path("artifacts/final_validation/main_prd_metric_diagnosis.json")


def diagnose_main_prd_metric_failure(
    *,
    analysis_dir: Path = DEFAULT_ANALYSIS_DIR,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    raw = _load_json(analysis_dir / "prd_generation_raw.json")
    validation = _load_json(analysis_dir / "prd_validation.json")
    prds = _load_prds(analysis_dir, raw)
    roadmap = _load_json(analysis_dir / "roadmap.json")
    requirements = _load_json(analysis_dir / "requirements.json").get("requirements", [])
    findings = _load_json(analysis_dir / "findings.json").get("findings", [])
    evidence_report = _load_json(analysis_dir / "evidence_report.json")

    failure = _first_metric_failure(validation.get("errors", []))
    prd = prds[failure["prd_index"]] if failure and failure["prd_index"] < len(prds) else {}
    failed_metric = ""
    if failure and failure["metric_index"] < len(prd.get("success_metrics", [])):
        failed_metric = prd["success_metrics"][failure["metric_index"]]
    version = _by_id(roadmap.get("versions", []), "version_id").get(prd.get("version_id"), {})
    requirement_ids = _list_text(prd.get("requirement_ids"))
    related_requirements = [
        requirement
        for requirement in requirements
        if isinstance(requirement, dict) and requirement.get("requirement_id") in requirement_ids
    ]
    request = build_prd_request(
        requirements=requirements if isinstance(requirements, list) else [],
        roadmap=roadmap,
        findings=findings if isinstance(findings, list) else [],
        evidence_report=evidence_report,
        analysis_goal=raw.get("analysis_goal") or "",
    )
    prompt_payload = json.loads(request.user_prompt)
    prompt_version = _by_id(prompt_payload.get("validated_versions", []), "version_id").get(prd.get("version_id"), {})

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "prd_id": prd.get("prd_id"),
        "version_id": prd.get("version_id"),
        "version_goal": version.get("goal"),
        "requirement_ids": requirement_ids,
        "failed_metric": failed_metric,
        "failed_metric_path": failure.get("path") if failure else None,
        "metric_classification": _classify_metric(failed_metric),
        "root_cause": _root_cause(failed_metric),
        "validation_errors": validation.get("errors", []),
        "success_metrics": _list_text(prd.get("success_metrics")),
        "open_questions": _list_text(prd.get("open_questions")),
        "analysis_goal": raw.get("analysis_goal"),
        "analysis_focus": _infer_analysis_focus(related_requirements),
        "provider": raw.get("provider"),
        "model": raw.get("model"),
        "max_tokens": _metadata(raw).get("max_tokens"),
        "temperature": _metadata(raw).get("temperature"),
        "thinking": _metadata(raw).get("thinking"),
        "prompt_context": {
            "version_goal": prompt_version.get("goal"),
            "validated_success_metric_candidates": prompt_version.get("validated_success_metric_candidates", []),
            "unsupported_success_metric_candidates": prompt_version.get("unsupported_success_metric_candidates", []),
            "requirements": [
                {
                    "requirement_id": requirement.get("requirement_id"),
                    "title": requirement.get("title"),
                    "success_metrics": _list_text(requirement.get("success_metrics")),
                    "validated_success_metric_candidates": _list_text(
                        _prompt_requirement(prompt_version, requirement.get("requirement_id")).get(
                            "validated_success_metric_candidates"
                        )
                    ),
                    "unsupported_success_metric_candidates": _list_text(
                        _prompt_requirement(prompt_version, requirement.get("requirement_id")).get(
                            "unsupported_success_metric_candidates"
                        )
                    ),
                }
                for requirement in related_requirements
            ],
            "success_metric_rule": prompt_payload.get("success_metric_rule"),
            "unsupported_metric_rule": prompt_payload.get("unsupported_metric_rule"),
        },
        "recommendation": (
            "Treat underdefined satisfaction metrics as open_questions unless the input provides an explicit "
            "user-reported rate, count, score, rating, survey measure, or target definition."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _load_prds(analysis_dir: Path, raw: dict[str, Any]) -> list[dict[str, Any]]:
    prds_path = analysis_dir / "prds.json"
    if prds_path.exists():
        prds = _load_json(prds_path).get("prds")
        if isinstance(prds, list) and prds:
            return [prd for prd in prds if isinstance(prd, dict)]
    extracted = raw.get("extracted_json") or raw.get("raw_output")
    if isinstance(extracted, str):
        try:
            prds = json.loads(extracted).get("prds")
        except json.JSONDecodeError:
            return []
        return [prd for prd in prds if isinstance(prd, dict)] if isinstance(prds, list) else []
    return []


def _first_metric_failure(errors: Any) -> dict[str, int | str] | None:
    if not isinstance(errors, list):
        return None
    for error in errors:
        if not isinstance(error, str):
            continue
        match = re.search(r"(prds\[(\d+)\]\.success_metrics\[(\d+)\])", error)
        if match:
            return {
                "path": match.group(1),
                "prd_index": int(match.group(2)),
                "metric_index": int(match.group(3)),
            }
    return None


def _classify_metric(metric: str) -> str:
    if not metric:
        return "Unknown"
    if not _is_measurable_metric(metric):
        return "Generator Bug - underdefined satisfaction metric"
    if _contains_unsupported_numeric_target(metric):
        return "Generator Bug - unsupported numeric target"
    return "Potential Validator Bug - measurable concept rejected"


def _root_cause(metric: str) -> str:
    if not metric:
        return "unknown_metric"
    if re.search(r"\buser satisfaction with\b", metric.lower()) and not _is_measurable_metric(metric):
        return "model_copied_underdefined_requirement_metric_into_prd_success_metrics"
    if not _is_measurable_metric(metric):
        return "model_generated_vague_success_metric"
    return "validator_metric_heuristic_gap"


def _contains_unsupported_numeric_target(metric: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\s*%", metric))


def _prompt_requirement(version_payload: dict[str, Any], requirement_id: Any) -> dict[str, Any]:
    for requirement in version_payload.get("requirements", []):
        if isinstance(requirement, dict) and requirement.get("requirement_id") == requirement_id:
            return requirement
    return {}


def _metadata(raw: dict[str, Any]) -> dict[str, Any]:
    metadata = raw.get("response_metadata")
    return metadata if isinstance(metadata, dict) else {}


def _infer_analysis_focus(requirements: list[dict[str, Any]]) -> str:
    types = {requirement.get("requirement_type") for requirement in requirements if isinstance(requirement, dict)}
    if types == {"positive_feedback"}:
        return "positive_feedback_analysis"
    if "positive_feedback" in types and "problem" in types:
        return "mixed_analysis"
    return "problem_analysis"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _by_id(items: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    return {
        item[key]: item
        for item in items
        if isinstance(item, dict) and isinstance(item.get(key), str) and item.get(key)
    }


def _list_text(value: Any) -> list[str]:
    return [item.strip() for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose main-sample PRD success metric failures.")
    parser.add_argument("--analysis-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    report = diagnose_main_prd_metric_failure(analysis_dir=args.analysis_dir, output_path=args.output)
    print("Main PRD Metric Diagnosis: PASS")
    print(f"PRD ID: {report.get('prd_id')}")
    print(f"Version ID: {report.get('version_id')}")
    print(f"Failed Metric: {report.get('failed_metric')}")
    print(f"Root Cause: {report.get('root_cause')}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
