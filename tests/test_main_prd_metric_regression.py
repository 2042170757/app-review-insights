import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.llm.mock_provider import MockLLMProvider
from app.main_prd_metric_diagnosis import diagnose_main_prd_metric_failure
from app.prd_generator import build_prd_request, generate_prds
from app.prd_validator import STATUS_SUCCESS, STATUS_SUCCESS_METRIC_INVALID, validate_prd_output


class MainPRDMetricRegressionTests(unittest.TestCase):
    def test_main_sample_prd_request_marks_underdefined_requirement_metric(self) -> None:
        request = build_prd_request(
            requirements=_requirements(),
            roadmap=_roadmap(),
            findings=_findings(),
            evidence_report={"evidence_reports": []},
            analysis_goal="分析低评分用户对订阅和价格的主要问题",
        )
        payload = json.loads(request.user_prompt)
        version = payload["validated_versions"][1]
        req_005 = _prompt_requirement(version, "REQ-005")

        self.assertEqual(version["version_id"], "V2")
        self.assertIn("User satisfaction with workout relevance.", req_005["unsupported_success_metric_candidates"])
        self.assertNotIn("User satisfaction with workout relevance.", req_005["validated_success_metric_candidates"])
        self.assertIn("unsupported_success_metric_candidates", payload["unsupported_metric_rule"])

    def test_prds_1_failure_metric_is_rejected_as_vague(self) -> None:
        payload = _prd_payload(
            prd_id="PRD-V2",
            version_id="V2",
            requirement_ids=["REQ-002", "REQ-005"],
            goals=["Build user trust through transparent subscription practices and improve personalization by respecting user preferences in workout plans."],
            success_metrics=["Reduction in billing-related complaints.", "User satisfaction with workout relevance."],
            open_questions=[
                "How should user satisfaction with workout relevance be measured as a score or survey rating?",
            ],
        )

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)
        self.assertIn("prds[0].success_metrics[1]: not measurable", result.errors)

    def test_measurable_metric_passes_for_main_sample_context(self) -> None:
        payload = _prd_payload(
            prd_id="PRD-V2",
            version_id="V2",
            requirement_ids=["REQ-002", "REQ-005"],
            goals=["Build user trust through transparent subscription practices and improve personalization by respecting user preferences in workout plans."],
            success_metrics=[
                "Reduction in billing-related complaints.",
                "User-reported workout relevance satisfaction score.",
            ],
        )

        result = _validate(payload)

        self.assertTrue(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS)

    def test_empty_metrics_with_metric_open_question_passes_for_prds_1(self) -> None:
        payload = _prd_payload(
            prd_id="PRD-V2",
            version_id="V2",
            requirement_ids=["REQ-002", "REQ-005"],
            goals=["Build user trust through transparent subscription practices and improve personalization by respecting user preferences in workout plans."],
            success_metrics=[],
            open_questions=[
                "What measurable success metric should define workout relevance and billing clarity?",
            ],
        )

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_empty_metrics_without_metric_open_question_fails(self) -> None:
        payload = _prd_payload(
            success_metrics=[],
            open_questions=["Confirm launch sequencing."],
        )

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_unsupported_numeric_target_still_fails(self) -> None:
        payload = _prd_payload(success_metrics=["Decrease billing complaints by 20%."])

        result = _validate(payload)

        self.assertFalse(result.passed)
        self.assertEqual(result.status, STATUS_SUCCESS_METRIC_INVALID)

    def test_evidence_backed_numeric_target_still_passes(self) -> None:
        requirements = _requirements_by_id()
        requirements["REQ-001"]["success_metrics"] = ["Decrease billing complaints by 10%."]
        payload = _prd_payload(
            success_metrics=["Decrease billing complaints by 10%."],
            open_questions=[
                "What measurable success target should define this PRD?",
                "What free access threshold or scope should be used?",
            ],
        )

        result = _validate(payload, requirements_by_id=requirements)

        self.assertTrue(result.passed)

    def test_prd_id_generalization_does_not_depend_on_prd_v2(self) -> None:
        payload = _prd_payload(
            prd_id="PRD-CUSTOM",
            version_id="V3",
            requirement_ids=["REQ-006"],
            goals=["Reduce disruptive ads and redirects during workout sessions."],
            success_metrics=[],
            open_questions=["What measurable success metric should define ad disruption reduction?"],
        )

        result = _validate(payload)

        self.assertTrue(result.passed)

    def test_version_generalization_marks_unsupported_metrics_for_any_version(self) -> None:
        roadmap = _roadmap()
        roadmap["versions"][2]["success_metrics"] = ["User satisfaction with ad experience."]
        request = build_prd_request(
            requirements=_requirements(),
            roadmap=roadmap,
            findings=_findings(),
            evidence_report={"evidence_reports": []},
            analysis_goal="Goal",
        )
        payload = json.loads(request.user_prompt)
        version = _prompt_version(payload, "V3")

        self.assertIn("User satisfaction with ad experience.", version["unsupported_success_metric_candidates"])

    def test_generator_accepts_repaired_main_prd_with_empty_metrics_and_open_question(self) -> None:
        provider = MockLLMProvider(
            json.dumps(
                _prd_payload(
                    prd_id="PRD-V2",
                    version_id="V2",
                    requirement_ids=["REQ-002", "REQ-005"],
                    goals=[
                        "Build user trust through transparent subscription practices and improve personalization by respecting user preferences in workout plans."
                    ],
                    success_metrics=[],
                    open_questions=[
                        "What measurable success metric should define workout relevance and billing clarity?",
                    ],
                )
            ),
            model="mock-prd-model",
        )

        with TemporaryDirectory() as temp_dir:
            result = generate_prds(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                roadmap={"versions": [_roadmap()["versions"][1]]},
                roadmap_validation=_pass_validation(),
                findings=_findings(),
                finding_validation=_pass_validation(),
                issues=list(_issues_by_id().values()),
                topics=list(_topics_by_id().values()),
                reviews=_reviews(),
                provider=provider,
                analysis_goal="Goal",
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result.validation.passed)
        self.assertEqual(result.prds[0]["success_metrics"], [])

    def test_diagnosis_classifies_main_sample_metric_as_generator_bug(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_analysis_fixture(root)

            report = diagnose_main_prd_metric_failure(analysis_dir=root, output_path=root / "diagnosis.json")

        self.assertEqual(report["prd_id"], "PRD-V2")
        self.assertEqual(report["failed_metric"], "User satisfaction with workout relevance.")
        self.assertIn("Generator Bug", report["metric_classification"])
        self.assertEqual(report["root_cause"], "model_copied_underdefined_requirement_metric_into_prd_success_metrics")


def _validate(payload: dict, *, requirements_by_id: dict | None = None):
    return validate_prd_output(
        json.dumps(payload),
        requirements_by_id=requirements_by_id or _requirements_by_id(),
        versions_by_id=_versions_by_id(),
        findings_by_id=_findings_by_id(),
        issues_by_id=_issues_by_id(),
        topics_by_id=_topics_by_id(),
        valid_review_ids={review["id"] for review in _reviews()},
        requirement_validation_passed=True,
        roadmap_validation_passed=True,
        finding_validation_passed=True,
    )


def _prd_payload(
    *,
    prd_id: str = "PRD-V1",
    version_id: str = "V1",
    requirement_ids: list[str] | None = None,
    goals: list[str] | None = None,
    success_metrics: list[str],
    open_questions: list[str] | None = None,
) -> dict:
    requirement_ids = requirement_ids or ["REQ-001"]
    goals = goals or ["Improve subscription access transparency."]
    return {
        "prds": [
            {
                "prd_id": prd_id,
                "version_id": version_id,
                "title": "Main sample PRD",
                "overview": "Defines the validated product scope.",
                "problem_statement": "Users need the validated product behavior addressed.",
                "evidence_summary": f"Evidence is traceable through {requirement_ids[0]} and FINDING-001.",
                "goals": goals,
                "non_goals": ["Do not expand scope beyond validated requirements."],
                "requirement_ids": requirement_ids,
                "risks": ["Metric target may require product decision."],
                "success_metrics": success_metrics,
                "open_questions": open_questions
                or ["What measurable success target should define this PRD?"],
            }
        ]
    }


def _roadmap() -> dict:
    return {
        "versions": [
            {
                "version_id": "V1",
                "name": "Subscription Access",
                "goal": "Improve subscription access transparency.",
                "requirement_ids": ["REQ-001"],
                "rationale": "Fixture.",
                "risks": [],
                "success_metrics": [],
            },
            {
                "version_id": "V2",
                "name": "Trust and Personalization",
                "goal": "Build user trust through transparent subscription practices and improve personalization by respecting user preferences in workout plans.",
                "requirement_ids": ["REQ-002", "REQ-005"],
                "rationale": "Fixture.",
                "risks": [],
                "success_metrics": ["Reduction in billing-related complaints.", "User satisfaction with workout relevance."],
            },
            {
                "version_id": "V3",
                "name": "Ad Experience",
                "goal": "Reduce disruptive ads and redirects during workout sessions.",
                "requirement_ids": ["REQ-006"],
                "rationale": "Fixture.",
                "risks": [],
                "success_metrics": [],
            },
        ]
    }


def _requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "title": "Clarify subscription access",
            "description": "Users need clearer free and paid access boundaries.",
            "acceptance_criteria": ["Access rules are visible before purchase."],
            "priority": "P1",
            "priority_rationale": "Fixture.",
            "risks": [],
            "success_metrics": [],
            "uncertainty": "",
            "source_review_ids": ["review-001"],
            "requirement_type": "problem",
        },
        {
            "requirement_id": "REQ-002",
            "finding_ids": ["FINDING-002"],
            "title": "Ensure transparent subscription and billing practices",
            "description": "Users need clear subscription terms and cancellation.",
            "acceptance_criteria": ["Cancellation can be completed in the app."],
            "priority": "P2",
            "priority_rationale": "Fixture.",
            "risks": [],
            "success_metrics": ["Reduction in billing-related complaints."],
            "uncertainty": "",
            "source_review_ids": ["review-002"],
            "requirement_type": "problem",
        },
        {
            "requirement_id": "REQ-005",
            "finding_ids": ["FINDING-005"],
            "title": "Respect user preferences in workout plans",
            "description": "Workout plans should respect stated user preferences.",
            "acceptance_criteria": ["Users can specify preferences."],
            "priority": "P2",
            "priority_rationale": "Fixture.",
            "risks": [],
            "success_metrics": ["User satisfaction with workout relevance."],
            "uncertainty": "",
            "source_review_ids": ["review-005"],
            "requirement_type": "problem",
        },
        {
            "requirement_id": "REQ-006",
            "finding_ids": ["FINDING-006"],
            "title": "Reduce disruptive ads",
            "description": "Ads should not interrupt workout sessions.",
            "acceptance_criteria": ["Ads do not redirect unexpectedly."],
            "priority": "P2",
            "priority_rationale": "Fixture.",
            "risks": [],
            "success_metrics": [],
            "uncertainty": "",
            "source_review_ids": ["review-006"],
            "requirement_type": "problem",
        },
    ]


