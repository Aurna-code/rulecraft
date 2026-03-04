from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.policy.budget_router import BudgetState, should_attempt_repair


def test_should_attempt_repair_obeys_max_attempts() -> None:
    state = BudgetState(
        max_attempts=2,
        attempts_used=2,
        budget_usd=None,
        spent_usd=0.0,
        budget_tokens=None,
        spent_tokens=0,
    )
    assert (
        should_attempt_repair(
            state,
            {"cost": {"tokens_in": 10, "tokens_out": 10, "meta": {"cost_usd": 0.1}}},
        )
        is False
    )


def test_should_attempt_repair_obeys_cost_and_token_budgets() -> None:
    state = BudgetState(
        max_attempts=3,
        attempts_used=1,
        budget_usd=0.05,
        spent_usd=0.04,
        budget_tokens=20,
        spent_tokens=15,
    )
    last_event = {
        "cost": {
            "tokens_in": 3,
            "tokens_out": 5,
            "meta": {"cost_usd": 0.02},
        }
    }
    assert should_attempt_repair(state, last_event) is False
