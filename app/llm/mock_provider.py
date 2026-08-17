"""Mock LLM provider used by tests and offline diagnostics."""

from __future__ import annotations

from app.llm.base import LLMProvider, LLMRequest, LLMResponse


class MockLLMProvider(LLMProvider):
    provider_name = "mock"

    def __init__(self, raw_text: str, *, model: str = "mock-topic-model") -> None:
        self.raw_text = raw_text
        self.model = model
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(raw_text=self.raw_text, provider=self.provider_name, model=self.model)

