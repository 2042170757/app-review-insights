import unittest

from app.model_registry import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    audit_ai_deterministic_boundary,
    audit_failure_state_registry,
    build_model_registry,
)


class ModelRegistryTests(unittest.TestCase):
    def test_registry_contains_deepseek_for_all_semantic_tasks(self) -> None:
        registry = build_model_registry()

        self.assertGreaterEqual(len(registry), 7)
        self.assertTrue(all(item.provider == DEFAULT_PROVIDER for item in registry))
        self.assertTrue(all(item.model == DEFAULT_MODEL for item in registry))
        self.assertIn("Topic Discovery", {item.task for item in registry})
        self.assertIn("Test Case Generation", {item.task for item in registry})

    def test_registry_configuration_records_runtime_parameters(self) -> None:
        entry = build_model_registry()[0]

        self.assertEqual(entry.configuration["thinking"], {"type": "disabled"})
        self.assertEqual(entry.configuration["max_tokens"], 3000)
        self.assertEqual(entry.configuration["temperature"], 0.2)
        self.assertFalse(entry.configuration["stream"])
        self.assertEqual(entry.configuration["timeout_seconds"], 60)

    def test_ai_deterministic_boundary_has_no_overlap(self) -> None:
        result = audit_ai_deterministic_boundary()

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["overlap"], [])
        self.assertIn("Traceability Validation", result["deterministic_tasks"])
        self.assertIn("Requirement Generation", result["model_driven_tasks"])

    def test_failure_state_registry_contains_required_states(self) -> None:
        result = audit_failure_state_registry()

        self.assertEqual(result["status"], "PASS")
        self.assertIn("Missing API Key", result["failure_states"])
        self.assertIn("SKIPPED", result["failure_states"])
        self.assertIn("Evidence Insufficient", result["failure_states"])


if __name__ == "__main__":
    unittest.main()
