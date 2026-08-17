"""Read-only data quality audit for Phase 0.75 Apify artifacts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


TARGET_APP_ID = "839285684"
TARGET_TERRITORY = "US"
RAW_PATH = Path("artifacts/raw/apify/raw_response.json")
NORMALIZED_PATH = Path("artifacts/normalized/apify/normalized_reviews.json")
METADATA_PATH = Path("artifacts/normalized/apify/dataset_metadata.json")


@dataclass(frozen=True)
class ReviewSample:
    id: str
    rating: int | None
    title: str
    body_preview: str
    created_at: str
    territory: str


@dataclass
class AuditStats:
    total: int = 0
    raw_total: int = 0
    rating_distribution: dict[int, int] = field(default_factory=dict)
    empty_title_count: int = 0
    empty_body_count: int = 0
    duplicate_id_count: int = 0
    invalid_rating_count: int = 0
    invalid_date_count: int = 0
    non_us_territory_count: int = 0
    app_id_mismatch_count: int = 0
    source_mismatch_count: int = 0
    missing_id_count: int = 0
    missing_title_and_body_count: int = 0
    raw_missing_required_field_count: int = 0
    raw_placeholder_count: int = 0
    raw_error_row_count: int = 0
    source_unmatched_count: int = 0
    metadata_mismatch_count: int = 0


@dataclass
class AuditResult:
    passed: bool
    stats: AuditStats
    failures: list[str]
    samples: list[ReviewSample]
    metadata: dict[str, Any]
    id_strategy: str
    limitations: list[str]


def main() -> int:
    result = audit_apify_artifacts()
    print_audit_result(result)
    return 0 if result.passed else 1


def audit_apify_artifacts(
    *,
    raw_path: Path = RAW_PATH,
    normalized_path: Path = NORMALIZED_PATH,
    metadata_path: Path = METADATA_PATH,
) -> AuditResult:
    failures: list[str] = []
    raw_payload = _read_json_object(raw_path, failures, "raw dataset")
    normalized_payload = _read_json_object(normalized_path, failures, "normalized dataset")
    metadata = _read_json_object(metadata_path, failures, "dataset metadata")

    raw_items = _extract_list(raw_payload, "raw_items", failures, "raw dataset")
    reviews = _extract_list(normalized_payload, "reviews", failures, "normalized dataset")

    stats = AuditStats(total=len(reviews), raw_total=len(raw_items))
    stats.rating_distribution = _rating_distribution(reviews)
    stats.empty_title_count = sum(1 for review in reviews if not _text(review.get("title")))
    stats.empty_body_count = sum(1 for review in reviews if not _text(review.get("body")))
    stats.duplicate_id_count = _duplicate_count([_text(review.get("id")) for review in reviews])

    raw_id_map, id_strategy = _build_raw_id_map(raw_items)
    required_raw_fields = {"review_id", "app_id", "rating", "title", "text", "posted_at"}

    for item in raw_items:
        if item.get("success") is False or item.get("error"):
            stats.raw_error_row_count += 1
        missing_fields = [field for field in required_raw_fields if field not in item]
        if missing_fields:
            stats.raw_missing_required_field_count += 1
        if _has_placeholder_value(item):
            stats.raw_placeholder_count += 1

    seen_ids: set[str] = set()
    for review in reviews:
        review_id = _text(review.get("id"))
        if not review_id:
            stats.missing_id_count += 1
        elif review_id in seen_ids:
            pass
        else:
            seen_ids.add(review_id)

        if review.get("app_id") != TARGET_APP_ID:
            stats.app_id_mismatch_count += 1

        if review.get("territory") != TARGET_TERRITORY:
            stats.non_us_territory_count += 1

        rating = review.get("rating")
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            stats.invalid_rating_count += 1

        if not _text(review.get("title")) and not _text(review.get("body")):
            stats.missing_title_and_body_count += 1

        if not _is_parseable_iso8601(_text(review.get("created_at"))):
            stats.invalid_date_count += 1

        if review.get("source") != "apify":
            stats.source_mismatch_count += 1

        if review_id and review_id not in raw_id_map:
            stats.source_unmatched_count += 1

    _check_count(
        stats.raw_total,
        stats.total,
        failures,
        "raw / normalized counts differ",
    )
    _check_metadata(metadata, stats, failures)
    _append_stat_failures(stats, failures)

    samples = [
        ReviewSample(
            id=_text(review.get("id")),
            rating=review.get("rating") if isinstance(review.get("rating"), int) else None,
            title=_text(review.get("title")),
            body_preview=_text(review.get("body"))[:120],
            created_at=_text(review.get("created_at")),
            territory=_text(review.get("territory")),
        )
        for review in reviews[:5]
    ]

    return AuditResult(
        passed=not failures,
        stats=stats,
        failures=failures,
        samples=samples,
        metadata=metadata,
        id_strategy=id_strategy,
        limitations=[str(item) for item in metadata.get("limitations", [])]
        if isinstance(metadata.get("limitations"), list)
        else [],
    )


def print_audit_result(result: AuditResult) -> None:
    metadata = result.metadata
    stats = result.stats

    print("Apify Data Quality Audit")
    print(f"provider: {metadata.get('provider')}")
    print(f"actor: {metadata.get('actor')}")
    print(f"app_id: {metadata.get('app_id')}")
    print(f"territory: {metadata.get('territory')}")
    print(f"requested_limit: {metadata.get('requested_limit')}")
    print(f"metadata_actual_count: {metadata.get('actual_count')}")
    print(f"retrieved_at: {metadata.get('retrieved_at')}")
    print("coverage limitations:")
    for limitation in result.limitations:
        print(f"- {limitation}")

    print("raw dataset:")
    print(f"raw_total: {stats.raw_total}")
    print(f"raw_missing_required_field_count: {stats.raw_missing_required_field_count}")
    print(f"raw_placeholder_count: {stats.raw_placeholder_count}")
    print(f"raw_error_row_count: {stats.raw_error_row_count}")
    print(f"id_strategy: {result.id_strategy}")

    print("normalized dataset:")
    print(f"total: {stats.total}")
    print(f"rating_distribution: {json.dumps(stats.rating_distribution, sort_keys=True)}")
    print(f"empty_title_count: {stats.empty_title_count}")
    print(f"empty_body_count: {stats.empty_body_count}")
    print(f"duplicate_id_count: {stats.duplicate_id_count}")
    print(f"invalid_rating_count: {stats.invalid_rating_count}")
    print(f"invalid_date_count: {stats.invalid_date_count}")
    print(f"non-US territory count: {stats.non_us_territory_count}")
    print(f"app_id mismatch count: {stats.app_id_mismatch_count}")
    print(f"source_mismatch_count: {stats.source_mismatch_count}")
    print(f"source_unmatched_count: {stats.source_unmatched_count}")
    print(f"metadata_mismatch_count: {stats.metadata_mismatch_count}")

    print("sample_reviews:")
    print(json.dumps([sample.__dict__ for sample in result.samples], ensure_ascii=False, indent=2))

    if result.failures:
        print("failures:")
        for failure in result.failures:
            print(f"- {failure}")
    print(f"Conclusion: {'PASS' if result.passed else 'FAIL'}")


def _read_json_object(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{label} could not be read: {exc!r}")
        return {}
    if not isinstance(payload, dict):
        failures.append(f"{label} must be a JSON object")
        return {}
    return payload


def _extract_list(
    payload: dict[str, Any],
    key: str,
    failures: list[str],
    label: str,
) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        failures.append(f"{label} missing list field: {key}")
        return []
    items = [item for item in value if isinstance(item, dict)]
    if len(items) != len(value):
        failures.append(f"{label} contains non-object rows")
    return items


def _rating_distribution(reviews: list[dict[str, Any]]) -> dict[int, int]:
    counter: Counter[int] = Counter()
    for review in reviews:
        rating = review.get("rating")
        if isinstance(rating, int):
            counter[rating] += 1
    return dict(sorted(counter.items()))


def _duplicate_count(values: list[str]) -> int:
    counter = Counter(value for value in values if value)
    return sum(count - 1 for count in counter.values() if count > 1)


def _build_raw_id_map(raw_items: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], str]:
    review_id_items = {
        _text(item.get("review_id")): item for item in raw_items if _text(item.get("review_id"))
    }
    if review_id_items:
        return review_id_items, "raw review_id from Apify item, mapped to normalized id"

    id_items = {_text(item.get("id")): item for item in raw_items if _text(item.get("id"))}
    if id_items:
        return id_items, "raw id fallback from Apify item, mapped to normalized id"

    return {}, "unavailable: raw records contain no review_id or id"


def _check_metadata(metadata: dict[str, Any], stats: AuditStats, failures: list[str]) -> None:
    expected = {
        "provider": "apify",
        "app_id": TARGET_APP_ID,
        "territory": TARGET_TERRITORY,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            stats.metadata_mismatch_count += 1
            failures.append(f"metadata {key} mismatch: expected {value}, got {metadata.get(key)!r}")

    if metadata.get("actual_count") != stats.total:
        stats.metadata_mismatch_count += 1
        failures.append(
            f"metadata actual_count mismatch: expected {stats.total}, got {metadata.get('actual_count')!r}"
        )

    requested_limit = metadata.get("requested_limit")
    if isinstance(requested_limit, int) and stats.total > requested_limit:
        stats.metadata_mismatch_count += 1
        failures.append(f"normalized total {stats.total} exceeds requested_limit {requested_limit}")

    if not _is_parseable_iso8601(_text(metadata.get("retrieved_at"))):
        stats.metadata_mismatch_count += 1
        failures.append("metadata retrieved_at is not parseable ISO-8601")


def _check_count(actual: int, expected: int, failures: list[str], message: str) -> None:
    if actual != expected:
        failures.append(f"{message}: raw={actual}, normalized={expected}")


def _append_stat_failures(stats: AuditStats, failures: list[str]) -> None:
    checks = [
        ("missing id", stats.missing_id_count),
        ("app_id mismatch", stats.app_id_mismatch_count),
        ("non-US territory", stats.non_us_territory_count),
        ("invalid rating", stats.invalid_rating_count),
        ("missing title and body", stats.missing_title_and_body_count),
        ("invalid date", stats.invalid_date_count),
        ("source mismatch", stats.source_mismatch_count),
        ("duplicate id", stats.duplicate_id_count),
        ("raw missing required fields", stats.raw_missing_required_field_count),
        ("raw placeholder values", stats.raw_placeholder_count),
        ("raw error rows", stats.raw_error_row_count),
        ("source unmatched", stats.source_unmatched_count),
    ]
    for label, count in checks:
        if count:
            failures.append(f"{label}: {count}")


def _has_placeholder_value(item: dict[str, Any]) -> bool:
    placeholders = {"placeholder", "todo", "test", "n/a", "na", "null", "none"}
    for value in item.values():
        if isinstance(value, str) and value.strip().lower() in placeholders:
            return True
    return False


def _is_parseable_iso8601(value: str) -> bool:
    if not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


if __name__ == "__main__":
    raise SystemExit(main())

