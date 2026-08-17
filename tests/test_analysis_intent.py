import unittest

from app.analysis_intent import (
    ANALYSIS_FOCUS_MIXED,
    ANALYSIS_FOCUS_POSITIVE_FEEDBACK,
    ANALYSIS_FOCUS_PROBLEM,
    DEFAULT_ANALYSIS_FOCUS,
    focus_label,
    normalize_analysis_focus,
    validate_analysis_focus,
)


class AnalysisIntentTests(unittest.TestCase):
    def test_default_focus_is_problem_analysis(self) -> None:
        self.assertEqual(normalize_analysis_focus(None), DEFAULT_ANALYSIS_FOCUS)
        self.assertEqual(normalize_analysis_focus("  "), ANALYSIS_FOCUS_PROBLEM)

    def test_canonical_focus_values_are_valid(self) -> None:
        self.assertEqual(normalize_analysis_focus(ANALYSIS_FOCUS_PROBLEM), ANALYSIS_FOCUS_PROBLEM)
        self.assertEqual(normalize_analysis_focus(ANALYSIS_FOCUS_POSITIVE_FEEDBACK), ANALYSIS_FOCUS_POSITIVE_FEEDBACK)
        self.assertEqual(normalize_analysis_focus(ANALYSIS_FOCUS_MIXED), ANALYSIS_FOCUS_MIXED)

    def test_aliases_are_explicit_not_goal_keyword_inference(self) -> None:
        self.assertEqual(normalize_analysis_focus("positive_feedback"), ANALYSIS_FOCUS_POSITIVE_FEEDBACK)
        self.assertEqual(normalize_analysis_focus("mixed"), ANALYSIS_FOCUS_MIXED)
        with self.assertRaises(ValueError):
            normalize_analysis_focus("分析高评分用户为什么长期使用")

    def test_validate_and_label(self) -> None:
        self.assertTrue(validate_analysis_focus("positive"))
        self.assertFalse(validate_analysis_focus("unknown"))
        self.assertEqual(focus_label(ANALYSIS_FOCUS_POSITIVE_FEEDBACK), "Positive Feedback")


if __name__ == "__main__":
    unittest.main()
