import json
import tempfile
import unittest
from pathlib import Path

from app.analysis_scope import apply_analysis_scope, validate_constraints, write_scope_outputs


class AnalysisScopeTests(unittest.TestCase):
    def test_no_constraint_selects_all_reviews(self) -> None:
        result = apply_analysis_scope([_review("r1", 1), _review("r2", 5)], {})

        self.assertTrue(result.validation.passed)
        self.assertEqual(result.selected_count, 2)
        self.assertEqual(result.excluded_count, 0)
        self.assertEqual(result.constraints, {})

    def test_rating_1_to_2_selects_low_ratings(self) -> None:
        result = apply_analysis_scope([_review("r1", 1), _review("r2", 2), _review("r3", 3)], {"rating": {"min": 1, "max": 2}})

        self.assertEqual([review["id"] for review in result.selected_reviews], ["r1", "r2"])
        self.assertEqual(result.selected_count, 2)
        self.assertEqual(result.excluded_count, 1)

    def test_rating_1_to_3_selects_expected_reviews(self) -> None:
        result = apply_analysis_scope([_review("r1", 1), _review("r2", 3), _review("r3", 4)], {"rating": {"min": 1, "max": 3}})

        self.assertEqual([review["id"] for review in result.selected_reviews], ["r1", "r2"])

    def test_rating_4_to_5_selects_expected_reviews(self) -> None:
        result = apply_analysis_scope([_review("r1", 3), _review("r2", 4), _review("r3", 5)], {"rating": {"min": 4, "max": 5}})

        self.assertEqual([review["id"] for review in result.selected_reviews], ["r2", "r3"])

    def test_min_boundary_is_valid(self) -> None:
        validation = validate_constraints({"rating": {"min": 1, "max": 1}})

        self.assertTrue(validation.passed)
        self.assertEqual(validation.constraints["rating"], {"min": 1, "max": 1})

    def test_max_boundary_is_valid(self) -> None:
        validation = validate_constraints({"rating": {"min": 5, "max": 5}})

        self.assertTrue(validation.passed)
        self.assertEqual(validation.constraints["rating"], {"min": 5, "max": 5})

    def test_min_greater_than_max_fails(self) -> None:
        validation = validate_constraints({"rating": {"min": 3, "max": 2}})

        self.assertFalse(validation.passed)
        self.assertIn("constraints.rating.min must be <= max", validation.errors)

    def test_min_zero_fails(self) -> None:
        validation = validate_constraints({"rating": {"min": 0, "max": 2}})

        self.assertFalse(validation.passed)
        self.assertIn("constraints.rating.min must be >= 1", validation.errors)

    def test_max_six_fails(self) -> None:
        validation = validate_constraints({"rating": {"min": 1, "max": 6}})

        self.assertFalse(validation.passed)
        self.assertIn("constraints.rating.max must be <= 5", validation.errors)

    def test_rating_must_be_integer(self) -> None:
        validation = validate_constraints({"rating": {"min": 1.5, "max": 2}})

        self.assertFalse(validation.passed)
        self.assertIn("constraints.rating.min must be an integer", validation.errors)

    def test_selected_review_validation_catches_out_of_scope_item(self) -> None:
        result = apply_analysis_scope([_review("r1", "not-a-rating")], {"rating": {"min": 1, "max": 2}})

        self.assertTrue(result.validation.passed)
        self.assertEqual(result.selected_count, 0)

    def test_write_scope_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = apply_analysis_scope([_review("r1", 1), _review("r2", 5)], {"rating": {"min": 1, "max": 2}})
            paths = write_scope_outputs(result, output_dir=Path(tempdir))

            report = json.loads(paths["scope_report"].read_text(encoding="utf-8"))
            validation = json.loads(paths["scope_validation"].read_text(encoding="utf-8"))
            selected = json.loads(paths["selected_reviews"].read_text(encoding="utf-8"))

        self.assertEqual(report["input_count"], 2)
        self.assertEqual(report["selected_count"], 1)
        self.assertEqual(validation["status"], "PASS")
        self.assertEqual(selected["reviews"][0]["id"], "r1")


def _review(review_id: str, rating) -> dict[str, object]:
    return {"id": review_id, "rating": rating}


if __name__ == "__main__":
    unittest.main()
