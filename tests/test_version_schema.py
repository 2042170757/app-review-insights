import unittest

from app.version_schema import VALID_VERSION_IDS, VERSION_JSON_SCHEMA, Version


class VersionSchemaTests(unittest.TestCase):
    def test_valid_version_ids(self) -> None:
        self.assertEqual(VALID_VERSION_IDS, {"V1", "V2", "V3", "Deferred"})

    def test_version_dataclass(self) -> None:
        version = Version(
            version_id="V1",
            name="Subscription improvements",
            goal="Improve subscription clarity.",
            requirement_ids=["REQ-001"],
            rationale="High-priority validated requirement.",
            risks=[],
            success_metrics=[],
        )

        self.assertEqual(version.version_id, "V1")
        self.assertEqual(version.requirement_ids, ["REQ-001"])

    def test_schema_requires_version_fields(self) -> None:
        required = set(VERSION_JSON_SCHEMA["properties"]["versions"]["items"]["required"])

        self.assertIn("version_id", required)
        self.assertIn("goal", required)
        self.assertIn("requirement_ids", required)
        self.assertIn("rationale", required)


if __name__ == "__main__":
    unittest.main()
