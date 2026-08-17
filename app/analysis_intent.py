"""Explicit analysis focus selection for workflow runs."""

from __future__ import annotations


ANALYSIS_FOCUS_PROBLEM = "problem_analysis"
ANALYSIS_FOCUS_POSITIVE_FEEDBACK = "positive_feedback_analysis"
ANALYSIS_FOCUS_MIXED = "mixed_analysis"

DEFAULT_ANALYSIS_FOCUS = ANALYSIS_FOCUS_PROBLEM

VALID_ANALYSIS_FOCUSES = {
    ANALYSIS_FOCUS_PROBLEM,
    ANALYSIS_FOCUS_POSITIVE_FEEDBACK,
    ANALYSIS_FOCUS_MIXED,
}

ANALYSIS_FOCUS_ALIASES = {
    "problem": ANALYSIS_FOCUS_PROBLEM,
    "problems": ANALYSIS_FOCUS_PROBLEM,
    "product_problems": ANALYSIS_FOCUS_PROBLEM,
    "product problems": ANALYSIS_FOCUS_PROBLEM,
    "positive": ANALYSIS_FOCUS_POSITIVE_FEEDBACK,
    "positive_feedback": ANALYSIS_FOCUS_POSITIVE_FEEDBACK,
    "positive feedback": ANALYSIS_FOCUS_POSITIVE_FEEDBACK,
    "mixed": ANALYSIS_FOCUS_MIXED,
    "problems_positive": ANALYSIS_FOCUS_MIXED,
    "problems + positive feedback": ANALYSIS_FOCUS_MIXED,
}


def normalize_analysis_focus(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        return DEFAULT_ANALYSIS_FOCUS
    normalized = value.strip()
    lowered = normalized.lower()
    canonical = ANALYSIS_FOCUS_ALIASES.get(lowered, normalized)
    if canonical not in VALID_ANALYSIS_FOCUSES:
        raise ValueError(f"Invalid analysis_focus: {value}")
    return canonical


def validate_analysis_focus(value: str | None) -> bool:
    try:
        normalize_analysis_focus(value)
    except ValueError:
        return False
    return True


def focus_label(value: str | None) -> str:
    focus = normalize_analysis_focus(value)
    if focus == ANALYSIS_FOCUS_POSITIVE_FEEDBACK:
        return "Positive Feedback"
    if focus == ANALYSIS_FOCUS_MIXED:
        return "Problems + Positive Feedback"
    return "Product Problems"
