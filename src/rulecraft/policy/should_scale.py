"""Policy helpers for deciding when test-time scaling should run."""

from __future__ import annotations

from typing import Any, Literal, Mapping

ScaleTier = Literal["off", "probe", "full"]


def _event_verifier(event: Mapping[str, Any]) -> Mapping[str, Any]:
    verifier = event.get("verifier")
    if isinstance(verifier, Mapping):
        return verifier
    return {}


def _event_phase(event: Mapping[str, Any]) -> str | None:
    run = event.get("run")
    if not isinstance(run, Mapping):
        return None

    extra = run.get("extra")
    if not isinstance(extra, Mapping):
        return None

    phase = extra.get("phase")
    if isinstance(phase, str) and phase:
        return phase
    return None


def _event_outcome(event: Mapping[str, Any]) -> str | None:
    outcome = _event_verifier(event).get("outcome")
    if isinstance(outcome, str) and outcome:
        return outcome
    return None


def _event_reason_codes(event: Mapping[str, Any]) -> list[str]:
    reason_codes = _event_verifier(event).get("reason_codes")
    if not isinstance(reason_codes, list):
        return []
    return [code for code in reason_codes if isinstance(code, str) and code]


def _event_is_pass(event: Mapping[str, Any]) -> bool:
    verifier = _event_verifier(event)

    pass_value = verifier.get("pass")
    if isinstance(pass_value, int):
        return pass_value == 1

    verdict = verifier.get("verdict")
    outcome = verifier.get("outcome")
    return verdict == "PASS" and outcome != "FAIL"


def should_scale(events_so_far: list[dict[str, Any]], mode: str) -> ScaleTier:
    """Return a deterministic scaling tier for the current task state."""
    del mode  # Reserved for future mode-specific policy tuning.

    if not events_so_far:
        return "off"

    if any(_event_is_pass(event) for event in events_so_far):
        return "off"

    latest = events_so_far[-1]
    if "format_leak" in _event_reason_codes(latest):
        return "off"

    if any(_event_outcome(event) == "UNKNOWN" for event in events_so_far):
        return "probe"

    fail_or_unknown = sum(1 for event in events_so_far if _event_outcome(event) in {"FAIL", "UNKNOWN"})
    saw_repair = any(_event_phase(event) == "repair" for event in events_so_far)
    if saw_repair and fail_or_unknown >= 2:
        return "probe"

    return "off"


def escalate_to_full(probe_event: dict[str, Any], budget_ok: bool) -> bool:
    """Escalate from probe to full only for non-pass probe results with budget headroom."""
    if not budget_ok:
        return False
    return not _event_is_pass(probe_event)


__all__ = ["ScaleTier", "should_scale", "escalate_to_full"]
