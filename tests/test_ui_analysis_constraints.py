from pathlib import Path
import unittest


class UIAnalysisConstraintTests(unittest.TestCase):
    def test_ui_exposes_rating_constraint_options_and_submits_constraints(self) -> None:
        source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")

        self.assertIn("Analysis Constraints", source)
        self.assertIn("1-2 Stars", source)
        self.assertIn("1-3 Stars", source)
        self.assertIn("4-5 Stars", source)
        self.assertIn("constraintsForRating(ratingConstraint)", source)
        self.assertIn("...(Object.keys(constraints).length ? { constraints } : {})", source)


if __name__ == "__main__":
    unittest.main()
