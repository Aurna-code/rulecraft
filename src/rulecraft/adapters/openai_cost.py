"""Static cost estimation for OpenAI models."""

from __future__ import annotations

from typing import Any

# USD per million tokens. Update this table as provider pricing changes.
OPENAI_PRICING_PER_MILLION: dict[str, dict[str, float]] = {
    "gpt-5": {"input": 1.25, "output": 10.0},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
}


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _pricing_for_model(model: str) -> dict[str, float] | None:
    if model in OPENAI_PRICING_PER_MILLION:
        return OPENAI_PRICING_PER_MILLION[model]

    for prefix, prices in OPENAI_PRICING_PER_MILLION.items():
        if model.startswith(prefix):
            return prices
    return None


def estimate_openai_cost_usd(model: str, tokens_in: Any, tokens_out: Any) -> float | None:
    prices = _pricing_for_model(model)
    in_count = _coerce_optional_int(tokens_in)
    out_count = _coerce_optional_int(tokens_out)
    if prices is None or in_count is None or out_count is None:
        return None

    input_cost = in_count * prices["input"]
    output_cost = out_count * prices["output"]
    return (input_cost + output_cost) / 1_000_000
