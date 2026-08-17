"""Utilities for resolving App Store URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


class AppStoreUrlError(ValueError):
    """Raised when a URL is not a supported App Store app URL."""


@dataclass(frozen=True)
class AppStoreAppRef:
    storefront: str
    apple_store_app_id: str


_APP_ID_RE = re.compile(r"^id(?P<app_id>\d+)$")


def parse_app_store_url(url: str) -> AppStoreAppRef:
    """Parse an apps.apple.com app URL into storefront and app id.

    Example:
        https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684
        -> storefront="US", apple_store_app_id="839285684"
    """

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise AppStoreUrlError("App Store URL must use http or https")

    host = parsed.netloc.lower()
    if host != "apps.apple.com":
        raise AppStoreUrlError("URL host must be apps.apple.com")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        raise AppStoreUrlError("App Store URL is missing storefront or app id")

    storefront = path_parts[0]
    if not re.fullmatch(r"[A-Za-z]{2}", storefront):
        raise AppStoreUrlError("App Store storefront must be a two-letter code")

    app_id: str | None = None
    for part in path_parts:
        match = _APP_ID_RE.match(part)
        if match:
            app_id = match.group("app_id")
            break

    if app_id is None:
        raise AppStoreUrlError("App Store URL is missing an id<digits> app id segment")

    return AppStoreAppRef(storefront=storefront.upper(), apple_store_app_id=app_id)

