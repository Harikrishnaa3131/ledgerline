"""Token pricing for the cost dashboard and the llm_calls table."""
from __future__ import annotations

# USD per million tokens: (input, output), from provider public API pricing pages.
USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.1, 0.5),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "gpt-4o-mini": (0.15, 0.6),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    if model == "fake":
        return 0.0
    version = model.rsplit("-", 1)[-1]
    stable_model = model.rsplit("-", 1)[0] if len(version) == 8 and version.isdigit() else model
    prices = USD_PER_MTOK.get(stable_model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
