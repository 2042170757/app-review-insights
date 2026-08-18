import json
import unittest

from app.prd_generator import build_prd_request
from app.prd_validator import STATUS_MISSING_OPEN_QUESTION, STATUS_SUCCESS, validate_prd_output


class PRDRequirementIDGeneralizationTests(unittest.TestCase):
    def test_req_007_large_file_crash_uses_current_requirement_context(self) -> None:
        requirement = _requirement(
            title="App crashes when opening large files",
            description="Users need large files to open without crashes.",
            acceptance_criteria=["Large files open without crashing for the supported file size range."],
        )
        version = _version(goal="Prevent crashes when opening large files.")
        prd = _prd(
            goal=version["goal"],
            title="Large file stability",
            overview="Prevent crashes when opening large files.",
            problem_statement="Users report crashes when opening large files.",
            open_questions=["What large file size threshold should define crash-free opening success?"],
            success_metrics=["Percentage of large file openings that do not crash."],
        )

        result = _validate(requirement=requirement, version=version, prd=prd)

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_req_007_support_accessibility_uses_current_requirement_context(self) -> None:
        requirement = _requirement(
            title="Improve support channel accessibility",
            description="Users need a clear support channel when account recovery is unclear.",
            acceptance_criteria=["A clear support contact path is visible from account recovery guidance."],
        )
        version = _version(goal="Improve support accessibility.")
        prd = _prd(
            goal=version["goal"],
            title="Support accessibility",
            overview="Improve support accessibility for account recovery.",
            problem_statement="Users need a clearer support contact path.",
            open_questions=["Which support channel should be available for account recovery questions?"],
            success_metrics=["User-reported support contact success rate."],
        )

        result = _validate(requirement=requirement, version=version, prd=prd)

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_req_007_large_file_missing_context_question_fails_without_refresh_requirement(self) -> None:
        requirement = _requirement(
            title="App crashes when opening large files",
            description="Users need large files to open without crashes.",
            acceptance_criteria=["Large files open without crashing for the supported file size range."],
        )
        version = _version(goal="Prevent crashes when opening large files.")
        prd = _prd(
            goal=version["goal"],
            title="Large file stability",
            overview="Prevent crashes when opening large files.",
            problem_statement="Users report crashes when opening large files.",
            open_questions=["Confirm launch sequence."],
            success_metrics=["Percentage of large file openings that do not crash."],
        )

        result = _validate(requirement=requirement, version=version, prd=prd)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_MISSING_OPEN_QUESTION)
        self.assertIn("large file stability threshold", result.errors[0])
        self.assertNotIn("content refresh", result.errors[0])

    def test_prd_request_derives_required_questions_from_requirement_text_not_id(self) -> None:
        requirement = _requirement(
            title="App crashes when opening large files",
            description="Users need large files to open without crashes.",
            acceptance_criteria=["Large files open without crashing for the supported file size range."],
        )
        request = build_prd_request(
            requirements=[requirement],
            roadmap={"versions": [_version(goal="Prevent crashes when opening large files.")]},
            findings=[_finding()],
            evidence_report={"evidence_reports": []},
            analysis_goal="goal",
        )
        payload = json.loads(request.user_prompt)
        required_questions = payload["validated_versions"][0]["required_open_questions"]

        self.assertEqual(required_questions[0]["requirement_id"], "REQ-007")
        self.assertIn("large file", required_questions[0]["decision"])
        self.assertNotIn("cadence", json.dumps(required_questions))
        self.assertIn("Requirement IDs have no built-in product meaning", payload["open_question_guidance"]["context_rule"])


def _validate(*, requirement: dict, version: dict, prd: dict):
    return validate_prd_output(
        json.dumps({"prds": [prd]}),
        requirements_by_id={"REQ-007": requirement},
        versions_by_id={"V1": version},
        findings_by_id={"FINDING-001": _finding()},
        issues_by_id={"ISSUE-001": {"issue_id": "ISSUE-001", "topic_ids": ["TOPIC-001"], "review_ids": ["review-001"]}},
        topics_by_id={"TOPIC-001": {"topic_id": "TOPIC-001", "review_ids": ["review-001"]}},
        valid_review_ids={"review-001"},
        requirement_validation_passed=True,
        roadmap_validation_passed=True,
        finding_validation_passed=True,
    )


def _prd(
    *,
    goal: str,
    title: str,
    overview: str,
    problem_statement: str,
    open_questions: list[str],
    success_metrics: list[str],
) -> dict:
    return {
        "prd_id": "PRD-V1",
        "version_id": "V1",
        "title": title,
        "overview": overview,
        "problem_statement": problem_statement,
        "evidence_summary": "Evidence is traceable through REQ-007 and FINDING-001.",
        "goals": [goal],
        "non_goals": ["Do not expand beyond REQ-007."],
        "requirement_ids": ["REQ-007"],
        "risks": ["Evidence scope should be confirmed."],
        "success_metrics": success_metrics,
        "open_questions": open_questions,
    }


def _requirement(*, title: str, description: str, acceptance_criteria: list[str]) -> dict:
    return {
        "requirement_id": "REQ-007",
        "requirement_type": "problem",
        "finding_ids": ["FINDING-001"],
        "title": title,
        "description": description,
        "acceptance_criteria": acceptance_criteria,
        "priority": "P1",
        "priority_rationale": "Fixture.",
        "risks": [],
        "success_metrics": [],
        "uncertainty": "Fixture.",
        "source_review_ids": ["review-001"],
    }


def _version(*, goal: str) -> dict:
    return {
        "version_id": "V1",
        "name": "Contextual PRD",
        "goal": goal,
        "requirement_ids": ["REQ-007"],
        "rationale": "Fixture.",
        "risks": [],
        "success_metrics": [],
    }


def _finding() -> dict:
    return {
        "finding_id": "FINDING-001",
        "finding_type": "product_problem",
        "issue_ids": ["ISSUE-001"],
        "review_ids": ["review-001"],
        "title": "Finding",
        "statement": "Fixture finding.",
        "evidence_summary": "review-001 supports it.",
        "support_count": 1,
        "confidence": 0.8,
        "uncertainty": "Fixture.",
        "conflicting_review_ids": [],
    }


if __name__ == "__main__":
    unittest.main()
