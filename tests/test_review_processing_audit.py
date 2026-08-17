import unittest

from app.review_processing_audit import (
    audit_exact_duplicate_detection,
    audit_json_csv_inputs,
    audit_lexical_near_duplicate_detection,
    audit_mixed_language_detection,
    audit_raw_evidence_preservation,
    audit_semantic_similarity_boundary,
    audit_statistics_consistency,
    audit_unknown_app_generalization,
)


class ReviewProcessingAuditTests(unittest.TestCase):
    def test_raw_evidence_preservation_passes(self) -> None:
        reviews = [_processed_review(str(index), f"Title {index}", f"Body {index}") for index in range(5)]

        result = audit_raw_evidence_preservation(reviews)

        self.assertTrue(result.passed)
        self.assertEqual(result.data["sampled"], 5)

    def test_raw_evidence_preservation_fails_on_mismatch(self) -> None:
        reviews = [_processed_review(str(index), f"Title {index}", f"Body {index}") for index in range(5)]
        reviews[0]["raw_body"] = "changed evidence"

        result = audit_raw_evidence_preservation(reviews)

        self.assertFalse(result.passed)
        self.assertTrue(any("raw_body does not match" in detail for detail in result.details))

    def test_unknown_app_generalization_passes(self) -> None:
        result = audit_unknown_app_generalization()

        self.assertTrue(result.passed)
        self.assertEqual(result.data["statistics"]["total"], 3)
        self.assertEqual(result.data["statistics"]["valid"], 3)

    def test_mixed_language_detection_passes(self) -> None:
        result = audit_mixed_language_detection()

        self.assertTrue(result.passed)
        self.assertGreaterEqual(len(result.data["language_distribution"]), 2)
        self.assertNotEqual(result.data["languages"], ["en", "en", "en", "en"])

    def test_exact_duplicate_detection_passes(self) -> None:
        result = audit_exact_duplicate_detection()

        self.assertTrue(result.passed)
        self.assertEqual(result.data["exact_duplicate_count"], 2)
        self.assertEqual(result.data["retained_count"], 1)

    def test_lexical_near_duplicate_detection_passes(self) -> None:
        result = audit_lexical_near_duplicate_detection()

        self.assertTrue(result.passed)
        self.assertEqual(result.data["threshold"], 0.82)
        self.assertGreaterEqual(result.data["lexical_similarity"], result.data["threshold"])
        self.assertEqual(result.data["candidate_flags"]["lexical-a"], True)
        self.assertEqual(result.data["candidate_flags"]["lexical-b"], True)
        self.assertEqual(result.data["candidate_flags"]["lexical-c"], False)

    def test_semantic_similarity_boundary_passes_without_requiring_detection(self) -> None:
        result = audit_semantic_similarity_boundary()

        self.assertTrue(result.passed)
        self.assertLess(result.data["similarity"], result.data["threshold"])
        self.assertFalse(result.data["candidate_flags"]["semantic-a"])
        self.assertFalse(result.data["candidate_flags"]["semantic-b"])
        self.assertIn("delegated to Phase 2 semantic analysis", result.data["phase_boundary"])

    def test_statistics_consistency_passes(self) -> None:
        result = audit_statistics_consistency()

        self.assertTrue(result.passed)
        self.assertEqual(result.data["statistics"]["total"], 5)
        self.assertEqual(result.data["statistics"]["average_rating"], 2.4)
        self.assertEqual(result.data["statistics"]["rating_distribution"], {1: 2, 2: 1, 3: 1, 5: 1})

    def test_json_csv_inputs_pass(self) -> None:
        result = audit_json_csv_inputs()

        self.assertTrue(result.json_input.passed)
        self.assertTrue(result.csv_input.passed)
        self.assertEqual(result.json_input.data["statistics"]["total"], 3)
        self.assertEqual(result.csv_input.data["statistics"]["total"], 3)


def _processed_review(review_id: str, title: str, body: str) -> dict:
    return {
        "id": review_id,
        "raw_title": title,
        "raw_body": body,
        "raw_review": {
            "id": review_id,
            "title": title,
            "body": body,
        },
    }


if __name__ == "__main__":
    unittest.main()