def _requirements_by_id() -> dict:
    return {item["requirement_id"]: item for item in _requirements()}


def _versions_by_id() -> dict:
    return {item["version_id"]: item for item in _roadmap()["versions"]}


def _findings() -> list[dict]:
    return [
        {
            "finding_id": finding_id,
            "title": "Finding",
            "statement": "Users describe the validated issue.",
            "issue_ids": [issue_id],
            "review_ids": [review_id],
            "confidence": 0.8,
            "uncertainty": "",
            "conflicting_review_ids": [],
        }
        for finding_id, issue_id, review_id in [
            ("FINDING-001", "ISSUE-001", "review-001"),
            ("FINDING-002", "ISSUE-002", "review-002"),
            ("FINDING-005", "ISSUE-005", "review-005"),
            ("FINDING-006", "ISSUE-006", "review-006"),
        ]
    ]


def _findings_by_id() -> dict:
    return {item["finding_id"]: item for item in _findings()}


def _issues_by_id() -> dict:
    return {
        issue_id: {"issue_id": issue_id, "topic_ids": [topic_id], "review_ids": [review_id]}
        for issue_id, topic_id, review_id in [
            ("ISSUE-001", "TOPIC-001", "review-001"),
            ("ISSUE-002", "TOPIC-002", "review-002"),
            ("ISSUE-005", "TOPIC-005", "review-005"),
            ("ISSUE-006", "TOPIC-006", "review-006"),
        ]
    }


