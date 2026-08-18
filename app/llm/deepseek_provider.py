"""DeepSeek production LLM provider."""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    MissingAPIKeyError,
    ModelAuthenticationError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
)


DEEPSEEK_API_KEY = "DEEPSEEK_API_KEY"
DEEPSEEK_MODEL = "DEEPSEEK_MODEL"
DEEPSEEK_BASE_URL = "DEEPSEEK_BASE_URL"
DEEPSEEK_THINKING = "DEEPSEEK_THINKING"
DEEPSEEK_MAX_TOKENS = "DEEPSEEK_MAX_TOKENS"
DEEPSEEK_TEMPERATURE = "DEEPSEEK_TEMPERATURE"
DEEPSEEK_TIMEOUT = "DEEPSEEK_TIMEOUT"
DEEPSEEK_TIMEOUT_SECONDS = "DEEPSEEK_TIMEOUT_SECONDS"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_THINKING = "disabled"
DEFAULT_MAX_TOKENS = 3000
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TIMEOUT_SECONDS = 60.0
VALID_THINKING_VALUES = {"enabled", "disabled"}


class DeepSeekProvider(LLMProvider):
    provider_name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
        thinking: str = DEFAULT_THINKING,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError(f"Missing API Key: {DEEPSEEK_API_KEY} is not configured.")
        self.api_key = api_key
        self.model = model or DEFAULT_DEEPSEEK_MODEL
        self.base_url = base_url.rstrip("/") or DEFAULT_DEEPSEEK_BASE_URL
        self.thinking = _parse_thinking(thinking)
        self.max_tokens = _validate_positive_int(DEEPSEEK_MAX_TOKENS, max_tokens)
        self.temperature = _validate_temperature(temperature)
        self.timeout_seconds = _validate_positive_float(DEEPSEEK_TIMEOUT, timeout_seconds)

    @classmethod
    def from_env(cls) -> "DeepSeekProvider":
        return cls(
            api_key=os.environ.get(DEEPSEEK_API_KEY, ""),
            model=os.environ.get(DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL),
            base_url=os.environ.get(DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_BASE_URL),
            thinking=os.environ.get(DEEPSEEK_THINKING, DEFAULT_THINKING),
            max_tokens=_parse_int_env(DEEPSEEK_MAX_TOKENS, DEFAULT_MAX_TOKENS),
            temperature=_parse_float_env(DEEPSEEK_TEMPERATURE, DEFAULT_TEMPERATURE),
            timeout_seconds=_parse_timeout_env(),
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        max_tokens = _request_max_tokens(request, self.max_tokens)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        request.system_prompt
                        + "\nReturn a single valid JSON object. Do not wrap it in Markdown."
                    ),
                },
                {"role": "user", "content": request.user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": self.thinking},
            "max_tokens": max_tokens,
            "temperature": self.temperature,
            "stream": False,
        }
        http_request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                status_code = getattr(response, "status", None) or getattr(response, "code", None)
        except TimeoutError as exc:
            raise ModelTimeoutError(f"Timeout: {_sanitize_message(repr(exc), self.api_key)}") from exc
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            message = f"HTTP {exc.code}: {_sanitize_message(error_body[:2000], self.api_key)}"
            if exc.code in {401, 403}:
                raise ModelAuthenticationError(f"Authentication Error: {message}") from exc
            if exc.code == 429:
                raise ModelRateLimitError(f"Rate Limit: {message}") from exc
            raise ModelRequestError(f"Model Request Error: {message}") from exc
        except URLError as exc:
            sanitized = _sanitize_message(repr(exc), self.api_key)
            if "timed out" in sanitized.lower():
                raise ModelTimeoutError(f"Timeout: {sanitized}") from exc
            raise ModelRequestError(f"Model Request Error: {sanitized}") from exc

        try:
            response_payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ModelRequestError(f"Model Request Error: invalid provider JSON: {exc!r}") from exc

        raw_text = _extract_message_content(response_payload)
        if not raw_text:
            raise ModelRequestError("Model Request Error: empty model output text")
        return LLMResponse(
            raw_text=raw_text,
            provider=self.provider_name,
            model=self.model,
            metadata={
                "base_url": self.base_url,
                "endpoint": "/chat/completions",
                "http_status": status_code,
                "thinking": payload["thinking"],
                "max_tokens": max_tokens,
                "default_max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "stream": payload["stream"],
                "timeout_seconds": self.timeout_seconds,
                "response_format": payload["response_format"],
                "provider_response": _redact_provider_response(response_payload),
            },
        )


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _sanitize_message(message: str, api_key: str) -> str:
    sanitized = message.replace(api_key, "[REDACTED_SECRET]") if api_key else message
    return re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED_SECRET]", sanitized)


def _redact_provider_response(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload))


def _request_max_tokens(request: LLMRequest, default: int) -> int:
    options = request.generation_options if isinstance(request.generation_options, dict) else {}
    value = options.get("max_tokens", default)
    return _validate_positive_int("request.max_tokens", value)


def _parse_thinking(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in VALID_THINKING_VALUES:
        raise ModelRequestError(
            f"Model Request Error: {DEEPSEEK_THINKING} must be one of {sorted(VALID_THINKING_VALUES)}"
        )
    return normalized


def _parse_int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ModelRequestError(f"Model Request Error: {name} must be an integer") from exc


def _parse_float_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ModelRequestError(f"Model Request Error: {name} must be a number") from exc


def _parse_timeout_env() -> float:
    if os.environ.get(DEEPSEEK_TIMEOUT) is not None:
        return _parse_float_env(DEEPSEEK_TIMEOUT, DEFAULT_TIMEOUT_SECONDS)
    return _parse_float_env(DEEPSEEK_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS)


def _validate_positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or value <= 0:
        raise ModelRequestError(f"Model Request Error: {name} must be greater than 0")
    return value


def _validate_temperature(value: float) -> float:
    if isinstance(value, bool) or value < 0 or value > 2:
        raise ModelRequestError(f"Model Request Error: {DEEPSEEK_TEMPERATURE} must be between 0 and 2")
    return value


def _validate_positive_float(name: str, value: float) -> float:
    if isinstance(value, bool) or value <= 0:
        raise ModelRequestError(f"Model Request Error: {name} must be greater than 0")
    return value
