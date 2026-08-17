"""Phase 0.75 smoke test for Apify-backed US App Store review collection."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

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
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class ApifySmokeStatuses:
    authentication: str
    provider_dependency: str
    actor_run: str
    dataset_retrieval: str
    reviews: str


def main() -> int:
    load_apify_environment()
    token = os.environ.get(APIFY_API_TOKEN)
    if not token:
        result = _missing_token_result()
        raw_path, normalized_path, metadata_path = save_apify_artifacts(result)
        statuses = determine_smoke_statuses(result, token_present=False)
        print(f"Authentication: {statuses.authentication}")
        print(f"Provider Dependency: {statuses.provider_dependency}")
        print(f"Actor Run: {statuses.actor_run}")
        print(f"Dataset Retrieval: {statuses.dataset_retrieval}")
        print(f"Reviews: {statuses.reviews}")
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

    statuses = determine_smoke_statuses(result, token_present=True)

    print(f"Authentication: {statuses.authentication}")
    print(f"Provider Dependency: {statuses.provider_dependency}")
    print(f"Actor Run: {statuses.actor_run}")
    print(f"Dataset Retrieval: {statuses.dataset_retrieval}")
    print(f"Reviews: {statuses.reviews}")
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


def determine_smoke_statuses(
    result: ApifyReviewFetchResult,
    *,
    token_present: bool,
) -> ApifySmokeStatuses:
    if not token_present:
        return ApifySmokeStatuses(
            authentication="FAIL",
            provider_dependency="SKIPPED",
            actor_run="SKIPPED",
            dataset_retrieval="SKIPPED",
            reviews="SKIPPED",
        )

    if _has_error(result, "missing dependency"):
        return ApifySmokeStatuses(
            authentication="PASS",
            provider_dependency="FAIL",
            actor_run="SKIPPED",
            dataset_retrieval="SKIPPED",
            reviews="SKIPPED",
        )

    if _has_error(result, "authentication failure"):
        return ApifySmokeStatuses(
            authentication="FAIL",
            provider_dependency="PASS",
            actor_run="SKIPPED",
            dataset_retrieval="SKIPPED",
            reviews="SKIPPED",
        )

    actor_failed = _has_error(result, "actor run failure") or _has_error(result, "network failure")
    if actor_failed and not _has_dataset_id(result):
        return ApifySmokeStatuses(
            authentication="PASS",
            provider_dependency="PASS",
            actor_run="FAIL",
            dataset_retrieval="SKIPPED",
            reviews="SKIPPED",
        )

    if not _actor_succeeded(result):
        return ApifySmokeStatuses(
            authentication="PASS",
            provider_dependency="PASS",
            actor_run="SKIPPED",
            dataset_retrieval="SKIPPED",
            reviews="SKIPPED",
        )

    if _has_error(result, "dataset retrieval failure") or (
        _has_error(result, "network failure") and _has_dataset_id(result)
    ):
        return ApifySmokeStatuses(
            authentication="PASS",
            provider_dependency="PASS",
            actor_run="PASS",
            dataset_retrieval="FAIL",
            reviews="SKIPPED",
        )

    if not _has_dataset_id(result):
        return ApifySmokeStatuses(
            authentication="PASS",
            provider_dependency="PASS",
            actor_run="PASS",
            dataset_retrieval="SKIPPED",
            reviews="SKIPPED",
        )

    if result.reviews:
        return ApifySmokeStatuses(
            authentication="PASS",
            provider_dependency="PASS",
            actor_run="PASS",
            dataset_retrieval="PASS",
            reviews="PASS",
        )

    if _has_error(result, "empty dataset"):
        return ApifySmokeStatuses(
            authentication="PASS",
            provider_dependency="PASS",
            actor_run="PASS",
            dataset_retrieval="PASS",
            reviews="EMPTY",
        )

    return ApifySmokeStatuses(
        authentication="PASS",
        provider_dependency="PASS",
        actor_run="PASS",
        dataset_retrieval="PASS",
        reviews="SKIPPED",
    )


def _actor_succeeded(result: ApifyReviewFetchResult) -> bool:
    metadata = result.dataset_metadata
    if not metadata:
        return False
    status = (metadata.actor_status or "").upper()
    return status == "SUCCEEDED"


def _has_dataset_id(result: ApifyReviewFetchResult) -> bool:
    metadata = result.dataset_metadata
    return bool(metadata and metadata.dataset_id)


def load_apify_environment(dotenv_path: Path = DOTENV_PATH) -> bool:
    """Load project .env without overriding existing system environment values."""

    if not dotenv_path.is_file():
        return False

    from dotenv import load_dotenv

    return bool(load_dotenv(dotenv_path=dotenv_path, override=False))


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
