import tempfile
import unittest
from pathlib import Path

from app.appstore_connect_probe import (
    ENV_ISSUER_ID,
    ENV_KEY_ID,
    ENV_PRIVATE_KEY_PATH,
    classify_api_failure,
    find_target_app,
    generate_jwt,
    load_config,
    ProbeConfig,
)


class AppStoreConnectProbeTests(unittest.TestCase):
    def test_missing_environment_variables(self) -> None:
        config, error = load_config({})

        self.assertIsNone(config)
        self.assertIsNotNone(error)
        assert error is not None
        self.assertEqual(error.status, "FAIL")
        self.assertEqual(error.diagnosis, "MISSING_ENVIRONMENT_VARIABLES")
        self.assertIn(ENV_ISSUER_ID, error.error_message or "")
        self.assertIn(ENV_KEY_ID, error.error_message or "")
        self.assertIn(ENV_PRIVATE_KEY_PATH, error.error_message or "")

    def test_private_key_file_not_found(self) -> None:
        env = {
            ENV_ISSUER_ID: "issuer",
            ENV_KEY_ID: "key",
            ENV_PRIVATE_KEY_PATH: "does-not-exist/AuthKey_TEST.p8",
        }

        config, error = load_config(env)

        self.assertIsNone(config)
        self.assertIsNotNone(error)
        assert error is not None
        self.assertEqual(error.diagnosis, "PRIVATE_KEY_FILE_NOT_FOUND")

    def test_complete_config_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "AuthKey_TEST.p8"
            key_path.write_text("not-a-real-key", encoding="utf-8")
            env = {
                ENV_ISSUER_ID: "issuer",
                ENV_KEY_ID: "key",
                ENV_PRIVATE_KEY_PATH: str(key_path),
            }

            config, error = load_config(env)

        self.assertIsNone(error)
        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.issuer_id, "issuer")
        self.assertEqual(config.key_id, "key")

    def test_jwt_generation_with_valid_ec_private_key(self) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "AuthKey_TEST.p8"
            private_key = ec.generate_private_key(ec.SECP256R1())
            key_path.write_bytes(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

            token, error = generate_jwt(
                ProbeConfig(
                    issuer_id="issuer",
                    key_id="key",
                    private_key_path=key_path,
                )
            )

        self.assertIsNone(error)
        self.assertIsNotNone(token)
        assert token is not None
        self.assertEqual(len(token.split(".")), 3)

    def test_error_mapping(self) -> None:
        self.assertEqual(
            classify_api_failure(401, "NOT_AUTHORIZED", "invalid token"),
            "401_UNAUTHORIZED_JWT_OR_API_KEY_REJECTED",
        )
        self.assertEqual(
            classify_api_failure(403, "FORBIDDEN", "insufficient role"),
            "403_FORBIDDEN_INSUFFICIENT_PERMISSION",
        )
        self.assertEqual(
            classify_api_failure(403, "FORBIDDEN", "API access has not been enabled"),
            "API_ACCESS_NOT_ENABLED",
        )
        self.assertEqual(
            classify_api_failure(404, "NOT_FOUND", "resource not found"),
            "RESOURCE_NOT_FOUND_OR_APP_NOT_VISIBLE",
        )

    def test_find_target_app_by_resource_or_attribute_id(self) -> None:
        apps = [
            {"id": "other", "attributes": {"name": "Other"}},
            {"id": "resource-1", "attributes": {"appStoreId": "839285684"}},
        ]

        self.assertEqual(find_target_app(apps, "839285684"), apps[1])
        self.assertEqual(find_target_app([{"id": "839285684"}], "839285684"), {"id": "839285684"})
        self.assertIsNone(find_target_app(apps, "123"))


if __name__ == "__main__":
    unittest.main()
