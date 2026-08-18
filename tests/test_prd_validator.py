import json
import unittest

from app.prd_validator import (
    STATUS_DUPLICATE_PRD_ID,
    STATUS_EVIDENCE_SUMMARY_INVALID,
    STATUS_GOAL_INCOHERENCE,
    STATUS_INPUT_VALIDATION_FAILED,
    STATUS_PROHIBITED_IMPLEMENTATION_DETAIL,
    STATUS_REQUIREMENT_VERSION_MISMATCH,
    STATUS_SCHEMA_VALIDATION_FAILED,
    STATUS_SUCCESS,
    STATUS_SUCCESS_METRIC_INVALID,
    STATUS_TRACEABILITY_MISMATCH,
    STATUS_MISSING_OPEN_QUESTION,
    STATUS_UNSUPPORTED_PRODUCT_DIRECTION,
    STATUS_UNKNOWN_FINDING_ID,
    STATUS_UNKNOWN_REQUIREMENT_ID,
    STATUS_UNKNOWN_VERSION_ID,
    validate_prd_output,
)


class PRDValidatorTests(unittest.TestCase):
    def test_valid_prd(self) -> None:
        result = _validate(_payload())

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)
        self.assertEqual(result.prds[0].prd_id, "PRD-V1")

    def test_unknown_version(self) -> None:
        payload = _payload()
        payload["prds"][0]["version_id"] = "V9"
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_VERSION_ID)

    def test_unknown_requirement(self) -> None:
        payload = _payload()
        payload["prds"][0]["requirement_ids"] = ["REQ-999"]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_REQUIREMENT_ID)

    def test_requirement_version_mismatch(self) -> None:
        payload = _payload()
        payload["prds"][0]["requirement_ids"] = ["REQ-001"]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_REQUIREMENT_VERSION_MISMATCH)

    def test_unknown_finding(self) -> None:
        requirements = _requirements_by_id()
        requirements["REQ-001"]["finding_ids"] = ["FINDING-999"]
        result = _validate(_payload(), requirements_by_id=requirements)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNKNOWN_FINDING_ID)

    def test_evidence_traceability_break(self) -> None:
        findings = _findings_by_id()
        findings["FINDING-001"]["review_ids"] = ["missing-review"]
        result = _validate(_payload(), findings_by_id=findings)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_TRACEABILITY_MISMATCH)

    def test_goal_incoherence(self) -> None:
        payload = _payload()
        payload["prds"][0]["goals"] = ["Improve workout personalization"]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_GOAL_INCOHERENCE)

    def test_empty_goals(self) -> None:
        payload = _payload()
        payload["prds"][0]["goals"] = []
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_empty_title(self) -> None:
        payload = _payload()
        payload["prds"][0]["title"] = ""
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_missing_evidence_summary_text(self) -> None:
        payload = _payload()
        payload["prds"][0]["evidence_summary"] = ""
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_evidence_summary_without_ids(self) -> None:
        payload = _payload()
        payload["prds"][0]["evidence_summary"] = "User feedback shows this is important."
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_EVIDENCE_SUMMARY_INVALID)

    def test_missing_problem_statement(self) -> None:
        payload = _payload()
        payload["prds"][0]["problem_statement"] = ""
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SCHEMA_VALIDATION_FAILED)

    def test_success_metric_not_measurable(self) -> None:
        payload = _payload()
        payload["prds"][0]["success_metrics"] = ["Improve user experience"]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_success_metric_with_unsupported_numeric_target(self) -> None:
        payload = _payload()
        payload["prds"][0]["success_metrics"] = ["Decrease subscription complaints by 10%."]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_unsupported_product_direction(self) -> None:
        payload = _payload()
        payload["prds"][0]["overview"] = "Launch a new membership tier and loyalty program."
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_UNSUPPORTED_PRODUCT_DIRECTION)

    def test_imported_dataset_prd_scope_is_not_limited_to_fixed_domains(self) -> None:
        payload = {
            "prds": [
                {
                    "prd_id": "PRD-V1",
                    "version_id": "V3",
                    "title": "PDF export reliability",
                    "overview": "Improve PDF export reliability and prevent freezes for standard projects.",
                    "problem_statement": "Users report slow PDF export and freezing during export.",
                    "evidence_summary": "Evidence is traceable through REQ-004 and FINDING-003.",
                    "goals": ["Improve PDF export reliability."],
                    "non_goals": ["Do not add unrelated export formats."],
                    "requirement_ids": ["REQ-004"],
                    "risks": ["Large projects may still require target definition."],
                    "success_metrics": ["Average PDF export time for a standard project."],
                    "open_questions": ["What target average PDF export time should define success?"],
                }
            ]
        }
        requirements = _requirements_by_id_with_text()
        requirements["REQ-004"] = {
            "requirement_id": "REQ-004",
            "finding_ids": ["FINDING-003"],
            "title": "PDF export is slow and can freeze",
            "description": "The product should provide a responsive and reliable PDF export experience.",
            "acceptance_criteria": ["PDF export completes without freezing the user interface."],
        }
        versions = _versions_by_id()
        versions["V3"] = {
            "version_id": "V3",
            "goal": "Improve PDF export reliability.",
            "requirement_ids": ["REQ-004"],
        }
        findings = _findings_by_id()
        findings["FINDING-003"] = {
            "finding_id": "FINDING-003",
            "issue_ids": ["ISSUE-003"],
            "review_ids": ["review-004"],
        }
        issues = _issues_by_id()
        issues["ISSUE-003"] = {"issue_id": "ISSUE-003", "topic_ids": ["TOPIC-003"], "review_ids": ["review-004"]}
        topics = _topics_by_id()
        topics["TOPIC-003"] = {"topic_id": "TOPIC-003", "review_ids": ["review-004"]}

        result = _validate(
            payload,
            requirements_by_id=requirements,
            versions_by_id=versions,
            findings_by_id=findings,
            issues_by_id=issues,
            topics_by_id=topics,
            valid_review_ids={"review-001", "review-002", "review-003", "review-004"},
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_positive_workout_scope_is_supported(self) -> None:
        payload = {
            "prds": [
                {
                    "prd_id": "PRD-V2",
                    "version_id": "V2",
                    "title": "Preserve workout effectiveness",
                    "overview": "Preserve workout effectiveness, motivation, and fitness routine clarity.",
                    "problem_statement": "Users value workout effectiveness and motivation in the current review sample.",
                    "evidence_summary": "Evidence is traceable through REQ-003 and FINDING-002.",
                    "goals": ["Improve workout content quality."],
                    "non_goals": [],
                    "requirement_ids": ["REQ-003"],
                    "risks": [],
                    "success_metrics": [],
                    "open_questions": ["What measurable success metric should define preservation of workout effectiveness?"],
                }
            ]
        }
        requirements = _requirements_by_id_with_text()
        requirements["REQ-003"]["title"] = "Preserve workout effectiveness"
        requirements["REQ-003"]["description"] = "Preserve health, fitness, motivation, and workout routine value."
        result = _validate(payload, requirements_by_id=requirements)

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_missing_open_question_for_uncertain_product_parameter(self) -> None:
        payload = _payload()
        payload["prds"][0]["open_questions"] = []
        result = _validate(payload, requirements_by_id=_requirements_by_id_with_text())

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_MISSING_OPEN_QUESTION)

    def test_non_goal_contains_technical_detail(self) -> None:
        payload = _payload()
        payload["prds"][0]["non_goals"] = ["Do not build a React component in this phase."]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_PROHIBITED_IMPLEMENTATION_DETAIL)

    def test_functionality_word_is_not_treated_as_function_code(self) -> None:
        payload = _payload()
        payload["prds"][0]["non_goals"] = ["Do not change the existing subscription functionality."]

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_function_code_word_still_fails(self) -> None:
        payload = _payload()
        payload["prds"][0]["risks"] = ["The function call may need a new API endpoint."]

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_PROHIBITED_IMPLEMENTATION_DETAIL)

    def test_verification_code_product_context_is_allowed(self) -> None:
        payload = _payload()
        payload["prds"][0]["problem_statement"] = (
            "Users report login failures when email verification code delivery is delayed."
        )
        payload["prds"][0]["evidence_summary"] = (
            "Evidence from FINDING-001 and REQ-001 describes account recovery and verification code delays."
        )
        payload["prds"][0]["goals"].append("Ensure verification codes are delivered promptly for account recovery.")

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_open_question_allowed(self) -> None:
        payload = _payload()
        payload["prds"][0]["open_questions"] = ["Confirm the free access threshold."]
        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_empty_success_metrics_require_metric_open_question(self) -> None:
        payload = _payload()
        payload["prds"][0]["success_metrics"] = []
        payload["prds"][0]["open_questions"] = ["Confirm launch sequence."]
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_empty_success_metrics_with_metric_open_question_allowed(self) -> None:
        payload = _payload()
        payload["prds"][0]["success_metrics"] = []
        payload["prds"][0]["open_questions"] = [
            "What measurable success metric should define billing clarity?",
            "What proportion of the library should remain free?",
        ]
        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_multiple_prds(self) -> None:
        payload = _payload()
        payload["prds"].append(
            {
                "prd_id": "PRD-V2",
                "version_id": "V2",
                "title": "Workout content PRD",
                "overview": "Define content quality scope.",
                "problem_statement": "Users need better workout content.",
                "evidence_summary": "Evidence is traceable through REQ-003 and FINDING-002.",
                "goals": ["Improve workout content quality."],
                "non_goals": [],
                "requirement_ids": ["REQ-003"],
                "risks": [],
                "success_metrics": ["Decrease content-related complaint rate."],
                "open_questions": ["What proportion of the library should remain free?"],
            }
        )
        result = _validate(payload)

        self.assertTrue(result.passed)
        self.assertEqual(len(result.prds), 2)

    def test_duplicate_prd_id(self) -> None:
        payload = _payload()
        payload["prds"].append(dict(payload["prds"][0]))
        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_DUPLICATE_PRD_ID)

    def test_input_validation_failed(self) -> None:
        result = validate_prd_output(
            json.dumps(_payload()),
            requirements_by_id=_requirements_by_id(),
            versions_by_id=_versions_by_id(),
            findings_by_id=_findings_by_id(),
            issues_by_id=_issues_by_id(),
            topics_by_id=_topics_by_id(),
            valid_review_ids={"review-001", "review-002"},
            requirement_validation_passed=False,
            roadmap_validation_passed=True,
            finding_validation_passed=True,
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_INPUT_VALIDATION_FAILED)


