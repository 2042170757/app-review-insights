import json
import os
import tempfile
import unittest
from pathlib import Path

from app.imports import create_import_dataset
from app.workflow.pipeline import BackendPipelineRunner


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class ImportWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_cwd = Path.cwd()
        os.chdir(self.tempdir.name)

    def tearDown(self) -> None:
        os.chdir(self.previous_cwd)
        self.tempdir.cleanup()

    def test_json_import_collection_writes_unified_schema_then_processing_runs(self) -> None:
        dataset = create_import_dataset(
            source_type="json",
            filename="reviews.json",
            content=json.dumps({"reviews": [_review("json-1")]}).encode("utf-8"),
            app_id="839285684",
        )
        runner = BackendPipelineRunner()
        context = _context(dataset)

        collection = runner.run_stage(stage="collection", context=context)
        processing = runner.run_stage(stage="processing", context=context)

        normalized = json.loads(Path("artifacts/normalized/import/normalized_reviews.json").read_text(encoding="utf-8"))
        processed = json.loads(Path("artifacts/processed/reviews.json").read_text(encoding="utf-8"))
        self.assertEqual(collection.summary["display_source"], "Imported JSON")
        self.assertEqual(normalized["reviews"][0]["source"], "json_import")
        self.assertEqual(processing.summary["input_count"], 1)
        self.assertEqual(processed["reviews"][0]["raw_review"]["id"], "json-1")

    def test_csv_import_collection_writes_unified_schema_then_processing_runs(self) -> None:
        dataset = create_import_dataset(
            source_type="csv",
            filename="reviews.csv",
            content=b"id,rating,title,body,created_at\ncsv-1,5,Title,,2026-08-17T00:00:00Z\n",
            app_id="839285684",
        )
        runner = BackendPipelineRunner()
        context = _context(dataset)

        collection = runner.run_stage(stage="collection", context=context)
        processing = runner.run_stage(stage="processing", context=context)

        normalized = json.loads(Path("artifacts/normalized/import/normalized_reviews.json").read_text(encoding="utf-8"))
        self.assertEqual(collection.summary["display_source"], "Imported CSV")
        self.assertEqual(normalized["reviews"][0]["source"], "csv_import")
        self.assertEqual(processing.summary["valid_count"], 1)

    def test_json_import_processing_applies_rating_filter(self) -> None:
        dataset = create_import_dataset(
            source_type="json",
            filename="reviews.json",
            content=json.dumps({"reviews": [_review("json-1", rating=1), _review("json-5", rating=5)]}).encode("utf-8"),
            app_id="839285684",
        )
        runner = BackendPipelineRunner()
        context = _context(dataset, constraints={"rating": {"min": 1, "max": 2}})

        runner.run_stage(stage="collection", context=context)
        processing = runner.run_stage(stage="processing", context=context)

        selected = json.loads(Path("artifacts/processed/reviews.json").read_text(encoding="utf-8"))["reviews"]
        full = json.loads(Path("artifacts/processed/reviews_all.json").read_text(encoding="utf-8"))["reviews"]
        self.assertEqual([review["id"] for review in selected], ["json-1"])
        self.assertEqual(len(full), 2)
        self.assertEqual(processing.summary["selected_count"], 1)
        self.assertEqual(processing.summary["excluded_count"], 1)

    def test_csv_import_processing_applies_rating_filter(self) -> None:
        dataset = create_import_dataset(
            source_type="csv",
            filename="reviews.csv",
            content=(
                b"id,rating,title,body,created_at\n"
                b"csv-1,1,Title,,2026-08-17T00:00:00Z\n"
                b"csv-5,5,Title,,2026-08-17T00:00:00Z\n"
            ),
            app_id="839285684",
        )
        runner = BackendPipelineRunner()
        context = _context(dataset, constraints={"rating": {"min": 4, "max": 5}})

        runner.run_stage(stage="collection", context=context)
        runner.run_stage(stage="processing", context=context)

        selected = json.loads(Path("artifacts/processed/reviews.json").read_text(encoding="utf-8"))["reviews"]
        self.assertEqual([review["id"] for review in selected], ["csv-5"])


def _context(dataset, constraints: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "run_id": "run-1",
        "app_url": VALID_URL,
        "analysis_goal": "Goal",
        "storefront": "US",
        "app_id": "839285684",
        "review_territory": "US",
        "source_type": dataset.source_type,
        "data_source": dataset.source_type,
        "import_metadata": dataset.metadata,
        "import_path": str(dataset.path),
        "constraints": constraints or {},
    }


def _review(review_id: str, *, rating: int = 4) -> dict[str, object]:
    return {
        "id": review_id,
        "rating": rating,
        "title": "Title",
        "body": "",
        "created_at": "2026-08-17T00:00:00Z",
    }


if __name__ == "__main__":
    unittest.main()