def _topics_by_id() -> dict:
    return {
        topic_id: {"topic_id": topic_id, "review_ids": [review_id]}
        for topic_id, review_id in [
            ("TOPIC-001", "review-001"),
            ("TOPIC-002", "review-002"),
            ("TOPIC-005", "review-005"),
            ("TOPIC-006", "review-006"),
        ]
    }


def _reviews() -> list[dict]:
    return [{"id": "review-001"}, {"id": "review-002"}, {"id": "review-005"}, {"id": "review-006"}]


def _pass_validation() -> dict:
    return {"status": "Success", "passed": True}


def _prompt_version(payload: dict, version_id: str) -> dict:
    for version in payload.get("validated_versions", []):
        if version.get("version_id") == version_id:
            return version
    return {}


def _prompt_requirement(version: dict, requirement_id: str) -> dict:
    for requirement in version.get("requirements", []):
        if requirement.get("requirement_id") == requirement_id:
            return requirement
    return {}


def _write_analysis_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    prds = _prd_payload(
        prd_id="PRD-V2",
        version_id="V2",
        requirement_ids=["REQ-002", "REQ-005"],
        goals=["Build user trust through transparent subscription practices and improve personalization by respecting user preferences in workout plans."],
        success_metrics=["Reduction in billing-related complaints.", "User satisfaction with workout relevance."],
    )
    (root / "prd_generation_raw.json").write_text(
        json.dumps(
            {
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "analysis_goal": "分析低评分用户对订阅和价格的主要问题",
                "extracted_json": json.dumps(prds),
                "response_metadata": {
                    "max_tokens": 3000,
                    "temperature": 0.2,
                    "thinking": {"type": "disabled"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "prd_validation.json").write_text(
        json.dumps({"status": "Success Metric Invalid", "errors": ["prds[0].success_metrics[1]: not measurable"]}),
        encoding="utf-8",
    )
    (root / "roadmap.json").write_text(json.dumps(_roadmap(), ensure_ascii=False), encoding="utf-8")
    (root / "requirements.json").write_text(json.dumps({"requirements": _requirements()}, ensure_ascii=False), encoding="utf-8")
    (root / "findings.json").write_text(json.dumps({"findings": _findings()}, ensure_ascii=False), encoding="utf-8")
    (root / "evidence_report.json").write_text(json.dumps({"evidence_reports": []}), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
