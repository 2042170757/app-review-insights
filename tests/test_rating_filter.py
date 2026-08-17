import json
import os
import tempfile
import unittest
from pathlib import Path

from app.topic_discovery import load_processed_reviews
from app.workflow.pipeline import BackendPipelineRunner, WorkflowStageExecutionError


class RatingFilterWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_cwd = Path.cwd()
        os.chdir(self.tempdir.name)

    def tearDown(self) -> None:
        os.chdir(self.previous_cwd)
        self.tempdir.cleanup()

    def test_processing_preserves_full_dataset_and_writes_selected_reviews(self) -> None:
        _write_normalized_reviews(Path("artifacts/normalized/apify/normalized_reviews.json"))
        runner = BackendPipelineRunner()

        result = runner.run_stage(stage="processing", context=_context({"rating": {"min": 1, "max": 2}}))

        selected = json.loads(Path("artifacts/processed/reviews.json").read_text(encoding="utf-8"))["reviews"]
        full = json.loads(Path("artifacts/processed/reviews_all.json").read_text(encoding="utf-8"))["reviews"]
        scope = json.loads(Path("artifacts/analysis_scope/scope_report.json").read_text(encoding="utf-8"))

        self.assertEqual([review["id"] for review in selected], ["review-1", "review-2"])
        self.assertEqual(len(full), 5)
        self.assertEqual(scope["input_count"], 5)
        self.assertEqual(scope["selected_count"], 2)
        self.assertEqual(scope["excluded_count"], 3)
        self.assertEqual(result.summary["selected_count"], 2)
        self.assertTrue(all(1 <= review["rating"] <= 2 for review in selected))

    def test_topic_discovery_default_input_uses_selected_reviews(self) -> None:
        _write_normalized_reviews(Path("artifacts/normalized/apify/normalized_reviews.json"))
        runner = BackendPipelineRunner()

        runner.run_stage(stage="processing", context=_context({"rating": {"min": 4, "max": 5}}))
        reviews = load_processed_reviews()

        self.assertEqual([review["id"] for review in reviews], ["review-4", "review-5"])
        self.assertTrue(all(4 <= review["rating"] <= 5 for review in reviews))

    def test_invalid_scope_fails_before_downstream_input_is_created(self) -> None:
        _write_normalized_reviews(Path("artifacts/normalized/apify/normalized_reviews.json"))
        runner = BackendPipelineRunner()

        with self.assertRaises(WorkflowStageExecutionError) as raised:
            runner.run_stage(stage="scope", context=_context({"rating": {"min": 0, "max": 2}}))

        self.assertEqual(raised.exception.stage, "scope")
        self.assertIn("Scope Validation failed", raised.exception.message)
        self.assertTrue(Path("artifacts/analysis_scope/scope_validation.json").exists())


def _write_normalized_reviews(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    reviews = [
        _review("review-1", 1),
        _review("review-2", 2),
        _review("review-3", 3),
        _review("review-4", 4),
        _review("review-5", 5),
    ]
    path.write_text(json.dumps({"reviews": reviews}), encoding="utf-8")


def _review(review_id: str, rating: int) -> dict[str, object]:
    return {
        "id": review_id,
        "source": "apify",
        "app_id": "839285684",
        "territory": "US",
        "rating": rating,
        "title": f"Title {review_id}",
        "body": f"Body {review_id}",
        "created_at": "2026-08-17T00:00:00Z",
    }


def _context(constraints: dict[str, object]) -> dict[str, object]:
    return {
        "run_id": "run-1",
        "app_url": "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684",
        "analysis_goal": "Goal",
        "storefront": "US",
        "app_id": "839285684",
        "review_territory": "US",
        "source_type": "app_store",
        "data_source": "app_store",
        "import_metadata": {},
        "import_path": "",
        "constraints": constraints,
    }


if __name__ == "__main__":
    unittest.main()
