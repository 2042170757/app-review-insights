import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.test_case_generator import build_default_mock_output, create_mock_provider, generate_test_cases, save_test_case_outputs


class TestCaseGeneratorTests(unittest.TestCase):
    def test_default_mock_output_covers_all_acceptance_criteria(self) -> None:
        payload = json.loads(build_default_mock_output(_requirements()))

        self.assertEqual(len(payload["test_cases"]), 3)
        self.assertEqual(payload["test_cases"][0]["acceptance_criteria_ids"], ["REQ-001-AC-1"])
        self.assertEqual(payload["test_cases"][2]["acceptance_criteria_ids"], ["REQ-002-AC-1"])

    def test_generate_test_cases_with_mock_provider(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = generate_test_cases(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                prd_validation=_pass_validation(),
                findings=_findings(),
                reviews=_reviews(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result.generation_passed)
        self.assertTrue(result.validation.passed)
        self.assertEqual(result.provider, "mock")
        self.assertEqual(len(result.test_cases), 3)
        self.assertEqual(result.coverage.requirement_coverage, 100.0)
        self.assertEqual(result.coverage.acceptance_criteria_coverage, 100.0)

    def test_input_validation_failure_skips_generation(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = generate_test_cases(
                requirements=_requirements(),
                requirement_validation={"status": "Failed", "passed": False},
                prd_validation=_pass_validation(),
                provider=provider,
                output_dir=Path(temp_dir),
            )

        self.assertFalse(result.generation_passed)
        self.assertEqual(result.generation_status, "Input Validation Failed")
        self.assertEqual(result.validation.status, "SKIPPED")
        self.assertEqual(provider.requests, [])

    def test_save_outputs_marks_mock(self) -> None:
        provider = create_mock_provider(build_default_mock_output(_requirements()))
        with TemporaryDirectory() as temp_dir:
            result = generate_test_cases(
                requirements=_requirements(),
                requirement_validation=_pass_validation(),
                prd_validation=_pass_validation(),
                findings=_findings(),
                reviews=_reviews(),
                provider=provider,
                output_dir=Path(temp_dir),
            )
            paths = save_test_case_outputs(result, output_dir=Path(temp_dir))
            raw = json.loads(paths["raw"].read_text(encoding="utf-8"))
            test_cases = json.loads(paths["test_cases"].read_text(encoding="utf-8"))
            coverage = json.loads(paths["coverage"].read_text(encoding="utf-8"))

        self.assertTrue(raw["is_mock"])
        self.assertEqual(raw["provider"], "mock")
        self.assertEqual(len(test_cases["test_cases"]), 3)
        self.assertEqual(coverage["covered_acceptance_criteria"], 3)


def _pass_validation() -> dict:
    return {"status": "Success", "passed": True}


def _requirements() -> list[dict]:
    return [
        {
            "requirement_id": "REQ-001",
            "finding_ids": ["FINDING-001"],
            "acceptance_criteria": ["Free access is visible.", "Free access limits are explained."],
            "priority": "P1",
        },
        {
            "requirement_id": "REQ-002",
            "finding_ids": ["FINDING-002"],
            "acceptance_criteria": ["Subscription value is explained."],
            "priority": "P2",
        },
    ]


def _findings() -> list[dict]:
    return [
        {"finding_id": "FINDING-001", "review_ids": ["review-001"]},
        {"finding_id": "FINDING-002", "review_ids": ["review-002"]},
    ]


def _reviews() -> list[dict]:
    return [{"id": "review-001"}, {"id": "review-002"}]


if __name__ == "__main__":
    unittest.main()
