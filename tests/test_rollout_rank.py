from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.runner.rollout_rank import rank_candidates


def _candidate(
    name: str,
    *,
    verdict: str,
    outcome: str,
    violated_constraints: list[str] | None = None,
    reason_codes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "y": name,
        "verifier": {
            "verdict": verdict,
            "outcome": outcome,
            "violated_constraints": violated_constraints,
            "reason_codes": reason_codes,
        },
        "cost": None,
    }


def test_rank_candidates_orders_by_verdict_and_outcome() -> None:
    ranked = rank_candidates(
        [
            _candidate("fail", verdict="FAIL", outcome="FAIL"),
            _candidate("partial", verdict="PARTIAL", outcome="UNKNOWN"),
            _candidate("pass_unknown", verdict="PASS", outcome="UNKNOWN"),
            _candidate("pass_ok", verdict="PASS", outcome="OK"),
        ]
    )

    assert [item["y"] for item in ranked] == ["pass_ok", "pass_unknown", "partial", "fail"]


def test_rank_candidates_tie_breaks_on_constraint_and_reason_counts() -> None:
    ranked = rank_candidates(
        [
            _candidate(
                "more_reasons",
                verdict="PASS",
                outcome="OK",
                violated_constraints=["a"],
                reason_codes=["r1", "r2"],
            ),
            _candidate(
                "more_constraints",
                verdict="PASS",
                outcome="OK",
                violated_constraints=["a", "b"],
                reason_codes=["r1"],
            ),
            _candidate(
                "best_tie",
                verdict="PASS",
                outcome="OK",
                violated_constraints=["a"],
                reason_codes=["r1"],
            ),
        ]
    )

    assert [item["y"] for item in ranked] == ["best_tie", "more_reasons", "more_constraints"]
