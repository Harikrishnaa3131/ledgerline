"""The interface every LLM provider client implements."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class ProviderError(RuntimeError):
    """A provider call failed without exposing request credentials in logs."""


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> LLMResponse: ...
