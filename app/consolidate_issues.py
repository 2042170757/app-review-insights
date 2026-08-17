"""CLI entrypoint for Phase 2.2b issue consolidation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from app.analysis_intent import DEFAULT_ANALYSIS_FOCUS, normalize_analysis_focus
from app.issue_consolidation import (
    DEFAULT_ANALYSIS_DIR,
    DEFAULT_ISSUE_GOAL,
    DEFAULT_MOCK_ISSUE_OUTPUT,
    DEFAULT_PROCESSED_REVIEWS_PATH,
    DEFAULT_TOPICS_PATH,
    create_failure_result,
    consolidate_issues,
    load_processed_reviews,
    load_topics,
)
from app.llm.base import MissingAPIKeyError, ModelRequestError
from app.llm.deepseek_provider import DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL
from app.llm.mock_provider import MockLLMProvider
from app.llm.provider import build_production_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate validated topics into issues.")
    parser.add_argument("--reviews", type=Path, default=DEFAULT_PROCESSED_REVIEWS_PATH)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS_PATH)
    parser.add_argument("--provider", choices=["mock", "deepseek"], default="mock")
    parser.add_argument("--goal", default=DEFAULT_ISSUE_GOAL)
    parser.add_argument("--analysis-focus", default=DEFAULT_ANALYSIS_FOCUS)
    parser.add_argument("--mock-output", type=Path, help="Optional JSON file containing mock issue output.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    args = parser.parse_args()

    load_dotenv(override=False)
    try:
        analysis_focus = normalize_analysis_focus(args.analysis_focus)
    except ValueError as exc:
        print("Issue Consolidation: FAIL")
        print(f"Failure Type: Invalid Analysis Focus")
        print(f"Message: {exc}")
        return 1
    reviews = load_processed_reviews(args.reviews)
    topics = load_topics(args.topics)
    if args.provider == "mock":
        raw_output = (
            args.mock_output.read_text(encoding="utf-8")
            if args.mock_output
            else DEFAULT_MOCK_ISSUE_OUTPUT
        )
        result = consolidate_issues(
            reviews,
            topics,
            provider=MockLLMProvider(raw_output, model="mock-issue-model"),
            analysis_goal=args.goal,
            analysis_focus=analysis_focus,
            output_dir=args.output_dir,
            is_mock=True,
        )
    else:
        try:
            provider = build_production_provider()
        except MissingAPIKeyError as exc:
            result = create_failure_result(
                "Missing API Key",
                args.goal,
                str(exc),
                args.output_dir,
                provider="deepseek",
                model=os.environ.get(DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL),
                analysis_focus=analysis_focus,
            )
        except ModelRequestError as exc:
            result = create_failure_result(
                "Model Request Error",
                args.goal,
                str(exc),
                args.output_dir,
                provider="deepseek",
                model=os.environ.get(DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL),
                analysis_focus=analysis_focus,
            )
        else:
            result = consolidate_issues(
                reviews,
                topics,
                provider=provider,
                analysis_goal=args.goal,
                analysis_focus=analysis_focus,
                output_dir=args.output_dir,
                is_mock=False,
            )

    if result.passed:
        print("Issue Consolidation: PASS")
        print(f"Provider: {result.provider}")
        print(f"Model: {result.model}")
        print(f"Analysis Focus: {result.analysis_focus}")
        print(f"Issue Count: {len(result.issues)}")
        print(f"Unmerged Topic Count: {len(result.unmerged_topic_ids)}")
        print("Validation: PASS")
        for issue in result.issues:
            print(f"issue_id: {issue.issue_id}")
            print(f"name: {issue.name}")
            print(f"topic_count: {len(issue.topic_ids)}")
            print(f"review_count: {len(issue.review_ids)}")
            print(f"confidence: {issue.confidence}")
            print(f"uncertainty: {issue.uncertainty}")
            print(f"merge_rationale: {issue.merge_rationale}")
    else:
        print("Issue Consolidation: FAIL")
        print(f"Provider: {result.provider}")
        print(f"Model: {result.model}")
        print(f"Analysis Focus: {result.analysis_focus}")
        print(f"Issue Count: {len(result.issues)}")
        print(f"Unmerged Topic Count: {len(result.unmerged_topic_ids)}")
        print(f"Validation: {result.validation.status}")
        print(f"Failure Type: {result.status}")
        if result.error:
            print(f"Message: {result.error}")
        for error in result.validation.errors:
            print(f"- {error}")
    print("Output files:")
    for label, path in result.saved_paths.items():
        print(f"{label}: {path}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
