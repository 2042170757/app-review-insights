# App Review Insights

Phase 0 implements a Review Collector smoke test only. It does not include a React frontend, AI pipeline, PRD generation, requirement generation, test case generation, or database integration.

## Requirements

- Python 3.11+
- No third-party Python package is required for Phase 0.

## Run The Smoke Test

```bash
python -m app.collector_smoke_test
```

The command:

1. Parses the target US App Store URL.
2. Prints `app_id` and `storefront`.
3. Requests Apple's public US customer review RSS JSON feed.
4. Fetches real reviews with pagination and a maximum review limit.
5. Prints the first 3 normalized reviews.
6. Saves raw Apple RSS responses under `artifacts/raw/`.
7. Saves normalized reviews under `artifacts/normalized/`.

## Run Unit Tests

```bash
python -m unittest discover -s tests
```

The unit tests cover App Store URL parsing, invalid URLs, missing app ids, normalized review constraints, and offline JSON/CSV import providers.

## Data Source

The live collector uses Apple's public customer review RSS JSON endpoint:

```text
https://itunes.apple.com/{storefront}/rss/customerreviews/page={page}/id={apple_store_app_id}/sortby=mostrecent/json
```

For the Phase 0 smoke test, the storefront is explicitly resolved from the App Store URL and passed to `AppleRSSProvider`. The target run uses `US`.

## Data Limits

- Apple RSS is a public feed and may be unavailable, rate limited, incomplete, or changed by Apple without notice.
- Results are scoped to a storefront, such as `US`.
- Pagination is limited by Apple's RSS behavior and by this smoke test's configured `max_pages` and `max_reviews`.
- Phase 0 does not claim complete historical coverage.
- If Apple RSS fails, the smoke test reports structured errors and does not fabricate review data.

