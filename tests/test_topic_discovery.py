import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.llm.base import LLMRequest, ModelRequestError, ModelTimeoutError
from app.llm.mock_provider import MockLLMProvider
from app.topic_discovery import build_topic_request, discover_topics, extract_json_text, load_processed_reviews


class TopicDiscoveryTests(unittest.TestCase):
    def test_legal_topic_json(self) -> None:
        provider = MockLLMProvider(
            json.dumps(
                {
                    "topics": [
                        {
                            "topic_id": "TOPIC-001",
                            "name": "Pricing concerns",
                            "description": "Users mention pricing concerns.",
                            "review_ids": ["r1", "r2"],
                            "confidence": 0.84,
                            "uncertainty": "Limited to provided reviews.",
                        }
                    ]
                }
            )
        )
        with TemporaryDirectory() as temp_dir:
            result = discover_topics(
                _reviews(),
                analysis_goal="Analyze low ratings",
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result.passed)
        self.assertEqual(result.status, "Success")
        self.assertEqual(len(result.topics), 1)

    def test_invalid_json(self) -> None:
        provider = MockLLMProvider("{bad json")
        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Invalid JSON")

    def test_schema_validation_failed(self) -> None:
        provider = MockLLMProvider(json.dumps({"topics": [{"topic_id": "TOPIC-001"}]}))
        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Schema Validation Failed")

    def test_unknown_review_id(self) -> None:
        provider = MockLLMProvider(
            json.dumps(
                {
                    "topics": [
                        {
                            "topic_id": "TOPIC-001",
                            "name": "Name",
                            "description": "Description",
                            "review_ids": ["missing"],
                            "confidence": 0.5,
                            "uncertainty": "",
                        }
                    ]
                }
            )
        )
        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Unknown Review ID")
        self.assertEqual(result.topics, [])

    def test_duplicate_topic_id(self) -> None:
        topic = {
            "topic_id": "TOPIC-001",
            "name": "Name",
            "description": "Description",
            "review_ids": ["r1"],
            "confidence": 0.5,
            "uncertainty": "",
        }
        provider = MockLLMProvider(json.dumps({"topics": [topic, topic]}))
        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Schema Validation Failed")

    def test_confidence_range(self) -> None:
        provider = MockLLMProvider(
            json.dumps(
                {
                    "topics": [
                        {
                            "topic_id": "TOPIC-001",
                            "name": "Name",
                            "description": "Description",
                            "review_ids": ["r1"],
                            "confidence": -0.1,
                            "uncertainty": "",
                        }
                    ]
                }
            )
        )
        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Schema Validation Failed")

    def test_empty_topics(self) -> None:
        provider = MockLLMProvider(json.dumps({"topics": []}))
        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertTrue(result.passed)
        self.assertEqual(result.status, "Empty Topics")
        self.assertEqual(result.topics, [])

    def test_analysis_goal_is_passed(self) -> None:
        provider = MockLLMProvider(json.dumps({"topics": []}))
        with TemporaryDirectory() as temp_dir:
            discover_topics(_reviews(), analysis_goal="Exact goal text", provider=provider, output_dir=Path(temp_dir))

        self.assertEqual(provider.requests[0].analysis_goal, "Exact goal text")
        self.assertIn("Exact goal text", provider.requests[0].user_prompt)

    def test_mock_provider_records_request(self) -> None:
        provider = MockLLMProvider(json.dumps({"topics": []}))
        request = LLMRequest("system", "user", "goal")

        response = provider.generate(request)

        self.assertEqual(response.raw_text, json.dumps({"topics": []}))
        self.assertEqual(provider.requests, [request])

    def test_raw_and_validation_results_are_saved(self) -> None:
        provider = MockLLMProvider(json.dumps({"topics": []}))
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = discover_topics(_reviews(), analysis_goal="Goal", provider=provider, output_dir=output_dir)

            raw = json.loads((output_dir / "topic_discovery_raw.json").read_text(encoding="utf-8"))
            topics = json.loads((output_dir / "topics.json").read_text(encoding="utf-8"))
            validation = json.loads((output_dir / "topic_validation.json").read_text(encoding="utf-8"))

        self.assertEqual(raw["raw_output"], json.dumps({"topics": []}))
        self.assertEqual(topics["topics"], [])
        self.assertEqual(validation["status"], "Empty Topics")
        self.assertIn("raw", result.saved_paths)

    def test_model_request_failed(self) -> None:
        class FailingProvider:
            provider_name = "failing"

            def generate(self, request):
                raise ModelRequestError("request failed")

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(), analysis_goal="Goal", provider=FailingProvider(), output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Model Request Error")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_timeout(self) -> None:
        class TimeoutProvider:
            provider_name = "timeout"

            def generate(self, request):
                raise ModelTimeoutError("timeout")

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(), analysis_goal="Goal", provider=TimeoutProvider(), output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Timeout")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_load_processed_reviews(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reviews.json"
            path.write_text(json.dumps({"reviews": _reviews()}), encoding="utf-8")

            reviews = load_processed_reviews(path)

        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0]["id"], "r1")

    def test_prompt_does_not_generate_downstream_artifacts(self) -> None:
        request = build_topic_request(_reviews(), analysis_goal="Goal")

        self.assertIn("Do not generate Requirements", request.system_prompt)
        self.assertIn("Do not generate product solutions", request.system_prompt)
        self.assertIn("only Topic discovery", request.system_prompt)
        self.assertIn("Do not use a predefined Topic list", request.system_prompt)

    def test_markdown_fenced_json_is_extracted(self) -> None:
        raw_text = '```json\n{"topics": []}\n```'

        self.assertEqual(extract_json_text(raw_text), '{"topics": []}')


def _reviews() -> list[dict]:
    return [
        {
            "id": "r1",
            "rating": 1,
            "clean_title": "Too expensive",
            "clean_body": "The subscription is too expensive.",
            "created_at": "2026-08-15T00:00:00Z",
            "language": "en",
        },
        {
            "id": "r2",
            "rating": 2,
            "clean_title": "Price",
            "clean_body": "I cannot use workouts without paying.",
            "created_at": "2026-08-16T00:00:00Z",
            "language": "en",
        },
    ]


if __name__ == "__main__":
    unittest.main()
