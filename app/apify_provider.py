"""Apify-backed App Store review provider for Phase 0.75 validation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers import NormalizedReview, ReviewFetchResult, ReviewProviderError


APIFY_ACTOR_ID = "apihq/app-store-reviews-scraper"


@dataclass(frozen=True)
class ApifyRunMetadata:
    provider: str
    actor: str
    app_id: str
    territory: str
    requested_limit: int
    actual_count: int
    retrieved_at: str
    is_live: bool
    source_url: str
    limitations: list[str]
    run_id: str | None = None
    dataset_id: str | None = None
    actor_status: str | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ApifyReviewFetchResult(ReviewFetchResult):
    raw_items: list[dict[str, Any]] = field(default_factory=list)
    dataset_metadata: ApifyRunMetadata | None = None


class ApifyReviewProvider:
    """Fetch App Store reviews through the Apify actor marketplace.

    The provider intentionally stays outside AppleRSSProvider. It implements the
    same ReviewProvider-compatible `fetch_reviews` method and returns the same
    normalized review shape.
    """

    provider_name = "apify"

    def __init__(
        self,
        *,
        api_token: str,
        territory: str = "US",
        actor_id: str = APIFY_ACTOR_ID,
        sort: str = "recent",
    ) -> None:
        if not api_token:
            raise ValueError("APIFY_API_TOKEN is required")
        if not territory:
            raise ValueError("territory is required")
        self.api_token = api_token
        self.territory = territory.upper()
        self.country = territory.lower()
        self.actor_id = actor_id
        self.sort = sort

    def build_actor_input(self, app_id: str, *, max_reviews: int) -> dict[str, Any]:
        return {
            "appIds": [app_id],
            "country": self.country,
            "maxReviews": max_reviews,
            "sort": self.sort,
        }

    def fetch_reviews(self, app_id: str, *, max_reviews: int) -> ApifyReviewFetchResult:
        if max_reviews < 1:
            raise ValueError("max_reviews must be at least 1")

        result = ApifyReviewFetchResult(provider=self.provider_name)
        source_url = f"https://apify.com/{self.actor_id}"
        retrieved_at = datetime.now(UTC).isoformat()
        run_info: dict[str, Any] | None = None
        raw_items: list[dict[str, Any]] = []

        try:
            client = self._build_client()
            run_info = _to_plain_dict(
                client.actor(self.actor_id).call(
                    run_input=self.build_actor_input(app_id, max_reviews=max_reviews)
                )
            )
        except ImportError as exc:
            result.errors.append(
                self._error(
                    "missing dependency",
                    "apify-client is not installed.",
                    raw_error=repr(exc),
                )
            )
            return self._finish_result(result, app_id, max_reviews, retrieved_at, source_url, run_info)
        except Exception as exc:
            result.errors.append(
                self._error(
                    classify_apify_exception(exc),
                    "Apify actor run failed.",
                    raw_error=sanitize_error_message(repr(exc)),
                )
            )
            return self._finish_result(result, app_id, max_reviews, retrieved_at, source_url, run_info)

        actor_status = str(run_info.get("status") or "").upper()
        if actor_status and actor_status != "SUCCEEDED":
            result.errors.append(
                self._error(
                    "actor run failure",
                    f"Apify actor finished with status {actor_status}.",
                    raw_error=sanitize_error_message(json.dumps(run_info, ensure_ascii=False)),
                )
            )
            return self._finish_result(result, app_id, max_reviews, retrieved_at, source_url, run_info)

        dataset_id = _run_value(run_info, "defaultDatasetId", "default_dataset_id")
        if not dataset_id:
            result.errors.append(
                self._error(
                    "dataset retrieval failure",
                    "Apify actor run did not include defaultDatasetId.",
                    raw_error=sanitize_error_message(json.dumps(run_info, ensure_ascii=False)),
                )
            )
            return self._finish_result(result, app_id, max_reviews, retrieved_at, source_url, run_info)

        try:
            raw_items = list(client.dataset(str(dataset_id)).iterate_items())
        except Exception as exc:
            result.errors.append(
                self._error(
                    classify_apify_exception(exc, dataset=True),
                    "Apify dataset retrieval failed.",
                    raw_error=sanitize_error_message(repr(exc)),
                )
            )
            return self._finish_result(
                result,
                app_id,
                max_reviews,
                retrieved_at,
                source_url,
                run_info,
                raw_items,
            )

        result.raw_items = [dict(item) for item in raw_items if isinstance(item, dict)]
        if not result.raw_items:
            result.errors.append(
                self._error(
                    "empty dataset",
                    "Apify dataset returned no review rows.",
                )
            )
            return self._finish_result(
                result,
                app_id,
                max_reviews,
                retrieved_at,
                source_url,
                run_info,
                result.raw_items,
            )

        for item in result.raw_items:
            if item.get("success") is False:
                result.errors.append(
                    self._error(
                        "actor diagnostic row",
                        str(item.get("error") or "Apify returned a diagnostic row."),
                        raw_error=sanitize_error_message(json.dumps(item, ensure_ascii=False)),
                    )
                )
                continue

            try:
                result.reviews.append(
                    normalize_apify_review(
                        item,
                        app_id=app_id,
                        territory=self.territory,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                result.errors.append(
                    self._error(
                        "malformed review",
                        "Apify review row could not be normalized.",
                        raw_error=sanitize_error_message(repr(exc)),
                    )
                )

        if not result.reviews:
            result.errors.append(
                self._error(
                    "empty dataset",
                    "Apify returned rows, but none could be normalized into usable reviews.",
                )
            )

        return self._finish_result(
            result,
            app_id,
            max_reviews,
            retrieved_at,
            source_url,
            run_info,
            result.raw_items,
        )

    def _build_client(self) -> Any:
        from apify_client import ApifyClient

        return ApifyClient(token=self.api_token)

    def _finish_result(
        self,
        result: ApifyReviewFetchResult,
        app_id: str,
        max_reviews: int,
        retrieved_at: str,
        source_url: str,
        run_info: dict[str, Any] | None,
        raw_items: list[dict[str, Any]] | None = None,
    ) -> ApifyReviewFetchResult:
        raw_items = raw_items or result.raw_items
        result.coverage = (
            f"Third-party Apify actor={self.actor_id}, territory={self.territory}, "
            f"requested_limit={max_reviews}, actual_count={len(result.reviews)}. "
            "Reviews are collected from the Apple App Store storefront through Apify."
        )
        result.dataset_metadata = ApifyRunMetadata(
            provider=self.provider_name,
            actor=self.actor_id,
            app_id=app_id,
            territory=self.territory,
            requested_limit=max_reviews,
            actual_count=len(result.reviews),
            retrieved_at=retrieved_at,
            is_live=True,
            source_url=source_url,
            limitations=[
                "Apify is a third-party collection provider, not Apple App Store Connect API.",
                "The requested limit is a maximum target, not a guaranteed count.",
                "Fields, availability, frequency, and accuracy depend on the provider and Apple's storefront behavior.",
                "This smoke test validates up to 50 recent US reviews and does not guarantee complete historical coverage.",
            ],
            run_id=str(run_info.get("id")) if run_info and run_info.get("id") else None,
            dataset_id=str(_run_value(run_info, "defaultDatasetId", "default_dataset_id"))
            if run_info and _run_value(run_info, "defaultDatasetId", "default_dataset_id")
            else None,
            actor_status=str(run_info.get("status")) if run_info and run_info.get("status") else None,
            errors=[asdict(error) for error in result.errors],
        )
        return result

    def _error(self, diagnosis: str, message: str, *, raw_error: str | None = None) -> ReviewProviderError:
        return ReviewProviderError(
            provider=self.provider_name,
            message=f"{diagnosis}: {message}",
            source_url=f"https://apify.com/{self.actor_id}",
            raw_error=raw_error,
            status_code=None,
            page=None,
        )


def normalize_apify_review(
    item: dict[str, Any],
    *,
    app_id: str,
    territory: str,
) -> NormalizedReview:
    review_id = str(item.get("review_id") or item.get("id") or "").strip()
    if not review_id:
        raise ValueError("Apify review id is empty")

    rating = int(item["rating"])
    if rating < 1 or rating > 5:
        raise ValueError(f"Apify rating out of range: {rating}")

    normalized_territory = territory.upper()
    if normalized_territory != "US":
        raise ValueError(f"Apify Phase 0.75 expects US territory, got {normalized_territory}")

    title = str(item.get("title") or "")
    body = str(item.get("text") or item.get("body") or "")
    if not title and not body:
        raise ValueError("Apify review must contain title or body")

    created_at = str(item.get("posted_at") or item.get("created_at") or "")
    if not created_at:
        raise ValueError("Apify review created_at is empty")
    created_at = _parseable_iso8601(created_at)

    return {
        "id": review_id,
        "source": "apify",
        "app_id": str(item.get("app_id") or app_id),
        "territory": normalized_territory,
        "rating": rating,
        "title": title,
        "body": body,
        "author": item.get("user_name") or item.get("author") or None,
        "created_at": created_at,
        "app_version": item.get("app_version") or None,
        "source_url": item.get("url") or None,
    }


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    attrs = {
        key: getattr(value, key)
        for key in ("id", "status", "default_dataset_id", "defaultDatasetId")
        if hasattr(value, key)
    }
    if attrs:
        return attrs
    raise TypeError(f"Unsupported Apify run info type: {type(value).__name__}")


def _run_value(run_info: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = run_info.get(key)
        if value:
            return value
    return None


def classify_apify_exception(exc: Exception, *, dataset: bool = False) -> str:
    text = repr(exc).lower()
    if "401" in text or "unauthorized" in text or "authentication" in text:
        return "authentication failure"
    if "403" in text or "forbidden" in text:
        return "authentication failure"
    if "network" in text or "timeout" in text or "connection" in text:
        return "network failure"
    return "dataset retrieval failure" if dataset else "actor run failure"


def sanitize_error_message(message: str) -> str:
    return message.replace("\n", " ")[:2000]


def save_apify_artifacts(
    result: ApifyReviewFetchResult,
    *,
    raw_dir: Path = Path("artifacts/raw/apify"),
    normalized_dir: Path = Path("artifacts/normalized/apify"),
) -> tuple[Path, Path, Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)

    raw_response_path = raw_dir / "raw_response.json"
    normalized_reviews_path = normalized_dir / "normalized_reviews.json"
    dataset_metadata_path = normalized_dir / "dataset_metadata.json"

    raw_response_path.write_text(
        json.dumps(
            {
                "provider": result.provider,
                "coverage": result.coverage,
                "raw_items": result.raw_items,
                "errors": [asdict(error) for error in result.errors],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    normalized_reviews_path.write_text(
        json.dumps({"reviews": result.reviews}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    dataset_metadata_path.write_text(
        json.dumps(
            asdict(result.dataset_metadata) if result.dataset_metadata else {},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return raw_response_path, normalized_reviews_path, dataset_metadata_path


def _parseable_iso8601(value: str) -> str:
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value
