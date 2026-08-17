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


def _context(dataset) -> dict[str, object]:
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
    }


def _review(review_id: str) -> dict[str, object]:
    return {
        "id": review_id,
        "rating": 4,
        "title": "Title",
        "body": "",
        "created_at": "2026-08-17T00:00:00Z",
    }


if __name__ == "__main__":
    unittest.main()
