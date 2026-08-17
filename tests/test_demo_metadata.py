import json
import os
import tempfile
import unittest
from pathlib import Path

from app.demo import DEMO_CACHE_ROOT_ENV, demo_cache_artifact_paths, load_demo_cache, validate_demo_cache


class DemoMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_cache_root = os.environ.get(DEMO_CACHE_ROOT_ENV)

    def tearDown(self) -> None:
        if self.previous_cache_root is None:
            os.environ.pop(DEMO_CACHE_ROOT_ENV, None)
        else:
            os.environ[DEMO_CACHE_ROOT_ENV] = self.previous_cache_root

    def test_builtin_demo_metadata_is_explicit_and_valid(self) -> None:
        result = validate_demo_cache()

        self.assertEqual(result["status"], "PASS")
        metadata = result["metadata"]
        self.assertTrue(metadata["is_demo"])
        self.assertEqual(metadata["mode"], "cached_demo")
        self.assertEqual(metadata["source_provider"], "apify")
        self.assertEqual(metadata["territory"], "US")
        self.assertEqual(metadata["app_id"], "839285684")
        self.assertEqual(metadata["review_count"], 50)
        self.assertEqual(metadata["model_provider"], "deepseek")
        self.assertEqual(metadata["model"], "deepseek-v4-flash")

    def test_demo_artifacts_do_not_contain_secret_markers(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in demo_cache_artifact_paths())

        self.assertNotIn("DEEPSEEK_API_KEY=", combined)
        self.assertNotIn("APIFY_API_TOKEN=", combined)
        self.assertNotIn("OPENAI_API_KEY=", combined)
        self.assertNotIn("Bearer ", combined)

    def test_missing_cache_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            os.environ[DEMO_CACHE_ROOT_ENV] = str(Path(tempdir) / "missing")

            result = validate_demo_cache()

        self.assertEqual(result["status"], "FAIL")
        self.assertIn("Missing demo cache artifact", result["errors"][0])

    def test_invalid_cache_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "demo_metadata.json").write_text("{not json", encoding="utf-8")
            os.environ[DEMO_CACHE_ROOT_ENV] = str(root)

            result = validate_demo_cache()

        self.assertEqual(result["status"], "FAIL")
        self.assertIn("Invalid demo cache JSON", result["errors"][0])

    def test_metadata_review_count_matches_cached_reviews(self) -> None:
        cache = load_demo_cache()
        reviews = json.loads((cache.root / "processing" / "reviews.json").read_text(encoding="utf-8"))["reviews"]

        self.assertEqual(len(reviews), cache.metadata["review_count"])


if __name__ == "__main__":
    unittest.main()
