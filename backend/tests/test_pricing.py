from ledgerline.llm.pricing import cost_usd


def test_known_model_cost_uses_usd_per_million_token_prices():
    assert cost_usd("claude-opus-5-5", 1_000_000, 1_000_000) == 24.0


def test_unknown_model_is_not_reported_as_free():
    assert cost_usd("unknown-model", 1000, 1000) is None


def test_dated_model_alias_uses_its_base_price():
    assert cost_usd("claude-opus-4-5-20251101", 1_000_000, 0) == 5.0
