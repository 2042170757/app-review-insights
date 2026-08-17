import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.providers import (
    CsvImportProvider,
    JsonImportProvider,
    normalize_apple_rss_entry,
)


class ProviderNormalizationTests(unittest.TestCase):
    def test_apple_review_schema_constraints(self) -> None:
        review = normalize_apple_rss_entry(
            {
                "id": {"label": "review-1"},
                "im:rating": {"label": "5"},
                "title": {"label": "Useful"},
                "content": {"label": ""},
                "author": {"name": {"label": "Reviewer"}},
                "updated": {"label": "2026-08-17T00:08:45-07:00"},
                "im:version": {"label": "1.2.3"},
            },
            app_id="839285684",
            territory="US",
            source_url="https://itunes.apple.com/us/rss/customerreviews/page=1/id=839285684/sortby=mostrecent/json",
        )

        self.assertIsNotNone(review)
        assert review is not None
        self.assertGreaterEqual(review["rating"], 1)
        self.assertLessEqual(review["rating"], 5)
        self.assertEqual(review["territory"], "US")
        self.assertTrue(review["id"])
        self.assertTrue(review["body"] or review["title"])
        datetime.fromisoformat(review["created_at"])

    def test_json_import_provider_runs_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reviews.json"
            path.write_text(
                json.dumps(
                    {
                        "reviews": [
                            {
                                "id": "json-1",
                                "rating": 4,
                                "title": "Title",
                                "body": "",
                                "created_at": "2026-08-17T00:00:00+00:00",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = JsonImportProvider(path).fetch_reviews("app-1", max_reviews=10)

        self.assertFalse(result.errors)
        self.assertEqual(len(result.reviews), 1)
        self.assertEqual(result.reviews[0]["source"], "json_import")

    def test_csv_import_provider_runs_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reviews.csv"
            path.write_text(
                "id,rating,title,body,created_at\n"
                "csv-1,3,,Body,2026-08-17T00:00:00+00:00\n",
                encoding="utf-8",
            )

            result = CsvImportProvider(path).fetch_reviews("app-1", max_reviews=10)

        self.assertFalse(result.errors)
        self.assertEqual(len(result.reviews), 1)
        self.assertEqual(result.reviews[0]["source"], "csv_import")


if __name__ == "__main__":
    unittest.main()

