"""Minimal SSOT-aligned contract types."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .ssot import SCHEMA_VERSION


@dataclass(slots=True)
class VerifierResult:
    verdict: str
    outcome: str
    reason_codes: list[str] | None = None
    violated_constraints: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VerifierResult":
        reason_codes = data.get("reason_codes")
        violated_constraints = data.get("violated_constraints")
        return cls(
            verdict=str(data.get("verdict", "")),
            outcome=str(data.get("outcome", "")),
            reason_codes=list(reason_codes) if isinstance(reason_codes, list) else None,
            violated_constraints=list(violated_constraints) if isinstance(violated_constraints, list) else None,
        )


@dataclass(slots=True)
class EventLog:
    schema_version: str = SCHEMA_VERSION
    trace_id: str = ""
    x_ref: str = ""
    selected_rules: list[Any] = field(default_factory=list)
    verifier: VerifierResult | dict[str, Any] = field(default_factory=dict)
    verdict: str | None = None
    outcome: str | None = None
    cost: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if isinstance(self.verifier, dict):
            payload["verifier"] = dict(self.verifier)
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EventLog":
        verifier_data = data.get("verifier", {})
        verifier: VerifierResult | dict[str, Any]
        if isinstance(verifier_data, VerifierResult):
            verifier = verifier_data
        elif isinstance(verifier_data, Mapping):
            if "verdict" in verifier_data and "outcome" in verifier_data:
                verifier = VerifierResult.from_dict(verifier_data)
            else:
                verifier = dict(verifier_data)
        else:
            verifier = {}

        selected_rules = data.get("selected_rules")
        if not isinstance(selected_rules, list):
            selected_rules = []

        cost = data.get("cost")
        if not isinstance(cost, Mapping):
            cost = {}

        return cls(
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            trace_id=str(data.get("trace_id", "")),
            x_ref=str(data.get("x_ref", "")),
            selected_rules=selected_rules,
            verifier=verifier,
            verdict=str(data.get("verdict")) if isinstance(data.get("verdict"), str) else None,
            outcome=str(data.get("outcome")) if isinstance(data.get("outcome"), str) else None,
            cost=dict(cost),
        )


def _extract_verdict_outcome(verifier_result: Any) -> tuple[str | None, str | None]:
    if isinstance(verifier_result, VerifierResult):
        return verifier_result.verdict, verifier_result.outcome

    if isinstance(verifier_result, Mapping):
        verdict = verifier_result.get("verdict")
        outcome = verifier_result.get("outcome")
        return (
            str(verdict) if isinstance(verdict, str) else None,
            str(outcome) if isinstance(outcome, str) else None,
        )

    verdict = getattr(verifier_result, "verdict", None)
    outcome = getattr(verifier_result, "outcome", None)
    return (
        str(verdict) if isinstance(verdict, str) else None,
        str(outcome) if isinstance(outcome, str) else None,
    )


def pass_from(verifier_result: Any) -> int:
    verdict, outcome = _extract_verdict_outcome(verifier_result)
    return int(verdict == "PASS" and outcome != "FAIL")
