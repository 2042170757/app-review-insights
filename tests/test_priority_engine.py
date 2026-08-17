import unittest

from app.priority_engine import assign_requirement_priorities, calculate_requirement_priority


class PriorityEngineTests(unittest.TestCase):
    def test_high_support_high_confidence_stays_conservative_without_impact_score(self) -> None:
        decision = calculate_requirement_priority(
            _requirement(finding_ids=["FINDING-001"], priority="P0"),
            findings_by_id={"FINDING-001": _finding(support_count=15, confidence=0.95)},
            evidence_reports_by_id={"FINDING-001": _evidence_report(support_count=15, evidence_strength="High")},
        )

        self.assertEqual(decision.final_priority, "P1")
        self.assertEqual(decision.suggested_priority, "P0")
        self.assertIn("conservative", decision.rationale)

    def test_medium_evidence_maps_to_p2_boundary(self) -> None:
        decision = calculate_requirement_priority(
            _requirement(finding_ids=["FINDING-002"]),
            findings_by_id={"FINDING-002": _finding(support_count=3, confidence=0.7)},
            evidence_reports_by_id={"FINDING-002": _evidence_report(support_count=3, evidence_strength="Medium")},
        )

        self.assertEqual(decision.final_priority, "P2")

    def test_low_evidence_with_conflict_maps_to_p3(self) -> None:
        decision = calculate_requirement_priority(
            _requirement(finding_ids=["FINDING-003"], uncertainty="unclear impact"),
            findings_by_id={
                "FINDING-003": _finding(
                    support_count=1,
                    confidence=0.5,
                    uncertainty="unclear scope",
                    conflicting_review_ids=["r9", "r10"],
                )
            },
            evidence_reports_by_id={
                "FINDING-003": _evidence_report(
                    support_count=1,
                    evidence_strength="Low",
                    conflicting_count=2,
                )
            },
        )

        self.assertEqual(decision.final_priority, "P3")
        self.assertGreater(decision.conflict_penalty, 0)
        self.assertGreater(decision.uncertainty_penalty, 0)

    def test_assign_priorities_overwrites_suggested_priority(self) -> None:
        payload, decisions = assign_requirement_priorities(
            {
                "requirements": [
                    _requirement(
                        priority="P0",
                        priority_rationale="Model suggested P0.",
                        suggested_priority="P0",
                        suggested_priority_rationale="Model rationale.",
                    )
                ]
            },
            findings_by_id={"FINDING-001": _finding(support_count=2, confidence=0.7)},
            evidence_reports_by_id={"FINDING-001": _evidence_report(support_count=2, evidence_strength="Medium")},
        )

        self.assertEqual(payload["requirements"][0]["priority"], "P2")
        self.assertNotIn("suggested_priority", payload["requirements"][0])
        self.assertEqual(decisions[0].suggested_priority, "P0")


def _requirement(**overrides) -> dict:
    requirement = {
        "requirement_id": "REQ-001",
        "finding_ids": ["FINDING-001"],
        "title": "Clarify subscription terms",
        "description": "Users need clear subscription terms before commitment.",
        "acceptance_criteria": ["Users can see renewal price and renewal date before confirming."],
        "priority": "P1",
        "priority_rationale": "Model rationale.",
        "risks": [],
        "success_metrics": [],
        "uncertainty": "Small sample.",
    }
    requirement.update(overrides)
    return requirement


def _finding(**overrides) -> dict:
    finding = {
        "finding_id": "FINDING-001",
        "support_count": 2,
        "confidence": 0.8,
        "uncertainty": "Small sample.",
        "conflicting_review_ids": [],
    }
    finding.update(overrides)
    return finding


def _evidence_report(**overrides) -> dict:
    report = {
        "finding_id": "FINDING-001",
        "support_count": 2,
        "evidence_strength": "Medium",
        "conflicting_count": 0,
    }
    report.update(overrides)
    return report


if __name__ == "__main__":
    unittest.main()
