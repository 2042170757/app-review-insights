"""Production LLM provider factory."""

from __future__ import annotations

import os

from app.llm.base import LLMProvider, ModelRequestError
from app.llm.deepseek_provider import DeepSeekProvider


LLM_PROVIDER = "LLM_PROVIDER"


def build_production_provider() -> LLMProvider:
    provider = os.environ.get(LLM_PROVIDER, "deepseek").lower()
    if provider != "deepseek":
        raise ModelRequestError(f"Model Request Error: unsupported LLM_PROVIDER={provider!r}")
    return DeepSeekProvider.from_env()
