import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.issue_consolidation import (
    build_issue_request,
    build_validation_context,
    consolidate_issues,
    load_processed_reviews,
    load_topics,
)
from app.llm.base import ModelTimeoutError
from app.llm.mock_provider import MockLLMProvider


class IssueConsolidationTests(unittest.TestCase):
    def test_valid_mock_issue(self) -> None:
        provider = MockLLMProvider(json.dumps(_issue_payload()))
        with TemporaryDirectory() as temp_dir:
            result = consolidate_issues(
                _reviews(),
                _topics(),
                provider=provider,
                analysis_goal="Consolidate issues",
                output_dir=Path(temp_dir),
                is_mock=True,
            )

        self.assertTrue(result.passed)
        self.assertEqual(result.status, "Success")
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(provider.requests[0].analysis_goal, "Consolidate issues")

    def test_one_topic_to_one_issue(self) -> None:
        result = _run(_issue_payload(topic_ids=["TOPIC-001"], review_ids=["r1"]))

        self.assertTrue(result.passed)
        self.assertEqual(result.issues[0].topic_ids, ["TOPIC-001"])

    def test_two_topics_to_one_issue(self) -> None:
        result = _run(
            _issue_payload(
                topic_ids=["TOPIC-001", "TOPIC-003"],
                review_ids=["r1", "r4"],
            ),
            topics=_topics_with_related_subscription(),
            reviews=_reviews_with_related_subscription(),
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.issues[0].topic_ids, ["TOPIC-001", "TOPIC-003"])

    def test_two_unrelated_topics_to_two_issues(self) -> None:
        first = _issue(issue_id="ISSUE-001", topic_ids=["TOPIC-001"], review_ids=["r1"])
        second = _issue(
            issue_id="ISSUE-002",
            name="Crash on open",
            topic_ids=["TOPIC-002"],
            review_ids=["r3"],
        )

        result = _run({"issues": [first, second], "unmerged_topic_ids": []})

        self.assertTrue(result.passed)
        self.assertEqual(len(result.issues), 2)

    def test_topic_unmerged(self) -> None:
        result = _run({"issues": [_issue(topic_ids=["TOPIC-001"], review_ids=["r1"])], "unmerged_topic_ids": ["TOPIC-002"]})

        self.assertTrue(result.passed)
        self.assertEqual(result.unmerged_topic_ids, ["TOPIC-002"])

    def test_unknown_topic_id(self) -> None:
        payload = _issue_payload(topic_ids=["TOPIC-MISSING"])

        result = _run(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Unknown Topic ID")

    def test_unknown_review_id(self) -> None:
        payload = _issue_payload(review_ids=["missing-review"])

        result = _run(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Unknown Review ID")

    def test_duplicate_issue_id(self) -> None:
        issue = _issue()

        result = _run({"issues": [issue, issue], "unmerged_topic_ids": []})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Schema Validation Failed")

    def test_confidence_out_of_range(self) -> None:
        result = _run(_issue_payload(confidence=1.5))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Schema Validation Failed")

    def test_missing_merge_rationale(self) -> None:
        issue = _issue()
        del issue["merge_rationale"]

        result = _run({"issues": [issue], "unmerged_topic_ids": []})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Schema Validation Failed")

    def test_empty_issues(self) -> None:
        result = _run({"issues": [], "unmerged_topic_ids": ["TOPIC-001"]})

        self.assertTrue(result.passed)
        self.assertEqual(result.status, "Empty Issues")
        self.assertEqual(result.issues, [])
        self.assertEqual(result.unmerged_topic_ids, ["TOPIC-001"])

    def test_evidence_mismatch(self) -> None:
        result = _run(_issue_payload(topic_ids=["TOPIC-002"], review_ids=["r1"]))

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Evidence Mismatch")

    def test_invalid_json(self) -> None:
        provider = MockLLMProvider("{not json")
        with TemporaryDirectory() as temp_dir:
            result = consolidate_issues(
                _reviews(),
                _topics(),
                provider=provider,
                output_dir=Path(temp_dir),
                is_mock=True,
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Invalid JSON")

    def test_outputs_are_saved(self) -> None:
        provider = MockLLMProvider(json.dumps(_issue_payload()))
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = consolidate_issues(
                _reviews(),
                _topics(),
                provider=provider,
                output_dir=output_dir,
                is_mock=True,
            )
            raw = json.loads((output_dir / "issue_consolidation_raw.json").read_text(encoding="utf-8"))
            issues = json.loads((output_dir / "issues.json").read_text(encoding="utf-8"))
            validation = json.loads((output_dir / "issue_validation.json").read_text(encoding="utf-8"))

        self.assertTrue(raw["is_mock"])
        self.assertEqual(raw["phase"], "2.2b")
        self.assertEqual(len(issues["issues"]), 1)
        self.assertEqual(issues["unmerged_topic_ids"], [])
        self.assertEqual(validation["status"], "Success")
        self.assertIn("raw", result.saved_paths)

    def test_timeout_skips_validation(self) -> None:
        class TimeoutProvider:
            provider_name = "timeout"
            model = "timeout-model"

            def generate(self, request):
                raise ModelTimeoutError("timeout")

        with TemporaryDirectory() as temp_dir:
            result = consolidate_issues(
                _reviews(),
                _topics(),
                provider=TimeoutProvider(),
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "Timeout")
        self.assertEqual(result.validation.status, "SKIPPED")

    def test_build_validation_context(self) -> None:
        topic_ids, review_ids, topic_review_ids = build_validation_context(_reviews(), _topics())

        self.assertEqual(topic_ids, {"TOPIC-001", "TOPIC-002"})
        self.assertEqual(review_ids, {"r1", "r2", "r3"})
        self.assertEqual(topic_review_ids["TOPIC-001"], {"r1", "r2"})

    def test_build_issue_request_contains_topics_and_reviews(self) -> None:
        request = build_issue_request(_reviews(), _topics())

        self.assertIn("TOPIC-001", request.user_prompt)
        self.assertIn("r1", request.user_prompt)
        self.assertIn("issue_id", request.user_prompt)
        self.assertIn("evidence_reviews", request.user_prompt)
        self.assertIn("unmerged_topic_ids", request.user_prompt)
        self.assertIn("Issue Consolidation", request.system_prompt)

    def test_loaders(self) -> None:
        with TemporaryDirectory() as temp_dir:
            reviews_path = Path(temp_dir) / "reviews.json"
            topics_path = Path(temp_dir) / "topics.json"
            reviews_path.write_text(json.dumps({"reviews": _reviews()}), encoding="utf-8")
            topics_path.write_text(json.dumps({"topics": _topics()}), encoding="utf-8")

            reviews = load_processed_reviews(reviews_path)
            topics = load_topics(topics_path)

        self.assertEqual(len(reviews), 3)
        self.assertEqual(len(topics), 2)


def _run(payload: dict, *, reviews=None, topics=None):
    provider = MockLLMProvider(json.dumps(payload))
    with TemporaryDirectory() as temp_dir:
        return consolidate_issues(
            reviews or _reviews(),
            topics or _topics(),
            provider=provider,
            output_dir=Path(temp_dir),
            is_mock=True,
        )


def _issue_payload(**overrides) -> dict:
    return {"issues": [_issue(**overrides)], "unmerged_topic_ids": []}


def _issue(**overrides) -> dict:
    issue = {
        "issue_id": "ISSUE-001",
        "name": "Subscription transparency",
        "description": "Users describe subscription terms as unclear.",
        "topic_ids": ["TOPIC-001"],
        "review_ids": ["r1", "r2"],
        "merge_rationale": "Referenced topics and reviews describe the same issue.",
        "confidence": 0.86,
        "uncertainty": "Mock output for validator coverage.",
    }
    issue.update(overrides)
    return issue


def _reviews() -> list[dict]:
    return [
        {"id": "r1", "rating": 1, "clean_title": "Subscription", "clean_body": "Paywall issue."},
        {"id": "r2", "rating": 2, "clean_title": "Price", "clean_body": "Price issue."},
        {"id": "r3", "rating": 1, "clean_title": "Crash", "clean_body": "Crash issue."},
    ]


def _reviews_with_related_subscription() -> list[dict]:
    return _reviews() + [
        {"id": "r4", "rating": 1, "clean_title": "Trial", "clean_body": "Trial changed into paid subscription."},
    ]


def _topics() -> list[dict]:
    return [
        {
            "topic_id": "TOPIC-001",
            "name": "Subscription",
            "description": "Subscription topic.",
            "review_ids": ["r1", "r2"],
            "confidence": 0.9,
            "uncertainty": "",
        },
        {
            "topic_id": "TOPIC-002",
            "name": "Crash",
            "description": "Crash topic.",
            "review_ids": ["r3"],
            "confidence": 0.8,
            "uncertainty": "",
        },
    ]


def _topics_with_related_subscription() -> list[dict]:
    return _topics() + [
        {
            "topic_id": "TOPIC-003",
            "name": "Trial conversion",
            "description": "Trial and subscription conversion topic.",
            "review_ids": ["r4"],
            "confidence": 0.8,
            "uncertainty": "",
        },
    ]


if __name__ == "__main__":
    unittest.main()
