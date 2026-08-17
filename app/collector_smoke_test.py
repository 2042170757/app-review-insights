"""Phase 0 smoke test command for real US App Store review collection."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.providers import AppleRSSProvider, ReviewFetchResult
from app.url_resolver import parse_app_store_url


TARGET_APP_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"
RAW_DIR = Path("artifacts/raw")
NORMALIZED_DIR = Path("artifacts/normalized")


def main() -> int:
    app_ref = parse_app_store_url(TARGET_APP_URL)
    print(f"app_id: {app_ref.apple_store_app_id}")
    print(f"storefront: {app_ref.storefront}")

    provider = AppleRSSProvider(storefront=app_ref.storefront, max_pages=10)
    result = provider.fetch_reviews(app_ref.apple_store_app_id, max_reviews=100)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    raw_path = RAW_DIR / f"apple_rss_{app_ref.storefront}_{app_ref.apple_store_app_id}_{stamp}.json"
    normalized_path = (
        NORMALIZED_DIR / f"apple_rss_{app_ref.storefront}_{app_ref.apple_store_app_id}_{stamp}.json"
    )
    _save_outputs(result, raw_path, normalized_path)

    print(f"provider: {result.provider}")
    print(f"requested_pages: {len(result.raw_responses)}")
    print(f"fetched_reviews: {len(result.reviews)}")
    print(f"raw_json: {raw_path}")
    print(f"normalized_json: {normalized_path}")
    print("coverage:")
    print(result.coverage)

    if result.errors:
        print("errors:")
        print(json.dumps([asdict(error) for error in result.errors], ensure_ascii=False, indent=2))

    if not result.reviews:
        print("Apple RSS did not return usable real reviews; smoke test failed.")
        return 1

    print("first_3_reviews:")
    print(json.dumps(result.reviews[:3], ensure_ascii=False, indent=2))
    print("data_limits:")
    print(
        "- Uses Apple's public RSS customer review feed only.\n"
        "- Coverage is limited by storefront, Apple's RSS availability, page depth, and feed ordering.\n"
        "- This smoke test does not guarantee complete historical review coverage."
    )
    return 0


def _save_outputs(result: ReviewFetchResult, raw_path: Path, normalized_path: Path) -> None:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    raw_payload = {
        "provider": result.provider,
        "coverage": result.coverage,
        "raw_responses": [asdict(response) for response in result.raw_responses],
        "errors": [asdict(error) for error in result.errors],
    }
    raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    normalized_path.write_text(
        json.dumps({"reviews": result.reviews}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())

