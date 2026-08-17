"""Shared LLM provider protocol and result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMRequest:
    system_prompt: str
    user_prompt: str
    analysis_goal: str


@dataclass(frozen=True)
class LLMResponse:
    raw_text: str
    provider: str
    model: str | None = None


class LLMProvider(Protocol):
    provider_name: str

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate raw model output for a structured analysis request."""


class MissingAPIKeyError(RuntimeError):
    """Raised when a production LLM provider lacks required credentials."""


class ModelRequestError(RuntimeError):
    """Raised when the model request fails."""


class ModelTimeoutError(ModelRequestError):
    """Raised when the model request times out."""

