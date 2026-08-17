"""Review provider interfaces and Phase 0 provider implementations."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class NormalizedReview(TypedDict):
    id: str
    source: str
    app_id: str
    territory: str
    rating: int
    title: str
    body: str
    author: str | None
    created_at: str
    app_version: str | None
    source_url: str


@dataclass(frozen=True)
class RawResponse:
    page: int | None
    source_url: str
    status_code: int | None
    body: str


@dataclass(frozen=True)
class ReviewProviderError:
    provider: str
    message: str
    source_url: str | None = None
    page: int | None = None
    status_code: int | None = None
    raw_error: str | None = None


@dataclass
class ReviewFetchResult:
    provider: str
    reviews: list[NormalizedReview] = field(default_factory=list)
    raw_responses: list[RawResponse] = field(default_factory=list)
    errors: list[ReviewProviderError] = field(default_factory=list)
    coverage: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors


class ReviewProvider(Protocol):
    provider_name: str

    def fetch_reviews(
        self,
        app_id: str,
        *,
        max_reviews: int,
    ) -> ReviewFetchResult:
        """Fetch or import reviews and return normalized records."""


def _label(value: Any) -> str | None:
    if isinstance(value, dict):
        label = value.get("label")
        if label is None:
            return None
        return str(label)
    if value is None:
        return None
    return str(value)


def _require_parseable_datetime(value: str) -> str:
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def normalize_apple_rss_entry(
    entry: dict[str, Any],
    *,
    app_id: str,
    territory: str,
    source_url: str,
) -> NormalizedReview | None:
    """Convert one Apple RSS review entry into the unified review schema."""

    rating_label = _label(entry.get("im:rating"))
    if rating_label is None:
        return None

    rating = int(rating_label)
    if rating < 1 or rating > 5:
        raise ValueError(f"Apple RSS rating out of range: {rating}")

    review_id = _label(entry.get("id"))
    if not review_id:
        raise ValueError("Apple RSS review id is empty")

    title = _label(entry.get("title")) or ""
    body = _label(entry.get("content")) or ""
    if not title and not body:
        raise ValueError("Apple RSS review must contain title or body")

    created_at = _label(entry.get("updated"))
    if not created_at:
        raise ValueError("Apple RSS review created_at is empty")
    created_at = _require_parseable_datetime(created_at)

    author = None
    author_value = entry.get("author")
    if isinstance(author_value, dict):
        author = _label(author_value.get("name"))

    return {
        "id": review_id,
        "source": "apple_rss",
        "app_id": app_id,
        "territory": territory.upper(),
        "rating": rating,
        "title": title,
        "body": body,
        "author": author,
        "created_at": created_at,
        "app_version": _label(entry.get("im:version")),
        "source_url": source_url,
    }


class AppleRSSProvider:
    """Fetch public App Store customer reviews from Apple's RSS JSON feed."""

    provider_name = "apple_rss"

    def __init__(
        self,
        *,
        storefront: str,
        max_pages: int = 10,
        timeout_seconds: float = 20.0,
    ) -> None:
        if not storefront:
            raise ValueError("AppleRSSProvider requires an explicit storefront")
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        self.storefront = storefront.lower()
        self.territory = storefront.upper()
        self.max_pages = max_pages
        self.timeout_seconds = timeout_seconds

    def build_page_url(self, app_id: str, page: int) -> str:
        return (
            f"https://itunes.apple.com/{self.storefront}/rss/customerreviews/"
            f"page={page}/id={app_id}/sortby=mostrecent/json"
        )

    def fetch_reviews(
        self,
        app_id: str,
        *,
        max_reviews: int,
    ) -> ReviewFetchResult:
        if max_reviews < 1:
            raise ValueError("max_reviews must be at least 1")

        result = ReviewFetchResult(provider=self.provider_name)
        seen_ids: set[str] = set()

        for page in range(1, self.max_pages + 1):
            source_url = self.build_page_url(app_id, page)
            try:
                body = self._request(source_url)
                result.raw_responses.append(
                    RawResponse(page=page, source_url=source_url, status_code=200, body=body)
                )
                payload = json.loads(body)
                entries = self._extract_entries(payload)
            except HTTPError as exc:
                raw_error = exc.read().decode("utf-8", errors="replace")
                result.errors.append(
                    ReviewProviderError(
                        provider=self.provider_name,
                        message=f"Apple RSS HTTP error: {exc.reason}",
                        source_url=source_url,
                        page=page,
                        status_code=exc.code,
                        raw_error=raw_error,
                    )
                )
                break
            except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                result.errors.append(
                    ReviewProviderError(
                        provider=self.provider_name,
                        message="Apple RSS request or JSON parse failed",
                        source_url=source_url,
                        page=page,
                        raw_error=repr(exc),
                    )
                )
                break

            page_review_count = 0
            for entry in entries:
                try:
                    review = normalize_apple_rss_entry(
                        entry,
                        app_id=app_id,
                        territory=self.territory,
                        source_url=source_url,
                    )
                except (TypeError, ValueError) as exc:
                    result.errors.append(
                        ReviewProviderError(
                            provider=self.provider_name,
                            message="Apple RSS review normalization failed",
                            source_url=source_url,
                            page=page,
                            raw_error=repr(exc),
                        )
                    )
                    continue

                if review is None or review["id"] in seen_ids:
                    continue
                seen_ids.add(review["id"])
                result.reviews.append(review)
                page_review_count += 1
                if len(result.reviews) >= max_reviews:
                    break

            if len(result.reviews) >= max_reviews or page_review_count == 0:
                break

        if result.raw_responses and not result.reviews:
            result.errors.append(
                ReviewProviderError(
                    provider=self.provider_name,
                    message="Apple RSS returned no review entries",
                    source_url=result.raw_responses[-1].source_url,
                    page=result.raw_responses[-1].page,
                    status_code=result.raw_responses[-1].status_code,
                    raw_error="Feed response contained no review entry objects.",
                )
            )

        result.coverage = (
            f"Apple public Customer Reviews RSS feed, territory={self.territory}, "
            f"pages_requested={len(result.raw_responses)}, max_pages={self.max_pages}, "
            f"max_reviews={max_reviews}. Feed is sorted by most recent reviews."
        )
        return result

    def _request(self, source_url: str) -> str:
        request = Request(
            source_url,
            headers={
                "Accept": "application/json,text/javascript,*/*",
                "User-Agent": "app-review-insights-phase0/0.1",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")

    @staticmethod
    def _extract_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
        feed = payload.get("feed")
        if not isinstance(feed, dict):
            return []
        entries = feed.get("entry", [])
        if isinstance(entries, dict):
            return [entries]
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, dict)]


