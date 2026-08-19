"""Finding generation CLI for mock and DeepSeek providers."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
import os
from pathlib import Path

from dotenv import load_dotenv

from app.analysis_intent import DEFAULT_ANALYSIS_FOCUS, normalize_analysis_focus
from app.cli_i18n import line, stage_result, value
from app.finding_generation import (
    DEFAULT_FINDING_GOAL,
    build_finding_request,
    create_failure_result,
    generate_findings,
)
from app.finding_validator import FindingValidationResult, validate_finding_output
from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.llm.base import MissingAPIKeyError, ModelRequestError
from app.llm.deepseek_provider import DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL
from app.llm.mock_provider import MockLLMProvider
from app.llm.provider import build_production_provider


DEFAULT_REVIEWS_PATH = Path("artifacts/processed/reviews.json")
DEFAULT_ISSUES_PATH = Path("artifacts/analysis/issues.json")
DEFAULT_CLASSIFICATION_PATH = Path("artifacts/analysis/issue_classification.json")
DEFAULT_ELIGIBILITY_PATH = Path("artifacts/analysis/finding_eligibility.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence-grounded Finding generation.")
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS_PATH)
    parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES_PATH)
    parser.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION_PATH)
    parser.add_argument("--eligibility", type=Path, default=DEFAULT_ELIGIBILITY_PATH)
    parser.add_argument("--provider", choices=["mock", "deepseek"], default="mock")
    parser.add_argument("--goal", default=DEFAULT_FINDING_GOAL)
    parser.add_argument("--analysis-focus", default=DEFAULT_ANALYSIS_FOCUS)
    parser.add_argument("--mock-output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    args = parser.parse_args()

    load_dotenv(override=False)
    try:
        analysis_focus = normalize_analysis_focus(args.analysis_focus)
    except ValueError as exc:
        print(stage_result("Finding Generation", "FAIL"))
        print(line("Failure Type", "Invalid Analysis Focus"))
        print(line("Message", exc))
        return 1
    reviews = load_reviews(args.reviews)
    issues = load_issues(args.issues)
    classifications = load_classifications(args.classification)
    eligibility = load_eligibility(args.eligibility)
    if args.provider == "mock":
        raw_output = (
            args.mock_output.read_text(encoding="utf-8")
            if args.mock_output
            else build_default_mock_output(issues, eligibility)
        )
        provider = MockLLMProvider(raw_output, model="mock-finding-model")
        result = generate_findings(
            reviews=reviews,
            issues=issues,
            classifications=classifications,
            eligibility=eligibility,
            provider=provider,
            analysis_goal=args.goal,
            analysis_focus=analysis_focus,
            output_dir=args.output_dir,
            is_mock=True,
        )
    else:
        try:
            provider = build_production_provider()
        except (MissingAPIKeyError, ModelRequestError) as exc:
            provider_info = _ProviderInfo(
                provider_name="deepseek",
                model=os.environ.get(DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL),
            )
            eligible_issue_count = len(
                {item["issue_id"] for item in eligibility if item.get("eligible_for_finding") is True}
            )
            result = create_failure_result(
                "Missing API Key" if isinstance(exc, MissingAPIKeyError) else "Model Request Error",
                args.goal,
                str(exc),
                args.output_dir,
                provider_info,
                False,
                eligible_issue_count,
                analysis_focus=analysis_focus,
            )
        else:
            result = generate_findings(
                reviews=reviews,
                issues=issues,
                classifications=classifications,
                eligibility=eligibility,
                provider=provider,
                analysis_goal=args.goal,
                analysis_focus=analysis_focus,
                output_dir=args.output_dir,
                is_mock=False,
            )

    if result.generation_passed:
        print(stage_result("Finding Generation", "PASS"))
    else:
        print(stage_result("Finding Generation", "FAIL"))
        print(line("Failure Type", result.generation_status))
    print(line("Provider", result.provider))
    print(line("Model", result.model))
    print(line("Analysis Focus", result.analysis_focus))
    print(line("Finding Count", len(result.findings)))
    print(line("Eligibility Checked", result.eligible_issue_count))
    print(line("Validation", "PASS" if result.validation.passed else value(result.validation.status)))
    evidence_by_id = {report["finding_id"]: report for report in result.evidence_reports}
    for finding in result.findings:
        report = evidence_by_id.get(finding["finding_id"], {})
        print(f"finding_id: {finding['finding_id']}")
        print(f"finding_type: {finding.get('finding_type', 'product_problem')}")
        print(f"title: {finding['title']}")
        print(f"issue_count: {len(finding['issue_ids'])}")
        print(f"review_count: {len(finding['review_ids'])}")
        print(f"support_count: {finding['support_count']}")
        print(f"conflicting_count: {report.get('conflicting_count', 0)}")
        print(f"confidence: {finding['confidence']}")
        print(f"evidence_strength: {report.get('evidence_strength')}")
        print(f"uncertainty: {finding['uncertainty']}")
    for error in result.validation.errors:
        print(f"- {error}")
    print("输出文件：")
    for label, path in result.saved_paths.items():
        print(f"{label}: {path}")
    return 0 if result.generation_passed and result.validation.passed else 1


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
        "finding_type": next(
            (
                item.get("finding_type")
                for item in eligibility
                if item.get("issue_id") == issue.get("issue_id") and item.get("finding_type")
            ),
            "product_problem",
        ),
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


class _ProviderInfo:
    def __init__(self, *, provider_name: str, model: str) -> None:
        self.provider_name = provider_name
        self.model = model

    def generate(self, request):
        raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
