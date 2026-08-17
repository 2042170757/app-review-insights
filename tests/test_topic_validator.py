import json
import unittest

from app.topic_validator import (
    STATUS_EMPTY_TOPICS,
    STATUS_INVALID_JSON,
    STATUS_SCHEMA_VALIDATION_FAILED,
    STATUS_SUCCESS,
    STATUS_UNKNOWN_REVIEW_ID,
    validate_topic_output,
)


class TopicValidatorTests(unittest.TestCase):
    def test_valid_output(self) -> None:
        result = validate_topic_output(
            json.dumps(
                {
                    "topics": [
                        {
                            "topic_id": "TOPIC-001",
                            "name": "Subscription concern",
                            "description": "Users mention subscription pricing.",
                            "review_ids": ["r1"],
                            "confidence": 0.8,
                            "uncertainty": "Small sample.",
                        }
                    ]
                }
            ),
            {"r1"},
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(result.topics[0].topic_id, "TOPIC-001")

    def test_invalid_json(self) -> None:
        result = validate_topic_output("{not json", {"r1"})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INVALID_JSON)

    def test_schema_validation_failed_missing_field(self) -> None:
        result = validate_topic_output(
            json.dumps({"topics": [{"topic_id": "TOPIC-001"}]}),
            {"r1"},
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_unknown_review_id(self) -> None:
        result = validate_topic_output(
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
            ),
            {"r1"},
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_REVIEW_ID)

    def test_duplicate_topic_id(self) -> None:
        topic = {
            "topic_id": "TOPIC-001",
            "name": "Name",
            "description": "Description",
            "review_ids": ["r1"],
            "confidence": 0.5,
            "uncertainty": "",
        }

        result = validate_topic_output(json.dumps({"topics": [topic, topic]}), {"r1"})

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_confidence_range(self) -> None:
        result = validate_topic_output(
            json.dumps(
                {
                    "topics": [
                        {
                            "topic_id": "TOPIC-001",
                            "name": "Name",
                            "description": "Description",
                            "review_ids": ["r1"],
                            "confidence": 1.2,
                            "uncertainty": "",
                        }
                    ]
                }
            ),
            {"r1"},
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_empty_topics(self) -> None:
        result = validate_topic_output(json.dumps({"topics": []}), {"r1"})

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_EMPTY_TOPICS)
        self.assertEqual(result.warnings, ["empty_topics"])


if __name__ == "__main__":
    unittest.main()

