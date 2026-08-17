import unittest

from app.traceability import STATUS_FAIL, STATUS_PASS, TraceabilityArtifacts, TraceabilityGraph


class TraceabilityGraphTests(unittest.TestCase):
    def test_forward_and_backward_traceability_pass(self) -> None:
        graph = TraceabilityGraph(_artifacts())

        result = graph.validate()

        self.assertEqual(result.forward_traceability, STATUS_PASS)
        self.assertEqual(result.backward_traceability, STATUS_PASS)
        self.assertEqual(result.evidence_traceability, STATUS_PASS)
        self.assertEqual(result.explicit_test_case_review_link, STATUS_PASS)
        self.assertEqual(result.version_prd_consistency, STATUS_PASS)
        self.assertEqual(result.ac_structural_coverage, STATUS_PASS)
        self.assertEqual(graph.topics_for_review("review-1")[0]["topic_id"], "TOPIC-001")
        self.assertEqual(graph.issues_for_topic("TOPIC-001")[0]["issue_id"], "ISSUE-001")
        self.assertEqual(graph.findings_for_issue("ISSUE-001")[0]["finding_id"], "FINDING-001")
        self.assertEqual(graph.requirements_for_finding("FINDING-001")[0]["requirement_id"], "REQ-001")
        self.assertEqual(graph.versions_for_requirement("REQ-001")[0]["version_id"], "V1")
        self.assertEqual(graph.prds_for_requirement("REQ-001")[0]["prd_id"], "PRD-V1")
        self.assertEqual(graph.test_cases_for_acceptance_criteria("REQ-001-AC-1")[0]["test_case_id"], "TC-001")
        self.assertEqual(graph.reviews_for_test_case("TC-001")[0]["id"], "review-1")

    def test_unknown_acceptance_criteria_fails_backward_traceability(self) -> None:
        artifacts = _artifacts()
        artifacts.test_cases[0]["acceptance_criteria_ids"] = ["REQ-001-AC-404"]

        result = TraceabilityGraph(artifacts).validate()

        self.assertEqual(result.backward_traceability, STATUS_FAIL)
        self.assertIn("unknown acceptance_criteria_id", "\n".join(result.errors))

    def test_positive_issue_without_finding_is_expected_exclusion(self) -> None:
        artifacts = _artifacts()
        artifacts.issues.append(
            {
                "issue_id": "ISSUE-002",
                "name": "Positive feedback",
                "topic_ids": ["TOPIC-002"],
                "review_ids": ["review-2"],
                "merge_rationale": "Positive evidence only.",
                "confidence": 0.9,
                "uncertainty": "",
            }
        )
        artifacts.topics.append(
            {
                "topic_id": "TOPIC-002",
                "name": "Positive",
                "description": "Positive comments",
                "review_ids": ["review-2"],
                "confidence": 0.9,
                "uncertainty": "",
            }
        )
        artifacts.finding_eligibility["eligibility"].append(
            {
                "issue_id": "ISSUE-002",
                "issue_type": "positive_feedback",
                "eligible_for_finding": False,
                "reason": "Positive feedback is excluded.",
            }
        )

        result = TraceabilityGraph(artifacts).validate()

        self.assertEqual(result.forward_traceability, STATUS_PASS)
        self.assertIn("ISSUE-002", "\n".join(result.expected_exclusions))

    def test_prd_version_mismatch_fails(self) -> None:
        artifacts = _artifacts()
        artifacts.prds[0]["requirement_ids"] = ["REQ-404"]

        result = TraceabilityGraph(artifacts).validate()

        self.assertEqual(result.version_prd_consistency, STATUS_FAIL)

    def test_deferred_requirement_is_expected_exclusion(self) -> None:
        artifacts = _artifacts()
        artifacts.requirements.append(
            {
                "requirement_id": "REQ-002",
                "finding_ids": ["FINDING-001"],
                "title": "Improve subscription support",
                "description": "Improve subscription support.",
                "acceptance_criteria": ["Support requests are acknowledged."],
                "priority": "P3",
                "priority_rationale": "Fixture.",
                "risks": [],
                "success_metrics": [],
                "uncertainty": "Weak evidence.",
                "source_review_ids": ["review-1"],
            }
        )
        artifacts.roadmap["deferred_requirement_ids"] = ["REQ-002"]
        artifacts.roadmap["deferred_rationale"] = {"REQ-002": "Evidence is too weak for the current roadmap."}
        artifacts.test_coverage.update(
            {
                "total_requirements": 2,
                "covered_requirements": 1,
                "requirement_coverage": 50.0,
                "total_acceptance_criteria": 2,
                "covered_acceptance_criteria": 1,
                "acceptance_criteria_coverage": 50.0,
                "uncovered_requirement_ids": ["REQ-002"],
                "uncovered_acceptance_criteria_ids": ["REQ-002-AC-1"],
            }
        )

        result = TraceabilityGraph(artifacts).validate()

        self.assertEqual(result.forward_traceability, STATUS_PASS)
        self.assertEqual(result.ac_structural_coverage, STATUS_PASS)
        self.assertNotIn("REQ-002", result.orphan_summary["orphan_requirements"])
        self.assertNotIn("REQ-002-AC-1", result.orphan_summary["orphan_acceptance_criteria"])
        self.assertIn("REQ-002: deferred from Roadmap with rationale", result.expected_exclusions)

    def test_unassigned_requirement_still_fails_forward_traceability(self) -> None:
        artifacts = _artifacts()
        artifacts.requirements.append(
            {
                "requirement_id": "REQ-002",
                "finding_ids": ["FINDING-001"],
                "title": "Improve subscription support",
                "description": "Improve subscription support.",
                "acceptance_criteria": ["Support requests are acknowledged."],
                "priority": "P3",
                "priority_rationale": "Fixture.",
                "risks": [],
                "success_metrics": [],
                "uncertainty": "Weak evidence.",
                "source_review_ids": ["review-1"],
            }
        )
        artifacts.test_coverage.update(
            {
                "total_requirements": 2,
                "covered_requirements": 1,
                "requirement_coverage": 50.0,
                "total_acceptance_criteria": 2,
                "covered_acceptance_criteria": 1,
                "acceptance_criteria_coverage": 50.0,
                "uncovered_requirement_ids": ["REQ-002"],
                "uncovered_acceptance_criteria_ids": ["REQ-002-AC-1"],
            }
        )

        result = TraceabilityGraph(artifacts).validate()

        self.assertEqual(result.forward_traceability, STATUS_FAIL)
        self.assertIn("REQ-002: no downstream version", result.errors)
        self.assertIn("REQ-002: no downstream PRD", result.errors)