class JsonImportProvider:
    """Import already-collected review JSON into the unified schema."""

    provider_name = "json_import"

    def __init__(self, path: str | Path, *, territory: str = "US") -> None:
        self.path = Path(path)
        self.territory = territory.upper()

    def fetch_reviews(self, app_id: str, *, max_reviews: int) -> ReviewFetchResult:
        result = ReviewFetchResult(provider=self.provider_name)
        source_url = str(self.path)
        try:
            body = self.path.read_text(encoding="utf-8")
            payload = json.loads(body)
            result.raw_responses.append(
                RawResponse(page=None, source_url=source_url, status_code=None, body=body)
            )
            rows = payload.get("reviews", payload) if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                raise ValueError("JSON import must contain a list or {'reviews': list}")
            for row in rows[:max_reviews]:
                result.reviews.append(
                    _normalize_import_row(
                        row,
                        app_id=app_id,
                        territory=self.territory,
                        source="json_import",
                        source_url=source_url,
                    )
                )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            result.errors.append(
                ReviewProviderError(
                    provider=self.provider_name,
                    message="JSON import failed",
                    source_url=source_url,
                    raw_error=repr(exc),
                )
            )
        result.coverage = "Local JSON import provider; no live App Store request is made."
        return result


class CsvImportProvider:
    """Import review CSV rows into the unified schema."""

    provider_name = "csv_import"

    def __init__(self, path: str | Path, *, territory: str = "US") -> None:
        self.path = Path(path)
        self.territory = territory.upper()

    def fetch_reviews(self, app_id: str, *, max_reviews: int) -> ReviewFetchResult:
        result = ReviewFetchResult(provider=self.provider_name)
        source_url = str(self.path)
        try:
            body = self.path.read_text(encoding="utf-8")
            result.raw_responses.append(
                RawResponse(page=None, source_url=source_url, status_code=None, body=body)
            )
            rows = list(csv.DictReader(body.splitlines()))
            for row in rows[:max_reviews]:
                result.reviews.append(
                    _normalize_import_row(
                        row,
                        app_id=app_id,
                        territory=self.territory,
                        source="csv_import",
                        source_url=source_url,
                    )
                )
        except (OSError, csv.Error, TypeError, ValueError) as exc:
            result.errors.append(
                ReviewProviderError(
                    provider=self.provider_name,
                    message="CSV import failed",
                    source_url=source_url,
                    raw_error=repr(exc),
                )
            )
        result.coverage = "Local CSV import provider; no live App Store request is made."
        return result


def _normalize_import_row(
    row: Any,
    *,
    app_id: str,
    territory: str,
    source: Literal["json_import", "csv_import"],
    source_url: str,
) -> NormalizedReview:
    if not isinstance(row, dict):
        raise TypeError("Imported review row must be an object")

    rating = int(row["rating"])
    if rating < 1 or rating > 5:
        raise ValueError(f"Imported rating out of range: {rating}")

    review_id = str(row.get("id") or "").strip()
    if not review_id:
        raise ValueError("Imported review id is empty")

    title = str(row.get("title") or "")
    body = str(row.get("body") or "")
    if not title and not body:
        raise ValueError("Imported review must contain title or body")

    created_at = _require_parseable_datetime(str(row["created_at"]))

    return {
        "id": review_id,
        "source": source,
        "app_id": str(row.get("app_id") or app_id),
        "territory": str(row.get("territory") or territory).upper(),
        "rating": rating,
        "title": title,
        "body": body,
        "author": row.get("author") or None,
        "created_at": created_at,
        "app_version": row.get("app_version") or None,
        "source_url": str(row.get("source_url") or source_url),
    }
