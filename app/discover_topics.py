"""CLI entrypoint for Phase 2.1 Dynamic Topic Discovery."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from app.cli_i18n import line, stage_result, value
from app.llm.base import (
    MissingAPIKeyError,
    ModelAuthenticationError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
)
from app.llm.deepseek_provider import DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL
from app.llm.provider import build_production_provider
from app.topic_discovery import (
    DEFAULT_ANALYSIS_DIR,
    DEFAULT_PROCESSED_REVIEWS_PATH,
    create_failure_result,
    discover_topics,
    load_processed_reviews,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover dynamic topics from processed reviews.")
    parser.add_argument("--goal", required=True, help="Analysis goal passed verbatim to topic discovery.")
    parser.add_argument("--input", type=Path, default=DEFAULT_PROCESSED_REVIEWS_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    args = parser.parse_args()

    load_dotenv(override=False)
    reviews = load_processed_reviews(args.input)
    provider_name = "deepseek"
    model_name = os.environ.get(DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL)
    try:
        provider = build_production_provider()
    except MissingAPIKeyError as exc:
        result = create_failure_result(
            "Missing API Key",
            args.goal,
            str(exc),
            args.output_dir,
            provider=provider_name,
            model=model_name,
        )
    except ModelAuthenticationError as exc:
        result = create_failure_result(
            "Authentication Error",
            args.goal,
            str(exc),
            args.output_dir,
            provider=provider_name,
            model=model_name,
        )
    except ModelRateLimitError as exc:
        result = create_failure_result(
            "Rate Limit",
            args.goal,
            str(exc),
            args.output_dir,
            provider=provider_name,
            model=model_name,
        )
    except ModelTimeoutError as exc:
        result = create_failure_result(
            "Timeout",
            args.goal,
            str(exc),
            args.output_dir,
            provider=provider_name,
            model=model_name,
        )
    except ModelRequestError as exc:
        result = create_failure_result(
            "Model Request Error",
            args.goal,
            str(exc),
            args.output_dir,
            provider=provider_name,
            model=model_name,
        )
    else:
        result = discover_topics(
            reviews,
            analysis_goal=args.goal,
            provider=provider,
            output_dir=args.output_dir,
        )

    if result.passed:
        print(stage_result("Topic Discovery", "PASS"))
        print(line("Provider", result.provider))
        print(line("Model", result.model))
        print(line("Topic Count", len(result.topics)))
        print(line("Validation", "PASS"))
        for topic in result.topics:
            print(f"topic_id: {topic.topic_id}")
            print(f"name: {topic.name}")
            print(f"review_count: {len(topic.review_ids)}")
            print(f"confidence: {topic.confidence}")
            print(f"uncertainty: {topic.uncertainty}")
        print("输出文件：")
        for label, path in result.saved_paths.items():
            print(f"{label}: {path}")
        return 0

    print(stage_result("Topic Discovery", "FAIL"))
    print(line("Provider", result.provider))
    print(line("Model", result.model))
    print(line("Failure Type", result.status))
    if result.error:
        print(line("Message", result.error))
    print(line("Validation", value(result.validation.status)))
    for error in result.validation.errors:
        print(f"- {error}")
    print("输出文件：")
    for label, path in result.saved_paths.items():
        print(f"{label}: {path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
