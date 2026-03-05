from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.policy.should_scale import escalate_to_full, should_scale


def _event(
    *,
    verdict: str,
    outcome: str,
    phase: str = "primary",
    reason_codes: list[str] | None = None,
    pass_value: int | None = None,
) -> dict[str, Any]:
    if pass_value is None:
        pass_value = int(verdict == "PASS" and outcome != "FAIL")
    return {
        "run": {"extra": {"phase": phase}},
        "verifier": {
            "verdict": verdict,
            "outcome": outcome,
            "reason_codes": reason_codes,
            "violated_constraints": None,
            "pass": pass_value,
        },
    }


def test_should_scale_returns_off_if_any_attempt_passed() -> None:
    events = [
        _event(verdict="FAIL", outcome="UNKNOWN"),
        _event(verdict="PASS", outcome="OK"),
    ]
    assert should_scale(events, mode="json") == "off"


def test_should_scale_returns_off_for_format_leak_failures() -> None:
    events = [_event(verdict="FAIL", outcome="UNKNOWN", reason_codes=["format_leak"])]
    assert should_scale(events, mode="json") == "off"


def test_should_scale_returns_probe_for_unknown_outcome() -> None:
    events = [_event(verdict="FAIL", outcome="UNKNOWN", reason_codes=["semantic_miss"])]
    assert should_scale(events, mode="text") == "probe"


def test_should_scale_returns_probe_for_repeated_fail_after_repair() -> None:
    events = [
        _event(verdict="FAIL", outcome="FAIL", phase="primary", reason_codes=["semantic_miss"]),
        _event(verdict="FAIL", outcome="FAIL", phase="repair", reason_codes=["constraint_miss"]),
    ]
    assert should_scale(events, mode="text") == "probe"


def test_should_scale_is_deterministic() -> None:
    events = [
        _event(verdict="FAIL", outcome="FAIL", phase="primary", reason_codes=["semantic_miss"]),
    ]
    assert should_scale(events, mode="text") == "off"
    assert should_scale(events, mode="text") == "off"


def test_escalate_to_full_requires_non_pass_probe_and_budget() -> None:
    passing_probe = _event(verdict="PASS", outcome="OK")
    failing_probe = _event(verdict="FAIL", outcome="UNKNOWN")

    assert escalate_to_full(passing_probe, budget_ok=True) is False
    assert escalate_to_full(failing_probe, budget_ok=False) is False
    assert escalate_to_full(failing_probe, budget_ok=True) is True