def _artifacts() -> TraceabilityArtifacts:
    return TraceabilityArtifacts(
        reviews=[{"id": "review-1"}, {"id": "review-2"}],
        topics=[
            {
                "topic_id": "TOPIC-001",
                "name": "Subscription issue",
                "description": "Subscription issue",
                "review_ids": ["review-1"],
                "confidence": 0.9,
                "uncertainty": "",
            }
        ],
        topic_validation={"status": "Success", "passed": True},
        issues=[
            {
                "issue_id": "ISSUE-001",
                "name": "Subscription issue",
                "description": "Subscription issue",
                "topic_ids": ["TOPIC-001"],
                "review_ids": ["review-1"],
                "merge_rationale": "Same problem.",
                "confidence": 0.9,
                "uncertainty": "",
            }
        ],
        issue_validation={"status": "Success", "passed": True},
        issue_classification={"classifications": [{"issue_id": "ISSUE-001", "issue_type": "problem"}]},
        finding_eligibility={
            "eligibility": [
                {
                    "issue_id": "ISSUE-001",
                    "issue_type": "problem",
                    "eligible_for_finding": True,
                    "reason": "Problem.",
                }
            ]
        },
        findings=[
            {
                "finding_id": "FINDING-001",
                "issue_ids": ["ISSUE-001"],
                "review_ids": ["review-1"],
                "title": "Subscription issue",
                "statement": "Users report a subscription issue.",
                "evidence_summary": "review-1 supports it.",
                "support_count": 1,
                "confidence": 0.9,
                "uncertainty": "",
                "conflicting_review_ids": [],
            }
        ],
        finding_validation={"status": "Success", "passed": True},
        evidence_report={
            "evidence_reports": [
                {
                    "finding_id": "FINDING-001",
                    "support_count": 1,
                    "unique_support_count": 1,
                    "conflicting_count": 0,
                    "evidence_strength": "Medium",
                    "evidence_limitations": ["fixture"],
                }
            ]
        },
        requirements=[
            {
                "requirement_id": "REQ-001",
                "finding_ids": ["FINDING-001"],
                "title": "Improve subscription clarity",
                "description": "Improve subscription clarity.",
                "acceptance_criteria": ["Subscription price is visible before purchase."],
                "priority": "P1",
                "priority_rationale": "Fixture.",
                "risks": [],
                "success_metrics": [],
                "uncertainty": "",
                "source_review_ids": ["review-1"],
            }
        ],
        requirement_validation={"status": "Success", "passed": True},
        priority_report={
            "priority_report": [
                {
                    "requirement_id": "REQ-001",
                    "final_priority": "P1",
                    "final_score": 1,
                }
            ]
        },
        roadmap={
            "versions": [
                {
                    "version_id": "V1",
                    "name": "Subscription",
                    "goal": "Improve subscription clarity.",
                    "requirement_ids": ["REQ-001"],
                    "rationale": "Fixture.",
                    "risks": [],
                    "success_metrics": [],
                }
            ],
            "roadmap_items": [
                {
                    "requirement_id": "REQ-001",
                    "version_id": "V1",
                    "priority": "P1",
                    "rationale": "Fixture.",
                    "dependencies": [],
                }
            ],
            "deferred_requirement_ids": [],
            "deferred_rationale": {},
        },
        roadmap_validation={"status": "Success", "passed": True},
        prds=[
            {
                "prd_id": "PRD-V1",
                "version_id": "V1",
                "title": "Subscription",
                "overview": "Fixture",
                "problem_statement": "Fixture",
                "evidence_summary": "FINDING-001",
                "goals": ["Improve subscription clarity."],
                "non_goals": [],
                "requirement_ids": ["REQ-001"],
                "risks": [],
                "success_metrics": [],
                "open_questions": ["What price copy should be used?"],
            }
        ],
        prd_validation={"status": "Success", "passed": True},
        test_cases=[
            {
                "test_case_id": "TC-001",
                "requirement_id": "REQ-001",
                "acceptance_criteria_ids": ["REQ-001-AC-1"],
                "title": "Verify subscription price visibility",
                "preconditions": [],
                "steps": ["Open purchase flow.", "Check price text."],
                "expected_result": "Subscription price is visible before purchase.",
                "test_type": "functional",
                "priority": "P1",
                "source_review_ids": ["review-1"],
            }
        ],
        test_case_validation={"status": "Success", "passed": True},
        test_coverage={
            "total_requirements": 1,
            "covered_requirements": 1,
            "requirement_coverage": 100.0,
            "total_acceptance_criteria": 1,
            "covered_acceptance_criteria": 1,
            "acceptance_criteria_coverage": 100.0,
            "uncovered_requirement_ids": [],
            "uncovered_acceptance_criteria_ids": [],
        },
        processing_statistics={"total": 2},
        processing_report={"input_count": 2},
    )


if __name__ == "__main__":
    unittest.main()
