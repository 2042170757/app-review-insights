import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.find_findings import (
    build_default_mock_output,
    load_eligibility,
    load_issues,
    load_reviews,
    save_outputs,
)
from app.finding_validator import validate_finding_output
from app.llm.base import LLMRequest
from app.llm.mock_provider import MockLLMProvider


class FindFindingsTests(unittest.TestCase):
    def test_default_mock_output_uses_eligible_issue(self) -> None:
        raw_output = build_default_mock_output(_issues(), _eligibility())
        payload = json.loads(raw_output)

        self.assertEqual(payload["findings"][0]["issue_ids"], ["ISSUE-001"])
        self.assertEqual(payload["findings"][0]["support_count"], 2)

    def test_default_mock_output_empty_without_eligible_issue(self) -> None:
        raw_output = build_default_mock_output(_issues(), [])

        self.assertEqual(json.loads(raw_output), {"findings": []})

    def test_mock_provider(self) -> None:
        provider = MockLLMProvider(json.dumps({"findings": []}), model="mock-finding-model")
        request = LLMRequest("system", "user", "goal")

        response = provider.generate(request)

        self.assertEqual(response.provider, "mock")
        self.assertEqual(response.raw_text, json.dumps({"findings": []}))

    def test_save_outputs(self) -> None:
        raw_output = build_default_mock_output(_issues(), _eligibility())
        validation = validate_finding_output(
            raw_output,
            issues_by_id={issue["issue_id"]: issue for issue in _issues()},
            valid_review_ids={"r1", "r2"},
            eligible_issue_ids={"ISSUE-001"},
        )
        with TemporaryDirectory() as temp_dir:
            paths = save_outputs(
                raw_output=raw_output,
                validation=validation,
                findings=[finding.__dict__ for finding in validation.findings],
                evidence_reports=[report.to_dict() for report in validation.evidence_reports],
                output_dir=Path(temp_dir),
            )
            raw = json.loads(paths["raw"].read_text(encoding="utf-8"))
            findings = json.loads(paths["findings"].read_text(encoding="utf-8"))
            evidence = json.loads(paths["evidence"].read_text(encoding="utf-8"))

        self.assertEqual(raw["provider"], "mock")
        self.assertTrue(raw["is_mock"])
        self.assertEqual(len(findings["findings"]), 1)
        self.assertEqual(evidence["evidence_reports"][0]["evidence_strength"], "Medium")

    def test_loaders(self) -> None:
        with TemporaryDirectory() as temp_dir:
            reviews_path = Path(temp_dir) / "reviews.json"
            issues_path = Path(temp_dir) / "issues.json"
            eligibility_path = Path(temp_dir) / "eligibility.json"
            reviews_path.write_text(json.dumps({"reviews": [{"id": "r1"}]}), encoding="utf-8")
            issues_path.write_text(json.dumps({"issues": _issues()}), encoding="utf-8")
            eligibility_path.write_text(json.dumps({"eligibility": _eligibility()}), encoding="utf-8")

            reviews = load_reviews(reviews_path)
            issues = load_issues(issues_path)
            eligibility = load_eligibility(eligibility_path)

        self.assertEqual(reviews[0]["id"], "r1")
        self.assertEqual(issues[0]["issue_id"], "ISSUE-001")
        self.assertTrue(eligibility[0]["eligible_for_finding"])


def _issues() -> list[dict]:
    return [
        {
            "issue_id": "ISSUE-001",
            "name": "Paywall friction",
            "description": "Users report paywall friction.",
            "review_ids": ["r1", "r2"],
            "confidence": 0.82,
            "uncertainty": "",
        }
    ]


def _eligibility() -> list[dict]:
    return [
        {
            "issue_id": "ISSUE-001",
            "issue_type": "problem",
            "eligible_for_finding": True,
            "reason": "Problem issue.",
        }
    ]


if __name__ == "__main__":
    unittest.main()
