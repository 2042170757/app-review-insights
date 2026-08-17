"""Phase 0.75 smoke test for Apify-backed US App Store review collection."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, datetime

from app.apify_provider import (
    APIFY_ACTOR_ID,
    ApifyReviewFetchResult,
    ApifyReviewProvider,
    ApifyRunMetadata,
    save_apify_artifacts,
)
from app.providers import ReviewProviderError
from app.url_resolver import parse_app_store_url


TARGET_APP_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"
APIFY_API_TOKEN = "APIFY_API_TOKEN"
MAX_REVIEWS = 50


def main() -> int:
    token = os.environ.get(APIFY_API_TOKEN)
    if not token:
        result = _missing_token_result()
        raw_path, normalized_path, metadata_path = save_apify_artifacts(result)
        print("Authentication: FAIL")
        print("Failure Type: missing token")
        print(f"Missing environment variable: {APIFY_API_TOKEN}")
        print(f"raw_response: {raw_path}")
        print(f"normalized_reviews: {normalized_path}")
        print(f"dataset_metadata: {metadata_path}")
        return 1

    app_ref = parse_app_store_url(TARGET_APP_URL)
    print("provider: apify")
    print("actor: apihq/app-store-reviews-scraper")
    print(f"country: {app_ref.storefront.lower()}")
    print(f"territory: {app_ref.storefront}")
    print(f"app_id: {app_ref.apple_store_app_id}")

    provider = ApifyReviewProvider(api_token=token, territory=app_ref.storefront)
    result = provider.fetch_reviews(app_ref.apple_store_app_id, max_reviews=MAX_REVIEWS)
    raw_path, normalized_path, metadata_path = save_apify_artifacts(result)

    authentication_status = "FAIL" if _has_error(result, "authentication failure") else "PASS"
    actor_status = "FAIL" if _has_error(result, "actor run failure") else "PASS"
    dataset_status = "FAIL" if _has_error(result, "dataset retrieval failure") else "PASS"

    print(f"Authentication: {authentication_status}")
    print(f"Actor Run: {actor_status}")
    print(f"Dataset Retrieval: {dataset_status}")
    print(f"actual_count: {len(result.reviews)}")
    print(f"raw_response: {raw_path}")
    print(f"normalized_reviews: {normalized_path}")
    print(f"dataset_metadata: {metadata_path}")
    print("coverage:")
    print(result.coverage)

    if result.errors:
        print("errors:")
        print(json.dumps([asdict(error) for error in result.errors], ensure_ascii=False, indent=2))

    if not result.reviews:
        print("Apify did not return usable real reviews; smoke test failed.")
        return 1

    print("first_3_reviews:")
    print(json.dumps(result.reviews[:3], ensure_ascii=False, indent=2))
    print("first_review_schema:")
    print(json.dumps(result.reviews[0], ensure_ascii=False, indent=2))
    return 0


def _has_error(result: object, phrase: str) -> bool:
    errors = getattr(result, "errors", [])
    return any(phrase in ((error.message or "") + " " + (error.raw_error or "")).lower() for error in errors)


def _missing_token_result() -> ApifyReviewFetchResult:
    result = ApifyReviewFetchResult(provider="apify")
    result.errors.append(
        ReviewProviderError(
            provider="apify",
            message="missing token: APIFY_API_TOKEN is not configured.",
            source_url=f"https://apify.com/{APIFY_ACTOR_ID}",
        )
    )
    result.coverage = (
        "Third-party Apify actor=apihq/app-store-reviews-scraper was not requested "
        "because APIFY_API_TOKEN is missing."
    )
    result.dataset_metadata = ApifyRunMetadata(
        provider="apify",
        actor=APIFY_ACTOR_ID,
        app_id="839285684",
        territory="US",
        requested_limit=MAX_REVIEWS,
        actual_count=0,
        retrieved_at=datetime.now(UTC).isoformat(),
        is_live=False,
        source_url=f"https://apify.com/{APIFY_ACTOR_ID}",
        limitations=[
            "APIFY_API_TOKEN is required before live Apify review collection can run.",
            "No live request was made in this run.",
            "Apify is a third-party collection provider, not Apple App Store Connect API.",
        ],
        errors=[asdict(error) for error in result.errors],
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
