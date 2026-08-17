import io
import json
import os
import socket
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app.llm.base import (
    LLMRequest,
    MissingAPIKeyError,
    ModelAuthenticationError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
)
from app.llm.deepseek_provider import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_THINKING,
    DEFAULT_TIMEOUT_SECONDS,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MAX_TOKENS,
    DEEPSEEK_MODEL,
    DEEPSEEK_TEMPERATURE,
    DEEPSEEK_THINKING,
    DEEPSEEK_TIMEOUT,
    DeepSeekProvider,
)
from app.topic_discovery import extract_json_text


class DeepSeekProviderTests(unittest.TestCase):
    def test_missing_deepseek_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingAPIKeyError):
                DeepSeekProvider.from_env()

    def test_base_url_configuration(self) -> None:
        with patch.dict(
            os.environ,
            {
                DEEPSEEK_API_KEY: "secret-key",
                DEEPSEEK_BASE_URL: "https://example.deepseek.local/",
            },
            clear=True,
        ):
            provider = DeepSeekProvider.from_env()

        self.assertEqual(provider.base_url, "https://example.deepseek.local")

    def test_model_configuration(self) -> None:
        with patch.dict(
            os.environ,
            {DEEPSEEK_API_KEY: "secret-key", DEEPSEEK_MODEL: "deepseek-reasoner"},
            clear=True,
        ):
            provider = DeepSeekProvider.from_env()

        self.assertEqual(provider.model, "deepseek-reasoner")

    def test_default_model_and_base_url(self) -> None:
        provider = DeepSeekProvider(api_key="secret-key")

        self.assertEqual(provider.model, DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(provider.base_url, DEFAULT_DEEPSEEK_BASE_URL)
        self.assertEqual(provider.thinking, DEFAULT_THINKING)
        self.assertEqual(provider.max_tokens, DEFAULT_MAX_TOKENS)
        self.assertEqual(provider.temperature, DEFAULT_TEMPERATURE)
        self.assertEqual(provider.timeout_seconds, DEFAULT_TIMEOUT_SECONDS)

    def test_runtime_parameters_can_be_configured_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                DEEPSEEK_API_KEY: "secret-key",
                DEEPSEEK_MODEL: "deepseek-v4-flash",
                DEEPSEEK_THINKING: "disabled",
                DEEPSEEK_MAX_TOKENS: "2500",
                DEEPSEEK_TEMPERATURE: "0.1",
                DEEPSEEK_TIMEOUT: "45",
            },
            clear=True,
        ):
            provider = DeepSeekProvider.from_env()

        self.assertEqual(provider.model, "deepseek-v4-flash")
        self.assertEqual(provider.thinking, "disabled")
        self.assertEqual(provider.max_tokens, 2500)
        self.assertEqual(provider.temperature, 0.1)
        self.assertEqual(provider.timeout_seconds, 45.0)

    def test_invalid_runtime_configuration(self) -> None:
        invalid_envs = [
            {DEEPSEEK_API_KEY: "secret-key", DEEPSEEK_THINKING: "maybe"},
            {DEEPSEEK_API_KEY: "secret-key", DEEPSEEK_MAX_TOKENS: "0"},
            {DEEPSEEK_API_KEY: "secret-key", DEEPSEEK_TEMPERATURE: "3"},
            {DEEPSEEK_API_KEY: "secret-key", DEEPSEEK_TIMEOUT: "0"},
        ]
        for env in invalid_envs:
            with self.subTest(env=env):
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(ModelRequestError):
                        DeepSeekProvider.from_env()

    @patch("app.llm.deepseek_provider.urlopen")
    def test_normal_api_response(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _FakeHTTPResponse(
            {
                "id": "chatcmpl-test",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "topics": [
                                        {
                                            "topic_id": "TOPIC-001",
                                            "name": "Pricing",
                                            "description": "Pricing concern.",
                                            "review_ids": ["r1"],
                                            "confidence": 0.8,
                                            "uncertainty": "",
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ],
            },
            status=200,
        )
        provider = DeepSeekProvider(api_key="secret-key", model="deepseek-chat")

        response = provider.generate(_request())

        self.assertEqual(response.provider, "deepseek")
        self.assertEqual(response.model, "deepseek-chat")
        self.assertIn("TOPIC-001", response.raw_text)
        self.assertEqual(response.metadata["endpoint"], "/chat/completions")
        sent_request = mock_urlopen.call_args.args[0]
        self.assertEqual(sent_request.full_url, "https://api.deepseek.com/chat/completions")
        sent_payload = json.loads(sent_request.data.decode("utf-8"))
        self.assertEqual(sent_payload["response_format"], {"type": "json_object"})
        self.assertEqual(sent_payload["thinking"], {"type": "disabled"})
        self.assertEqual(sent_payload["max_tokens"], 3000)
        self.assertEqual(sent_payload["temperature"], 0.2)
        self.assertFalse(sent_payload["stream"])
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 60.0)
        self.assertEqual(response.metadata["thinking"], {"type": "disabled"})
        self.assertEqual(response.metadata["max_tokens"], 3000)

    def test_markdown_code_fence_json(self) -> None:
        raw_text = "```json\n{\"topics\": []}\n```"

        self.assertEqual(extract_json_text(raw_text), "{\"topics\": []}")

    @patch("app.llm.deepseek_provider.urlopen")
    def test_invalid_provider_json(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _FakeRawHTTPResponse("{not provider json")
        provider = DeepSeekProvider(api_key="secret-key")

        with self.assertRaises(ModelRequestError):
            provider.generate(_request())

    @patch("app.llm.deepseek_provider.urlopen")
    def test_http_error(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = _http_error(500, b'{"error":"server"}')
        provider = DeepSeekProvider(api_key="secret-key")

        with self.assertRaises(ModelRequestError) as raised:
            provider.generate(_request())

        self.assertIn("HTTP 500", str(raised.exception))

    @patch("app.llm.deepseek_provider.urlopen")
    def test_authentication_error(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = _http_error(401, b'{"error":"invalid auth"}')
        provider = DeepSeekProvider(api_key="secret-key")

        with self.assertRaises(ModelAuthenticationError):
            provider.generate(_request())

    @patch("app.llm.deepseek_provider.urlopen")
    def test_timeout(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = URLError(socket.timeout("timed out"))
        provider = DeepSeekProvider(api_key="secret-key")

        with self.assertRaises(ModelTimeoutError):
            provider.generate(_request())

    @patch("app.llm.deepseek_provider.urlopen")
    def test_rate_limit(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = _http_error(429, b'{"error":"too many requests"}')
        provider = DeepSeekProvider(api_key="secret-key")

        with self.assertRaises(ModelRateLimitError):
            provider.generate(_request())

    @patch("app.llm.deepseek_provider.urlopen")
    def test_api_key_not_in_error_output(self, mock_urlopen) -> None:
        secret = "unit-test-secret-value"
        mock_urlopen.side_effect = _http_error(
            500,
            f'{{"error":"Bearer {secret} failed for {secret}"}}'.encode("utf-8"),
        )
        provider = DeepSeekProvider(api_key=secret)

        with self.assertRaises(ModelRequestError) as raised:
            provider.generate(_request())

        self.assertNotIn(secret, str(raised.exception))
        self.assertIn("[REDACTED_SECRET]", str(raised.exception))


class _FakeHTTPResponse:
    def __init__(self, payload: dict, *, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _FakeRawHTTPResponse:
    status = 200

    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body.encode("utf-8")


def _http_error(status: int, body: bytes) -> HTTPError:
    return HTTPError(
        url="https://api.deepseek.com/chat/completions",
        code=status,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


def _request() -> LLMRequest:
    return LLMRequest(system_prompt="system", user_prompt="user", analysis_goal="goal")


if __name__ == "__main__":
    unittest.main()
