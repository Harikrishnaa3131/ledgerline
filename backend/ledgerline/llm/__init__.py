"""LLM provider clients."""
from __future__ import annotations

from ..config import get_settings
from .base import LLMClient, LLMResponse, ProviderError

__all__ = ["LLMClient", "LLMResponse", "ProviderError", "get_client"]


def get_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not configured")
        from .anthropic_client import AnthropicClient

        return AnthropicClient(settings.anthropic_api_key, settings.llm_model)
    if settings.llm_provider == "openai_compat":
        from .openai_compat import OpenAICompatClient

        return OpenAICompatClient(settings.openai_base_url, settings.openai_api_key, settings.llm_model)
    if settings.llm_provider == "fake":
        from .fake import FakeClient

        return FakeClient()
    raise ValueError(f"Unknown LLM_PROVIDER {settings.llm_provider!r}")