def _validate(
    payload: dict,
    *,
    requirements_by_id: dict | None = None,
    versions_by_id: dict | None = None,
    findings_by_id: dict | None = None,
    issues_by_id: dict | None = None,
    topics_by_id: dict | None = None,
    valid_review_ids: set[str] | None = None,
):
    return validate_prd_output(
        json.dumps(payload),
        requirements_by_id=requirements_by_id or _requirements_by_id(),
        versions_by_id=versions_by_id or _versions_by_id(),
        findings_by_id=findings_by_id or _findings_by_id(),
        issues_by_id=issues_by_id or _issues_by_id(),
        topics_by_id=topics_by_id or _topics_by_id(),
        valid_review_ids=valid_review_ids or {"review-001", "review-002", "review-003"},
        requirement_validation_passed=True,
        roadmap_validation_passed=True,
        finding_validation_passed=True,
    )


def _payload() -> dict:
    return {
        "prds": [
            {
                "prd_id": "PRD-V1",
                "version_id": "V1",
                "title": "Subscription PRD",
                "overview": "Define subscription scope.",
                "problem_statement": "Users need clearer subscription terms.",
                "evidence_summary": "Evidence is traceable through REQ-001, REQ-002, and FINDING-001.",
                "goals": ["Improve subscription billing clarity."],
                "non_goals": ["Do not expand scope beyond validated subscription requirements."],
                "requirement_ids": ["REQ-001", "REQ-002"],
                "risks": ["Revenue impact requires product review."],
                "success_metrics": ["Decrease subscription complaint rate."],
                "open_questions": ["What proportion of the library should remain free?"],
            }
        ]
    }


