"""Mock Finding generation CLI for Phase 3a."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.evidence_engine import calculate_evidence_reports
from app.finding_validator import FindingValidationResult, validate_finding_output
from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.llm.base import LLMRequest
from app.llm.mock_provider import MockLLMProvider


DEFAULT_REVIEWS_PATH = Path("artifacts/processed/reviews.json")
DEFAULT_ISSUES_PATH = Path("artifacts/analysis/issues.json")
DEFAULT_CLASSIFICATION_PATH = Path("artifacts/analysis/issue_classification.json")
DEFAULT_ELIGIBILITY_PATH = Path("artifacts/analysis/finding_eligibility.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock evidence-grounded Finding validation.")
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS_PATH)
    parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES_PATH)
    parser.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION_PATH)
    parser.add_argument("--eligibility", type=Path, default=DEFAULT_ELIGIBILITY_PATH)
    parser.add_argument("--mock-output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    args = parser.parse_args()

    reviews = load_reviews(args.reviews)
    issues = load_issues(args.issues)
    classifications = load_classifications(args.classification)
    eligibility = load_eligibility(args.eligibility)
    raw_output = (
        args.mock_output.read_text(encoding="utf-8")
        if args.mock_output
        else build_default_mock_output(issues, eligibility)
    )

    provider = MockLLMProvider(raw_output, model="mock-finding-model")
    response = provider.generate(
        LLMRequest(
            system_prompt="Phase 3a mock Finding generation. Do not call a production model.",
            user_prompt="Validate mock evidence-grounded findings.",
            analysis_goal="mock_finding_generation",
        )
    )
    issues_by_id = {issue["issue_id"]: issue for issue in issues}
    valid_review_ids = {review["id"] for review in reviews if isinstance(review.get("id"), str)}
    eligible_issue_ids = {
        item["issue_id"] for item in eligibility if item.get("eligible_for_finding") is True
    }
    validation = validate_finding_output(
        response.raw_text,
        issues_by_id=issues_by_id,
        valid_review_ids=valid_review_ids,
        eligible_issue_ids=eligible_issue_ids,
    )
    findings = [asdict(finding) for finding in validation.findings] if validation.passed else []
    evidence_reports = [report.to_dict() for report in validation.evidence_reports] if validation.passed else []
    paths = save_outputs(
        raw_output=response.raw_text,
        validation=validation,
        findings=findings,
        evidence_reports=evidence_reports,
        output_dir=args.output_dir,
    )

    if validation.passed:
        print("Finding Generation: PASS")
    else:
        print("Finding Generation: FAIL")
        print(f"Failure Type: {validation.status}")
    print("Provider: mock")
    print(f"Finding Count: {len(findings)}")
    print(f"Eligibility Checked: {len(eligible_issue_ids)}")
    print(f"Validation: {'PASS' if validation.passed else 'FAIL'}")
    if evidence_reports:
        print("Evidence Strength:")
        for report in evidence_reports:
            print(f"{report['finding_id']}: {report['evidence_strength']}")
    for error in validation.errors:
        print(f"- {error}")
    print("Output files:")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0 if validation.passed else 1


def load_reviews(path: Path = DEFAULT_REVIEWS_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    reviews = payload.get("reviews") if isinstance(payload, dict) else None
    if not isinstance(reviews, list) or not all(isinstance(review, dict) for review in reviews):
        raise ValueError(f"Reviews file is invalid: {path}")
    return list(reviews)


def load_issues(path: Path = DEFAULT_ISSUES_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    issues = payload.get("issues") if isinstance(payload, dict) else None
    if not isinstance(issues, list) or not all(isinstance(issue, dict) for issue in issues):
        raise ValueError(f"Issues file is invalid: {path}")
    return list(issues)


def load_classifications(path: Path = DEFAULT_CLASSIFICATION_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    classifications = payload.get("classifications") if isinstance(payload, dict) else None
    if not isinstance(classifications, list):
        raise ValueError(f"Issue classification file is invalid: {path}")
    return list(classifications)


def load_eligibility(path: Path = DEFAULT_ELIGIBILITY_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    eligibility = payload.get("eligibility") if isinstance(payload, dict) else None
    if not isinstance(eligibility, list):
        raise ValueError(f"Finding eligibility file is invalid: {path}")
    return list(eligibility)


def build_default_mock_output(issues: list[dict], eligibility: list[dict]) -> str:
    eligible_issue_ids = [
        item["issue_id"] for item in eligibility if item.get("eligible_for_finding") is True
    ]
    issue = next((item for item in issues if item.get("issue_id") in eligible_issue_ids), None)
    if not issue:
        return json.dumps({"findings": []})
    review_ids = list(dict.fromkeys(issue.get("review_ids", [])))
    support_count = len(review_ids)
    finding = {
        "finding_id": "FINDING-001",
        "issue_ids": [issue["issue_id"]],
        "review_ids": review_ids,
        "title": issue.get("name", "Mock finding"),
        "statement": issue.get("description", "Mock evidence-grounded finding."),
        "evidence_summary": f"Mock finding grounded in {support_count} issue evidence reviews.",
        "support_count": support_count,
        "confidence": min(float(issue.get("confidence", 0.8)), 1.0),
        "uncertainty": issue.get("uncertainty", ""),
        "conflicting_review_ids": [],
    }
    return json.dumps({"findings": [finding]}, ensure_ascii=False)


def save_outputs(
    *,
    raw_output: str,
    validation: FindingValidationResult,
    findings: list[dict],
    evidence_reports: list[dict],
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "finding_generation_raw.json"
    findings_path = output_dir / "findings.json"
    validation_path = output_dir / "finding_validation.json"
    evidence_path = output_dir / "evidence_report.json"

    raw_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "provider": "mock",
                "is_mock": True,
                "raw_output": raw_output,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    findings_path.write_text(json.dumps({"findings": findings}, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(validation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    evidence_path.write_text(
        json.dumps({"evidence_reports": evidence_reports}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "raw": raw_path,
        "findings": findings_path,
        "validation": validation_path,
        "evidence": evidence_path,
    }


if __name__ == "__main__":
    raise SystemExit(main())
