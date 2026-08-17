"""Production LLM provider factory and OpenAI implementation."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    MissingAPIKeyError,
    ModelRequestError,
    ModelTimeoutError,
)
from app.topic_schema import TOPIC_DISCOVERY_JSON_SCHEMA


OPENAI_API_KEY = "OPENAI_API_KEY"
OPENAI_MODEL = "OPENAI_MODEL"
LLM_PROVIDER = "LLM_PROVIDER"
LLM_TIMEOUT_SECONDS = "LLM_TIMEOUT_SECONDS"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"


class OpenAIResponsesProvider(LLMProvider):
    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_OPENAI_MODEL,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError("Missing API Key: OPENAI_API_KEY is not configured.")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "OpenAIResponsesProvider":
        return cls(
            api_key=os.environ.get(OPENAI_API_KEY, ""),
            model=os.environ.get(OPENAI_MODEL, DEFAULT_OPENAI_MODEL),
            timeout_seconds=float(os.environ.get(LLM_TIMEOUT_SECONDS, "60")),
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "topic_discovery_result",
                    "schema": TOPIC_DISCOVERY_JSON_SCHEMA,
                    "strict": True,
                }
            },
        }
        http_request = Request(
            "https://api.openai.com/v1/responses",
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
        except TimeoutError as exc:
            raise ModelTimeoutError(f"Timeout: {exc!r}") from exc
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ModelRequestError(
                f"Model Request Failed: HTTP {exc.code}: {error_body[:2000]}"
            ) from exc
        except URLError as exc:
            if "timed out" in repr(exc).lower():
                raise ModelTimeoutError(f"Timeout: {exc!r}") from exc
            raise ModelRequestError(f"Model Request Failed: {exc!r}") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ModelRequestError(f"Model Request Failed: invalid provider JSON: {exc!r}") from exc

        raw_text = _extract_output_text(payload)
        if not raw_text:
            raise ModelRequestError("Model Request Failed: empty model output text")
        return LLMResponse(raw_text=raw_text, provider=self.provider_name, model=self.model)


def build_production_provider() -> LLMProvider:
    provider = os.environ.get(LLM_PROVIDER, "openai").lower()
    if provider != "openai":
        raise ModelRequestError(f"Model Request Failed: unsupported LLM_PROVIDER={provider!r}")
    return OpenAIResponsesProvider.from_env()


def _extract_output_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text
    chunks: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "".join(chunks)

