"""CLI for deterministic issue type classification and finding eligibility."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.analysis_intent import DEFAULT_ANALYSIS_FOCUS, focus_label, normalize_analysis_focus
from app.finding_eligibility import evaluate_finding_eligibilities
from app.issue_consolidation import DEFAULT_ANALYSIS_DIR
from app.issue_type import classify_issues


DEFAULT_ISSUES_PATH = Path("artifacts/analysis/issues.json")
DEFAULT_CLASSIFICATION_PATH = Path("artifacts/analysis/issue_classification.json")
DEFAULT_ELIGIBILITY_PATH = Path("artifacts/analysis/finding_eligibility.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify issue types and apply Finding eligibility gate.")
    parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    parser.add_argument("--analysis-focus", default=DEFAULT_ANALYSIS_FOCUS)
    args = parser.parse_args()

    issues = load_issues(args.issues)
    try:
        analysis_focus = normalize_analysis_focus(args.analysis_focus)
        classifications = classify_issues(issues)
        eligibility = evaluate_finding_eligibilities(
            [item.to_dict() for item in classifications],
            analysis_focus=analysis_focus,
        )
    except ValueError as exc:
        print("Issue Classification: FAIL")
        print(f"Error: {exc}")
        return 1

    paths = save_outputs(classifications, eligibility, analysis_focus=analysis_focus, output_dir=args.output_dir)
    classification_distribution = Counter(item.issue_type for item in classifications)
    eligibility_distribution = Counter(item.eligible_for_finding for item in eligibility)

    print("Issue Classification: PASS")
    print(f"Analysis Focus: {analysis_focus} ({focus_label(analysis_focus)})")
    for item in classifications:
        print(f"{item.issue_id} {item.issue_type}")
    print("Finding Eligibility: PASS")
    print(f"Eligible: {eligibility_distribution[True]}")
    print(f"Ineligible: {eligibility_distribution[False]}")
    print("Issue Type Distribution:")
    for issue_type, count in sorted(classification_distribution.items()):
        print(f"{issue_type}: {count}")
    print("Output files:")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


def load_issues(path: Path = DEFAULT_ISSUES_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    issues = payload.get("issues") if isinstance(payload, dict) else None
    if not isinstance(issues, list) or not all(isinstance(issue, dict) for issue in issues):
        raise ValueError(f"Issues file is invalid: {path}")
    return list(issues)


def save_outputs(
    classifications,
    eligibility,
    *,
    analysis_focus: str = DEFAULT_ANALYSIS_FOCUS,
    output_dir: Path = DEFAULT_ANALYSIS_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    classification_path = output_dir / "issue_classification.json"
    eligibility_path = output_dir / "finding_eligibility.json"
    classification_payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "is_deterministic": True,
        "analysis_focus": analysis_focus,
        "classifications": [item.to_dict() for item in classifications],
    }
    eligibility_payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "is_deterministic": True,
        "analysis_focus": analysis_focus,
        "eligibility": [item.to_dict() for item in eligibility],
    }
    classification_path.write_text(json.dumps(classification_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    eligibility_path.write_text(json.dumps(eligibility_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"classification": classification_path, "eligibility": eligibility_path}


if __name__ == "__main__":
    raise SystemExit(main())
