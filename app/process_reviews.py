"""CLI entrypoint for Phase 1 deterministic review processing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.cli_i18n import line, stage_result
from app.review_processing import (
    DEFAULT_INPUT_PATH,
    DEFAULT_NEAR_DUPLICATE_THRESHOLD,
    DEFAULT_OUTPUT_DIR,
    ProcessingConfig,
    load_reviews,
    process_reviews,
    write_processing_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Process Unified Review Schema data.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--near-duplicate-threshold",
        type=float,
        default=DEFAULT_NEAR_DUPLICATE_THRESHOLD,
    )
    args = parser.parse_args()

    try:
        reviews = load_reviews(args.input)
        result = process_reviews(
            reviews,
            config=ProcessingConfig(near_duplicate_threshold=args.near_duplicate_threshold),
        )
        output_paths = write_processing_outputs(result, output_dir=args.output_dir)
    except Exception as exc:
        print(stage_result("Pipeline", "FAIL"))
        print(line("Error", repr(exc)))
        return 1

    print(stage_result("Pipeline", "PASS"))
    print(line("Input", result.report.input_count))
    print(line("Valid", result.report.valid_count))
    print(line("Retained", result.report.retained_count))
    print(line("Duplicates", result.report.exact_duplicate_count))
    print("统计信息：")
    print(json.dumps(result.statistics, ensure_ascii=False, indent=2))
    print("输出文件：")
    for label, path in output_paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
