import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.review_processing import (
    ProcessingConfig,
    load_reviews,
    normalize_datetime_utc,
    process_reviews,
    write_processing_outputs,
)


class ReviewProcessingTests(unittest.TestCase):
    def test_invalid_rating(self) -> None:
        result = process_reviews([{**_review("1"), "rating": 9}])

        self.assertFalse(result.reviews[0].is_valid)
        self.assertIn("invalid_rating", result.reviews[0].validation_errors)

    def test_missing_id(self) -> None:
        review = _review("1")
        review["id"] = ""

        result = process_reviews([review])

        self.assertFalse(result.reviews[0].is_valid)
        self.assertIn("missing_id", result.reviews[0].validation_errors)

    def test_missing_title_body(self) -> None:
        review = _review("1")
        review["title"] = ""
        review["body"] = ""

        result = process_reviews([review])

        self.assertFalse(result.reviews[0].is_valid)
        self.assertIn("missing_title_body", result.reviews[0].validation_errors)

    def test_invalid_date(self) -> None:
        result = process_reviews([{**_review("1"), "created_at": "not-a-date"}])

        self.assertFalse(result.reviews[0].is_valid)
        self.assertIn("invalid_created_at", result.reviews[0].validation_errors)

    def test_normalization(self) -> None:
        result = process_reviews(
            [
                {
                    **_review("1"),
                    "rating": "4",
                    "title": "  Great\n\nApp  ",
                    "body": "",
                    "created_at": "2026-08-15T00:29:48-07:00",
                }
            ]
        )
        review = result.reviews[0]

        self.assertEqual(review.rating, 4)
        self.assertEqual(review.title, "Great App")
        self.assertIsNone(review.body)
        self.assertEqual(review.created_at, "2026-08-15T07:29:48Z")

    def test_raw_text_preservation(self) -> None:
        raw_body = "  Keep\n  spacing evidence "

        result = process_reviews([{**_review("1"), "body": raw_body}])

        self.assertEqual(result.reviews[0].raw_body, raw_body)
        self.assertEqual(result.reviews[0].clean_body, "Keep spacing evidence")
        self.assertEqual(result.reviews[0].raw_review["body"], raw_body)

    def test_language_detection(self) -> None:
        reviews = [
            {**_review("en"), "body": "This app is useful and simple"},
            {**_review("zh"), "body": "这个应用很好用"},
            {**_review("es"), "body": "Esta app es excelente para mi"},
            {**_review("fr"), "body": "Cette app est très utile pour moi"},
            {**_review("other"), "title": "", "body": "🙂🙂🙂"},
        ]

        result = process_reviews(reviews)

        self.assertEqual([review.language for review in result.reviews], ["en", "zh", "es", "fr", "other"])
        self.assertTrue(all(review.language_confidence >= 0 for review in result.reviews))

    def test_exact_duplicate(self) -> None:
        result = process_reviews([_review("1"), _review("2")])

        self.assertTrue(all(review.is_duplicate for review in result.reviews))
        self.assertTrue(result.reviews[0].is_representative)
        self.assertFalse(result.reviews[1].is_representative)
        self.assertEqual(result.report.exact_duplicate_count, 2)
        self.assertEqual(result.report.retained_count, 1)

    def test_near_duplicate(self) -> None:
        reviews = [
            {**_review("1"), "title": "Login problem", "body": "Login fails every morning"},
            {**_review("2"), "title": "Login problem", "body": "Login fails every morning for me"},
        ]

        result = process_reviews(
            reviews,
            config=ProcessingConfig(near_duplicate_threshold=0.5),
        )

        self.assertTrue(result.reviews[0].near_duplicate_candidate)
        self.assertTrue(result.reviews[1].near_duplicate_candidate)
        self.assertEqual(result.report.near_duplicate_count, 2)

    def test_statistics(self) -> None:
        reviews = [
            {**_review("1"), "rating": 5, "app_version": "1.0"},
            {**_review("2"), "rating": 1, "created_at": "2026-08-16T00:00:00Z", "app_version": "1.1"},
        ]

        result = process_reviews(reviews)

        self.assertEqual(result.statistics["total"], 2)
        self.assertEqual(result.statistics["valid"], 2)
        self.assertEqual(result.statistics["rating_distribution"], {1: 1, 5: 1})
        self.assertEqual(result.statistics["average_rating"], 3.0)
        self.assertEqual(result.statistics["reviews_by_app_version"], {"1.0": 1, "1.1": 1})

    def test_processing_report_and_outputs(self) -> None:
        result = process_reviews([_review("1"), {**_review("2"), "rating": 8}])

        with TemporaryDirectory() as temp_dir:
            paths = write_processing_outputs(result, output_dir=Path(temp_dir))

            self.assertTrue(paths["reviews_json"].is_file())
            self.assertTrue(paths["reviews_csv"].is_file())
            self.assertTrue(paths["statistics"].is_file())
            self.assertTrue(paths["processing_report"].is_file())
            report = json.loads(paths["processing_report"].read_text(encoding="utf-8"))

        self.assertEqual(report["input_count"], 2)
        self.assertEqual(report["valid_count"], 1)
        self.assertEqual(report["invalid_count"], 1)
        self.assertEqual(report["exclusion_reasons"]["invalid_rating"], 1)

    def test_json_input(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reviews.json"
            path.write_text(json.dumps({"reviews": [_review("json-1")]}), encoding="utf-8")

            reviews = load_reviews(path)

        self.assertEqual(reviews[0]["id"], "json-1")

    def test_csv_input(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reviews.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(_review("csv-1").keys()))
                writer.writeheader()
                writer.writerow(_review("csv-1"))

            reviews = load_reviews(path)

        self.assertEqual(reviews[0]["id"], "csv-1")

    def test_generalizes_across_apps(self) -> None:
        reviews = [
            _review("app-a-1", app_id="app-a"),
            {
                **_review("app-b-1", app_id="app-b"),
                "territory": "CA",
                "title": "Different product",
                "body": "A different valid review for another app",
            },
        ]

        result = process_reviews(reviews)

        self.assertEqual(result.statistics["valid"], 2)
        self.assertEqual({review.app_id for review in result.reviews}, {"app-a", "app-b"})

    def test_normalize_datetime_utc(self) -> None:
        self.assertEqual(
            normalize_datetime_utc("2026-08-15T00:29:48+02:00"),
            "2026-08-14T22:29:48Z",
        )


def _review(review_id: str, *, app_id: str = "example-app") -> dict:
    return {
        "id": review_id,
        "source": "fixture",
        "app_id": app_id,
        "territory": "US",
        "rating": 5,
        "title": "Great app",
        "body": "This app is useful and simple",
        "author": "Reviewer",
        "created_at": "2026-08-15T00:29:48Z",
        "app_version": "1.0",
        "source_url": "https://example.test/reviews",
    }


if __name__ == "__main__":
    unittest.main()
