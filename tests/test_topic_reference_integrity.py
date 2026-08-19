import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.llm.base import LLMRequest, LLMResponse
from app.topic_discovery import build_topic_request, discover_topics, find_unknown_topic_review_ids


class TopicReferenceIntegrityTests(unittest.TestCase):
    def test_all_valid_review_ids_do_not_trigger_repair(self) -> None:
        provider = SequenceProvider([_topic(["r1", "r2"])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(["r1", "r2"]), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertTrue(result.passed)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(result.reference_integrity["initial_unknown_review_ids"], [])
        self.assertFalse(result.reference_integrity["repair_attempted"])

    def test_unknown_review_id_triggers_validation_failure_when_repair_does_not_fix_it(self) -> None:
        provider = SequenceProvider([_topic(["missing"]), _topic(["missing"])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(["r1"]), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Unknown Review ID")
        self.assertEqual(result.reference_integrity["initial_unknown_review_ids"], ["missing"])
        self.assertEqual(result.reference_integrity["final_unknown_review_ids"], ["missing"])

    def test_multiple_unknown_review_ids_are_detected(self) -> None:
        unknown = find_unknown_topic_review_ids(
            json.dumps(
                {
                    "topics": [
                        _topic_payload(["missing-a", "r1"]),
                        _topic_payload(["missing-b", "missing-a"]),
                    ]
                }
            ),
            {"r1"},
        )

        self.assertEqual(unknown, ["missing-a", "missing-b"])

    def test_reference_repair_success_continues_to_validator(self) -> None:
        provider = SequenceProvider([_topic(["r1", "missing"]), _topic(["r1"])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(["r1"]), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertTrue(result.passed)
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(result.topics[0].review_ids, ["r1"])
        self.assertTrue(result.reference_integrity["repair_success"])

    def test_reference_repair_failure_keeps_topic_discovery_failed(self) -> None:
        provider = SequenceProvider([_topic(["missing-a"]), _topic(["missing-b"])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(["r1"]), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Unknown Review ID")
        self.assertFalse(result.reference_integrity["repair_success"])
        self.assertEqual(result.reference_integrity["final_unknown_review_ids"], ["missing-b"])

    def test_repair_runs_at_most_once(self) -> None:
        provider = SequenceProvider([_topic(["missing-a"]), _topic(["missing-b"]), _topic(["r1"])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(["r1"]), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(len(provider.requests), 2)

    def test_initial_raw_response_is_preserved(self) -> None:
        initial = _topic(["missing"])
        repair = _topic(["r1"])
        provider = SequenceProvider([initial, repair])

        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            discover_topics(_reviews(["r1"]), analysis_goal="Goal", provider=provider, output_dir=output_dir)
            raw = json.loads((output_dir / "topic_discovery_raw.json").read_text(encoding="utf-8"))

        self.assertEqual(raw["raw_output"], initial)
        self.assertEqual(raw["initial_raw_response"], initial)
        self.assertEqual(raw["initial_extracted_json"], initial)

    def test_repair_raw_response_is_preserved(self) -> None:
        initial = _topic(["missing"])
        repair = _topic(["r1"])
        provider = SequenceProvider([initial, repair])

        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            discover_topics(_reviews(["r1"]), analysis_goal="Goal", provider=provider, output_dir=output_dir)
            raw = json.loads((output_dir / "topic_discovery_raw.json").read_text(encoding="utf-8"))

        self.assertEqual(raw["repair_raw_response"], repair)
        self.assertEqual(raw["repair_extracted_json"], repair)
        self.assertEqual(raw["reference_integrity"]["initial_unknown_review_ids"], ["missing"])
        self.assertEqual(raw["reference_integrity"]["final_unknown_review_ids"], [])

    def test_no_automatic_id_substitution(self) -> None:
        provider = SequenceProvider([_topic(["r01"]), _topic(["r01"])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(["r1"]), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.topics, [])
        self.assertNotIn("r1", result.extracted_json)

    def test_empty_review_ids_after_repair_remains_validator_failure(self) -> None:
        provider = SequenceProvider([_topic(["missing"]), _topic([])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(["r1"]), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Schema Validation Failed")
        self.assertTrue(result.reference_integrity["repair_success"])

    def test_scope_filtered_review_ids_limit_allowed_set(self) -> None:
        provider = SequenceProvider([_topic(["excluded-r2"]), _topic(["selected-r1"])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(
                _reviews(["selected-r1"]),
                analysis_goal="Goal",
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result.passed)
        repair_payload = json.loads(provider.requests[1].user_prompt)
        self.assertEqual(repair_payload["valid_review_ids"], ["selected-r1"])
        self.assertNotIn("excluded-r2", repair_payload["valid_review_ids"])

    def test_json_imported_review_ids_are_preserved(self) -> None:
        provider = SequenceProvider([_topic(["json-001", "missing"]), _topic(["json-001"])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(["json-001", "json-002"]), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertTrue(result.passed)
        self.assertEqual(result.topics[0].review_ids, ["json-001"])

    def test_csv_imported_review_ids_are_preserved(self) -> None:
        provider = SequenceProvider([_topic(["csv-001", "missing"]), _topic(["csv-002"])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(_reviews(["csv-001", "csv-002"]), analysis_goal="Goal", provider=provider, output_dir=Path(temp_dir))

        self.assertTrue(result.passed)
        self.assertEqual(result.topics[0].review_ids, ["csv-002"])

    def test_unknown_app_numeric_review_ids_are_preserved(self) -> None:
        provider = SequenceProvider([_topic(["14356559821", "14308658475"]), _topic(["14356559821"])])

        with TemporaryDirectory() as temp_dir:
            result = discover_topics(
                _reviews(["14356559821", "14280718030"]),
                analysis_goal="Goal",
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result.passed)
        self.assertEqual(result.topics[0].review_ids, ["14356559821"])

    def test_run_isolation_uses_only_current_review_ids(self) -> None:
        first_provider = SequenceProvider([_topic(["run-a-review"])])
        second_provider = SequenceProvider([_topic(["run-a-review"]), _topic(["run-b-review"])])

        with TemporaryDirectory() as first_dir:
            first = discover_topics(
                _reviews(["run-a-review"]),
                analysis_goal="Goal",
                provider=first_provider,
                output_dir=Path(first_dir),
            )
        with TemporaryDirectory() as second_dir:
            second = discover_topics(
                _reviews(["run-b-review"]),
                analysis_goal="Goal",
                provider=second_provider,
                output_dir=Path(second_dir),
            )

        self.assertTrue(first.passed)
        self.assertTrue(second.passed)
        repair_payload = json.loads(second_provider.requests[1].user_prompt)
        self.assertEqual(repair_payload["valid_review_ids"], ["run-b-review"])

    def test_prompt_contains_explicit_valid_review_ids(self) -> None:
        request = build_topic_request(_reviews(["r1", "r2"]), analysis_goal="Goal")
        payload = json.loads(request.user_prompt)

        self.assertIn("VALID REVIEW IDS", request.system_prompt)
        self.assertEqual(payload["valid_review_ids"], ["r1", "r2"])


class SequenceProvider:
    provider_name = "sequence"
    model = "sequence-model"

    def __init__(self, raw_responses: list[str]) -> None:
        self.raw_responses = list(raw_responses)
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self.raw_responses:
            raise AssertionError("No queued response")
        return LLMResponse(
            raw_text=self.raw_responses.pop(0),
            provider=self.provider_name,
            model=self.model,
            metadata={"request_index": len(self.requests)},
        )


def _topic(review_ids: list[str]) -> str:
    return json.dumps({"topics": [_topic_payload(review_ids)]})


def _topic_payload(review_ids: list[str]) -> dict:
    return {
        "topic_id": "TOPIC-001",
        "name": "Evidence topic",
        "description": "Users describe the same review-backed theme.",
        "review_ids": review_ids,
        "confidence": 0.82,
        "uncertainty": "Limited to supplied reviews.",
    }


def _reviews(ids: list[str]) -> list[dict]:
    return [
        {
            "id": review_id,
            "rating": 1,
            "clean_title": f"Title {review_id}",
            "clean_body": f"Body {review_id}",
            "created_at": "2026-08-15T00:00:00Z",
            "language": "en",
        }
        for review_id in ids
    ]


if __name__ == "__main__":
    unittest.main()
