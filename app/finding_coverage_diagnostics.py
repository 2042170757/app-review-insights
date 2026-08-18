"""Read-only diagnostics for eligible Issues without downstream Findings."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.finding_generation import build_finding_request
from app.topic_discovery import extract_json_text


DEFAULT_OUTPUT_PATH = Path("artifacts/final_validation/finding_coverage_diagnosis.json")
DEFAULT_ISSUE_ID = "ISSUE-012"

ROOT_CAUSES = {
    "Generator Bug",
    "Validator Bug",
    "Eligibility Rule Bug",
    "Evidence Insufficient",
    "Model Omission",
    "Classification Bug",
    "Expected Exclusion",
    "Traceability Rule Bug",
    "Unknown / Requires Further Investigation",
}

POSITIVE_TERMS = (
    "positive feedback",
    "appreciation",
    "appreciate",
    "love",
    "liked",
    "enjoy",
    "enjoyed",
    "useful",
    "helpful",
    "great",
    "amazing",
    "satisfied",
)
PROBLEM_TERMS = (
    "cannot",
    "unable",
    "crash",
    "freeze",
    "slow",
    "broken",
    "bug",
    "failure",
    "failed",
    "paywall",
    "subscription",
    "billing",
    "ads",
    "frustration",
    "frustrating",
)
NEGATED_PROBLEM_TERMS = (
    "not a product problem",
    "not product problem",
    "not a user problem",
)


def diagnose_finding_coverage(
    *,
    root: Path = Path("."),
    issue_id: str = DEFAULT_ISSUE_ID,
    output_path: Path | None = None,
) -> dict[str, Any]:
    artifacts = load_finding_coverage_artifacts(root)
    report = diagnose_finding_coverage_payloads(issue_id=issue_id, **artifacts)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def diagnose_finding_coverage_payloads(
    *,
    issue_id: str,
    reviews: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
    eligibility: list[dict[str, Any]],
    raw_generation: dict[str, Any],
    findings: list[dict[str, Any]],
    finding_validation: dict[str, Any],
    evidence_reports: list[dict[str, Any]],
    traceability_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reviews_by_id = {_text(review.get("id")): review for review in reviews if _text(review.get("id"))}
    issue = next((item for item in issues if _text(item.get("issue_id")) == issue_id), None)
    classification = next((item for item in classifications if _text(item.get("issue_id")) == issue_id), None)
    eligibility_item = next((item for item in eligibility if _text(item.get("issue_id")) == issue_id), None)
    raw_payload = _parse_stage_payload(raw_generation)
    raw_findings = raw_payload.get("findings") if isinstance(raw_payload.get("findings"), list) else []
    valid_findings_for_issue = [
        finding for finding in findings if issue_id in _id_list(finding.get("issue_ids"))
    ]
    raw_findings_for_issue = [
        finding for finding in raw_findings if isinstance(finding, dict) and issue_id in _id_list(finding.get("issue_ids"))
    ]
    raw_findings_with_wrong_issue = [
        {
            "finding_id": finding.get("finding_id"),
            "issue_ids": _id_list(finding.get("issue_ids")),
        }
        for finding in raw_findings
        if isinstance(finding, dict) and issue_id not in _id_list(finding.get("issue_ids"))
    ]

    request_input_contains_issue = _request_input_contains_issue(
        issue_id=issue_id,
        reviews=reviews,
        issues=issues,
        classifications=classifications,
        eligibility=eligibility,
        raw_generation=raw_generation,
    )
    issue_review_ids = _id_list(issue.get("review_ids")) if issue else []
    review_summaries = [_review_summary(review_id, reviews_by_id.get(review_id, {})) for review_id in issue_review_ids]
    evidence_strength = _issue_evidence_strength(len(issue_review_ids))
    positive_feedback_likely = _positive_feedback_likely(issue or {}, review_summaries)
    eligible_for_finding = bool(eligibility_item and eligibility_item.get("eligible_for_finding") is True)
    issue_type = _text((classification or {}).get("issue_type")) or _text((issue or {}).get("issue_type"))
    validation_errors = _list_text(finding_validation.get("errors"))
    validation_status = _text(finding_validation.get("status"))
    root_cause = _classify_root_cause(
        issue_exists=issue is not None,
        eligible_for_finding=eligible_for_finding,
        issue_type=issue_type,
        positive_feedback_likely=positive_feedback_likely,
        request_input_contains_issue=request_input_contains_issue,
        raw_findings_for_issue=raw_findings_for_issue,
        valid_findings_for_issue=valid_findings_for_issue,
        validation_passed=finding_validation.get("passed") is True,
        validation_errors=validation_errors,
        support_count=len(issue_review_ids),
    )
    recommendation = _recommendation(root_cause)
    traceability_errors = _list_text((traceability_report or {}).get("critical_issues")) + _list_text(
        (traceability_report or {}).get("errors")
    )
    traceability_errors_for_issue = [error for error in traceability_errors if issue_id in error]
    if eligible_for_finding and not valid_findings_for_issue and not traceability_errors_for_issue:
        traceability_errors_for_issue.append(f"{issue_id}: eligible issue has no downstream finding")

    return {
        "generated_at": _now(),
        "issue_id": issue_id,
        "issue_exists": issue is not None,
        "issue_type": issue_type,
        "name": (issue or {}).get("name"),
        "description": (issue or {}).get("description"),
        "confidence": (issue or {}).get("confidence"),
        "topic_ids": _id_list((issue or {}).get("topic_ids")),
        "review_ids": issue_review_ids,
        "eligible_for_finding": eligible_for_finding,
        "eligibility_reason": (eligibility_item or {}).get("reason"),
        "eligibility_finding_type": (eligibility_item or {}).get("finding_type"),
        "analysis_focus": _text(raw_generation.get("analysis_focus")),
        "supporting_review_count": len(issue_review_ids),
        "review_contents": review_summaries,
        "evidence_strength": evidence_strength,
        "uncertainty": (issue or {}).get("uncertainty"),
        "positive_feedback_likely": positive_feedback_likely,
        "finding_generation_input_contains_issue_012": request_input_contains_issue
        if issue_id == DEFAULT_ISSUE_ID
        else request_input_contains_issue,
        "finding_generation_input_contains_issue": request_input_contains_issue,
        "finding_generated": bool(valid_findings_for_issue),
        "finding_generated_in_raw": bool(raw_findings_for_issue),
        "finding_raw_count": len(raw_findings),
        "finding_valid_count": len(findings),
        "raw_findings_for_issue": [_finding_summary(finding) for finding in raw_findings_for_issue],
        "raw_findings_with_other_issue_ids": raw_findings_with_wrong_issue,
        "finding_validation": validation_status,
        "finding_validation_passed": finding_validation.get("passed"),
        "finding_validation_errors": validation_errors,
        "evidence_reports_for_issue": _evidence_reports_for_issue(evidence_reports, valid_findings_for_issue),
        "traceability_rule": "Eligible Issues are expected to have at least one downstream Finding.",
        "traceability_errors_for_issue": traceability_errors_for_issue,
        "eligibility_meaning": (
            "The current deterministic gate marks whether an Issue should be attempted for downstream "
            "Finding generation for the active analysis focus. Final traceability currently treats eligible "
            "Issues as requiring downstream Finding coverage."
        ),
        "root_cause": root_cause,
        "recommendation": recommendation,
    }


def load_finding_coverage_artifacts(root: Path) -> dict[str, Any]:
    paths = _artifact_paths(root)
    return {
        "reviews": _load_items(paths["reviews"], "reviews"),
        "issues": _load_items(paths["issues"], "issues"),
        "classifications": _load_items(paths["classification"], "classifications"),
        "eligibility": _load_items(paths["eligibility"], "eligibility"),
        "raw_generation": _load_json(paths["raw_generation"]),
        "findings": _load_items(paths["findings"], "findings"),
        "finding_validation": _load_json(paths["finding_validation"]),
        "evidence_reports": _load_items(paths["evidence_report"], "evidence_reports"),
        "traceability_report": _load_json(paths["traceability"]) if paths["traceability"] else {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose eligible Issues without downstream Findings.")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--issue-id", default=DEFAULT_ISSUE_ID)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    report = diagnose_finding_coverage(root=args.root, issue_id=args.issue_id, output_path=args.output)
    print("Finding Coverage Diagnostics: PASS")
    print(f"Issue: {report['issue_id']}")
    print(f"Eligible: {report['eligible_for_finding']}")
    print(f"Finding Generation Input: {report['finding_generation_input_contains_issue']}")
    print(f"Finding Generated: {report['finding_generated']}")
    print(f"Finding Generated In Raw: {report['finding_generated_in_raw']}")
    print(f"Finding Validation: {report['finding_validation']}")
    print(f"Root Cause: {report['root_cause']}")
    print(f"Output: {args.output}")
    return 0


def _artifact_paths(root: Path) -> dict[str, Path | None]:
    if (root / "artifacts" / "analysis").exists():
        analysis = root / "artifacts" / "analysis"
        processed = root / "artifacts" / "processed"
        final = root / "artifacts" / "analysis" / "final_validation_report.json"
        return {
            "reviews": processed / "reviews.json",
            "issues": analysis / "issues.json",
            "classification": analysis / "issue_classification.json",
            "eligibility": analysis / "finding_eligibility.json",
            "raw_generation": analysis / "finding_generation_raw.json",
            "findings": analysis / "findings.json",
            "finding_validation": analysis / "finding_validation.json",
            "evidence_report": analysis / "evidence_report.json",
            "traceability": final if final.exists() else None,
        }
    traceability = root / "traceability" / "final_validation_report.json"
    return {
        "reviews": root / "processing" / "reviews.json",
        "issues": root / "issue_consolidation" / "issues.json",
        "classification": root / "issue_consolidation" / "issue_classification.json",
        "eligibility": root / "issue_consolidation" / "finding_eligibility.json",
        "raw_generation": root / "finding_generation" / "finding_generation_raw.json",
        "findings": root / "finding_generation" / "findings.json",
        "finding_validation": root / "finding_generation" / "finding_validation.json",
        "evidence_report": root / "finding_generation" / "evidence_report.json",
        "traceability": traceability if traceability.exists() else None,
    }


def _request_input_contains_issue(
    *,
    issue_id: str,
    reviews: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
    eligibility: list[dict[str, Any]],
    raw_generation: dict[str, Any],
) -> bool:
    try:
        request = build_finding_request(
            reviews=reviews,
            issues=issues,
            classifications=classifications,
            eligibility=eligibility,
            analysis_goal=_text(raw_generation.get("analysis_goal")) or "diagnostic",
            analysis_focus=_text(raw_generation.get("analysis_focus")) or "problem_analysis",
        )
    except Exception:
        return False
    try:
        payload = json.loads(request.user_prompt)
    except json.JSONDecodeError:
        return False
    eligible_issues = payload.get("eligible_issues")
    if not isinstance(eligible_issues, list):
        return False
    return any(isinstance(item, dict) and _text(item.get("issue_id")) == issue_id for item in eligible_issues)


def _classify_root_cause(
    *,
    issue_exists: bool,
    eligible_for_finding: bool,
    issue_type: str,
    positive_feedback_likely: bool,
    request_input_contains_issue: bool,
    raw_findings_for_issue: list[dict[str, Any]],
    valid_findings_for_issue: list[dict[str, Any]],
    validation_passed: bool,
    validation_errors: list[str],
    support_count: int,
) -> str:
    if not issue_exists:
        return "Unknown / Requires Further Investigation"
    if not eligible_for_finding:
        return "Expected Exclusion"
    if positive_feedback_likely and issue_type != "positive_feedback":
        return "Classification Bug"
    if support_count <= 1 and not raw_findings_for_issue and not valid_findings_for_issue:
        return "Evidence Insufficient"
    if raw_findings_for_issue and not valid_findings_for_issue:
        return "Validator Bug" if validation_errors or not validation_passed else "Generator Bug"
    if request_input_contains_issue and not raw_findings_for_issue and not valid_findings_for_issue:
        return "Model Omission"
    if not request_input_contains_issue and eligible_for_finding:
        return "Eligibility Rule Bug"
    if valid_findings_for_issue:
        return "Expected Exclusion"
    return "Unknown / Requires Further Investigation"


def _recommendation(root_cause: str) -> str:
    recommendations = {
        "Classification Bug": (
            "Keep Traceability strict. In the next fix phase, adjust deterministic issue classification so "
            "positive feedback that explicitly says it is not a product problem is classified as positive_feedback."
        ),
        "Model Omission": (
            "Keep the validator strict. In the next fix phase, consider a Finding coverage guard or prompt retry "
            "for eligible Issues that entered the request but were omitted by the model."
        ),
        "Evidence Insufficient": (
            "Clarify whether eligibility means candidate-only or mandatory downstream coverage when evidence is too weak."
        ),
        "Validator Bug": (
            "Inspect rejected raw Findings against the validator errors before changing generation behavior."
        ),
        "Eligibility Rule Bug": (
            "Review the deterministic Finding Eligibility gate before changing Traceability."
        ),
        "Traceability Rule Bug": (
            "Only relax Traceability if eligible Issues are explicitly allowed to remain without Findings."
        ),
        "Expected Exclusion": "No Finding fix is required for this Issue under the current analysis focus.",
    }
    return recommendations.get(root_cause, "Collect the missing stage artifacts or rerun a minimal Finding smoke test.")


def _positive_feedback_likely(issue: dict[str, Any], review_summaries: list[dict[str, Any]]) -> bool:
    text = " ".join(
        [
            _text(issue.get("name")),
            _text(issue.get("description")),
            _text(issue.get("merge_rationale")),
            _text(issue.get("uncertainty")),
        ]
    ).lower()
    has_positive = any(term in text for term in POSITIVE_TERMS)
    has_negated_problem = any(term in text for term in NEGATED_PROBLEM_TERMS)
    has_problem = any(term in text for term in PROBLEM_TERMS)
    ratings = [item.get("rating") for item in review_summaries if isinstance(item.get("rating"), (int, float))]
    high_rating_evidence = bool(ratings) and min(ratings) >= 4
    return has_positive and high_rating_evidence and (has_negated_problem or not has_problem)


def _issue_evidence_strength(support_count: int) -> str:
    if support_count <= 0:
        return "None"
    if support_count == 1:
        return "Low"
    if support_count <= 3:
        return "Medium"
    return "High"


def _review_summary(review_id: str, review: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_id": review_id,
        "rating": review.get("rating"),
        "title": review.get("clean_title") or review.get("title"),
        "body": review.get("clean_body") or review.get("body"),
        "language": review.get("language"),
        "created_at": review.get("created_at"),
    }


def _finding_summary(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": finding.get("finding_id"),
        "finding_type": finding.get("finding_type"),
        "issue_ids": _id_list(finding.get("issue_ids")),
        "review_ids": _id_list(finding.get("review_ids")),
        "support_count": finding.get("support_count"),
        "title": finding.get("title"),
    }


def _evidence_reports_for_issue(
    evidence_reports: list[dict[str, Any]],
    findings_for_issue: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    finding_ids = {_text(finding.get("finding_id")) for finding in findings_for_issue}
    return [report for report in evidence_reports if _text(report.get("finding_id")) in finding_ids]


def _parse_stage_payload(raw: dict[str, Any]) -> dict[str, Any]:
    text = _text(raw.get("extracted_json")) or _text(raw.get("raw_output")) or _text(raw.get("raw_response"))
    if not text:
        return {}
    try:
        payload = json.loads(extract_json_text(text))
    except (json.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_items(path: Path | None, key: str) -> list[dict[str, Any]]:
    payload = _load_json(path)
    items = payload.get(key)
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _id_list(value: Any) -> list[str]:
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _list_text(value: Any) -> list[str]:
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
