"""Budget-aware routing for repair attempts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _coerce_optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _coerce_optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


@dataclass(slots=True)
class BudgetState:
    max_attempts: int
    attempts_used: int
    budget_usd: float | None
    spent_usd: float
    budget_tokens: int | None
    spent_tokens: int


def should_attempt_repair(state: BudgetState, last_event: dict[str, Any]) -> bool:
    if state.attempts_used >= state.max_attempts:
        return False

    cost = last_event.get("cost")
    if not isinstance(cost, dict):
        cost = {}
    meta = cost.get("meta")
    if not isinstance(meta, dict):
        meta = {}

    last_cost_usd = _coerce_optional_float(meta.get("cost_usd")) or 0.0
    last_tokens_in = _coerce_optional_int(cost.get("tokens_in")) or 0
    last_tokens_out = _coerce_optional_int(cost.get("tokens_out")) or 0
    predicted_tokens = last_tokens_in + last_tokens_out

    if state.budget_usd is not None and (state.spent_usd + last_cost_usd) > state.budget_usd:
        return False

    if state.budget_tokens is not None and (state.spent_tokens + predicted_tokens) > state.budget_tokens:
        return False

    return True