def _requirements_by_id() -> dict:
    return {
        "REQ-001": {"requirement_id": "REQ-001", "finding_ids": ["FINDING-001"]},
        "REQ-002": {"requirement_id": "REQ-002", "finding_ids": ["FINDING-001"]},
        "REQ-003": {"requirement_id": "REQ-003", "finding_ids": ["FINDING-002"]},
    }


def _requirements_by_id_with_text() -> dict:
    return {
        "REQ-001": {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "title": "Provide free access options",
            "description": "The product should offer free access without deciding the exact library threshold.",
            "acceptance_criteria": ["Free access behavior is described for users."],
        },
        "REQ-002": {
            "requirement_id": "REQ-002",
            "finding_ids": ["FINDING-001"],
            "title": "Clarify subscription billing",
            "description": "The product should explain subscription billing.",
            "acceptance_criteria": ["Billing terms are clear."],
        },
        "REQ-003": {
            "requirement_id": "REQ-003",
            "finding_ids": ["FINDING-002"],
            "title": "Improve workout content",
            "description": "The product should improve workout content.",
            "acceptance_criteria": ["Content quality is improved."],
        },
    }


def _versions_by_id() -> dict:
    return {
        "V1": {
            "version_id": "V1",
            "goal": "Improve subscription billing clarity.",
            "requirement_ids": ["REQ-001", "REQ-002"],
        },
        "V2": {
            "version_id": "V2",
            "goal": "Improve workout content quality.",
            "requirement_ids": ["REQ-003"],
        },
    }


def _findings_by_id() -> dict:
    return {
        "FINDING-001": {
            "finding_id": "FINDING-001",
            "issue_ids": ["ISSUE-001"],
            "review_ids": ["review-001", "review-002"],
        },
        "FINDING-002": {
            "finding_id": "FINDING-002",
            "issue_ids": ["ISSUE-002"],
            "review_ids": ["review-003"],
        },
    }


def _issues_by_id() -> dict:
    return {
        "ISSUE-001": {"issue_id": "ISSUE-001", "topic_ids": ["TOPIC-001"], "review_ids": ["review-001"]},
        "ISSUE-002": {"issue_id": "ISSUE-002", "topic_ids": ["TOPIC-002"], "review_ids": ["review-003"]},
    }


def _topics_by_id() -> dict:
    return {
        "TOPIC-001": {"topic_id": "TOPIC-001", "review_ids": ["review-001"]},
        "TOPIC-002": {"topic_id": "TOPIC-002", "review_ids": ["review-003"]},
    }


if __name__ == "__main__":
    unittest.main()
