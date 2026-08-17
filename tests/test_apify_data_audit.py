import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.apify_data_audit import audit_apify_artifacts


class ApifyDataAuditTests(unittest.TestCase):
    def test_valid_audit_passes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            paths = _write_artifacts(
                Path(temp_dir),
                raw_items=[
                    {
                        "success": True,
                        "review_id": "review-1",
                        "app_id": "839285684",
                        "rating": 5,
                        "title": "Title",
                        "text": "Body",
                        "posted_at": "2026-08-15T00:29:48Z",
                    }
                ],
                reviews=[
                    {
                        "id": "review-1",
                        "source": "apify",
                        "app_id": "839285684",
                        "territory": "US",
                        "rating": 5,
                        "title": "Title",
                        "body": "Body",
                        "author": None,
                        "created_at": "2026-08-15T00:29:48Z",
                        "app_version": None,
                        "source_url": None,
                    }
                ],
                actual_count=1,
            )

            result = audit_apify_artifacts(
                raw_path=paths["raw"],
                normalized_path=paths["normalized"],
                metadata_path=paths["metadata"],
            )

        self.assertTrue(result.passed)
        self.assertEqual(result.stats.total, 1)
        self.assertEqual(result.stats.rating_distribution, {5: 1})
        self.assertEqual(result.id_strategy, "raw review_id from Apify item, mapped to normalized id")

    def test_invalid_normalized_review_fails_with_counts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            paths = _write_artifacts(
                Path(temp_dir),
                raw_items=[
                    {
                        "success": True,
                        "review_id": "review-1",
                        "app_id": "839285684",
                        "rating": 5,
                        "title": "Title",
                        "text": "Body",
                        "posted_at": "2026-08-15T00:29:48Z",
                    }
                ],
                reviews=[
                    {
                        "id": "review-1",
                        "source": "not_apify",
                        "app_id": "bad",
                        "territory": "CN",
                        "rating": 6,
                        "title": "",
                        "body": "",
                        "author": None,
                        "created_at": "bad-date",
                        "app_version": None,
                        "source_url": None,
                    }
                ],
                actual_count=1,
            )

            result = audit_apify_artifacts(
                raw_path=paths["raw"],
                normalized_path=paths["normalized"],
                metadata_path=paths["metadata"],
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.stats.app_id_mismatch_count, 1)
        self.assertEqual(result.stats.non_us_territory_count, 1)
        self.assertEqual(result.stats.invalid_rating_count, 1)
        self.assertEqual(result.stats.invalid_date_count, 1)
        self.assertEqual(result.stats.missing_title_and_body_count, 1)
        self.assertEqual(result.stats.source_mismatch_count, 1)

    def test_duplicate_and_raw_count_mismatch_fail(self) -> None:
        with TemporaryDirectory() as temp_dir:
            paths = _write_artifacts(
                Path(temp_dir),
                raw_items=[
                    {
                        "success": True,
                        "review_id": "review-1",
                        "app_id": "839285684",
                        "rating": 5,
                        "title": "Title",
                        "text": "Body",
                        "posted_at": "2026-08-15T00:29:48Z",
                    }
                ],
                reviews=[
                    _review("review-1"),
                    _review("review-1"),
                ],
                actual_count=2,
            )

            result = audit_apify_artifacts(
                raw_path=paths["raw"],
                normalized_path=paths["normalized"],
                metadata_path=paths["metadata"],
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.stats.duplicate_id_count, 1)
        self.assertTrue(any("raw / normalized counts differ" in failure for failure in result.failures))

    def test_metadata_mismatch_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            paths = _write_artifacts(
                Path(temp_dir),
                raw_items=[
                    {
                        "success": True,
                        "review_id": "review-1",
                        "app_id": "839285684",
                        "rating": 5,
                        "title": "Title",
                        "text": "Body",
                        "posted_at": "2026-08-15T00:29:48Z",
                    }
                ],
                reviews=[_review("review-1")],
                actual_count=2,
            )

            result = audit_apify_artifacts(
                raw_path=paths["raw"],
                normalized_path=paths["normalized"],
                metadata_path=paths["metadata"],
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.stats.metadata_mismatch_count, 1)
        self.assertTrue(any("metadata actual_count mismatch" in failure for failure in result.failures))

    def test_raw_without_review_id_reports_id_strategy(self) -> None:
        with TemporaryDirectory() as temp_dir:
            paths = _write_artifacts(
                Path(temp_dir),
                raw_items=[
                    {
                        "success": True,
                        "id": "review-1",
                        "app_id": "839285684",
                        "rating": 5,
                        "title": "Title",
                        "text": "Body",
                        "posted_at": "2026-08-15T00:29:48Z",
                    }
                ],
                reviews=[_review("review-1")],
                actual_count=1,
            )

            result = audit_apify_artifacts(
                raw_path=paths["raw"],
                normalized_path=paths["normalized"],
                metadata_path=paths["metadata"],
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.id_strategy, "raw id fallback from Apify item, mapped to normalized id")
        self.assertEqual(result.stats.raw_missing_required_field_count, 1)


def _write_artifacts(
    root: Path,
    *,
    raw_items: list[dict],
    reviews: list[dict],
    actual_count: int,
) -> dict[str, Path]:
    raw_path = root / "raw_response.json"
    normalized_path = root / "normalized_reviews.json"
    metadata_path = root / "dataset_metadata.json"
    raw_path.write_text(json.dumps({"raw_items": raw_items}), encoding="utf-8")
    normalized_path.write_text(json.dumps({"reviews": reviews}), encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "provider": "apify",
                "actor": "apihq/app-store-reviews-scraper",
                "app_id": "839285684",
                "territory": "US",
                "requested_limit": 50,
                "actual_count": actual_count,
                "retrieved_at": "2026-08-17T08:08:31.532715+00:00",
                "limitations": ["third-party provider"],
            }
        ),
        encoding="utf-8",
    )
    return {"raw": raw_path, "normalized": normalized_path, "metadata": metadata_path}


def _review(review_id: str) -> dict:
    return {
        "id": review_id,
        "source": "apify",
        "app_id": "839285684",
        "territory": "US",
        "rating": 5,
        "title": "Title",
        "body": "Body",
        "author": None,
        "created_at": "2026-08-15T00:29:48Z",
        "app_version": None,
        "source_url": None,
    }


if __name__ == "__main__":
    unittest.main()

