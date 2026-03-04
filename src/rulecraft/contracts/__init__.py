"""Rulecraft contracts package."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, TypeVar

from .normalize import normalize_eventlog_dict
from .ssot import SCHEMA_VERSION
from .types import EventLog, VerifierResult, pass_from

PolicyVerdict = Literal["PASS", "FAIL", "PARTIAL"]
ExecutionOutcome = Literal["OK", "FAIL", "UNKNOWN"]

T = TypeVar("T")


@dataclass(slots=True)
class ValidationResult:
    schema_version: str = SCHEMA_VERSION
    validator_id: str = ""
    verdict: PolicyVerdict = "PARTIAL"
    outcome: ExecutionOutcome = "UNKNOWN"
    score: float | None = None
    score_method: str | None = None
    reason_codes: list[str] | None = None
    violated_constraints: list[str] | None = None
    score_evidence: dict[str, Any] | None = None
    fgfc: dict[str, Any] | None = None
    scores: dict[str, Any] | None = None
    failure_cluster_id: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidationResult":
        return from_dict(cls, data)


@dataclass(slots=True)
class RunLog:
    schema_version: str = SCHEMA_VERSION
    run_id: str = ""
    input_ref: str = ""
    bucket_id: str | None = None
    run_tags: list[str] | None = None
    control_signals: dict[str, Any] | None = None
    applied_rules: list[dict[str, Any]] = field(default_factory=list)
    run: dict[str, Any] = field(default_factory=dict)
    exec: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    validator: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] | None = None
    context_select: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunLog":
        return from_dict(cls, data)


@dataclass(slots=True)
class TraceBundle:
    """Trace refs only. Never store raw source text or direct PII/secrets."""

    schema_version: str = SCHEMA_VERSION
    run_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    bucket_id: str | None = None
    intent_key: str | None = None
    state_key: str | None = None
    refs: dict[str, Any] | None = None
    used_memory_ids: list[str] | None = None
    used_rule_ids: list[str] | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TraceBundle":
        return from_dict(cls, data)


def is_pass(vr: ValidationResult | VerifierResult | Mapping[str, Any]) -> bool:
    return pass_from(vr) == 1


def is_confirmed_pass(vr: ValidationResult | VerifierResult | Mapping[str, Any]) -> bool:
    if isinstance(vr, Mapping):
        verdict = vr.get("verdict")
        outcome = vr.get("outcome")
        return verdict == "PASS" and outcome == "OK"
    return getattr(vr, "verdict", None) == "PASS" and getattr(vr, "outcome", None) == "OK"


def to_dict(obj: Any) -> dict[str, Any]:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, Mapping):
        return dict(obj)
    raise TypeError(f"Unsupported type for to_dict: {type(obj)!r}")


def from_dict(cls: type[T], data: Mapping[str, Any]) -> T:
    if not is_dataclass(cls):
        raise TypeError(f"from_dict target must be dataclass type, got: {cls!r}")

    normalized = dict(data)

    if cls.__name__ == "TraceBundle":
        refs = dict(normalized.get("refs") or {})
        if "input_ref" in normalized and "input_ref" not in refs:
            refs["input_ref"] = normalized["input_ref"]
        if "output_ref" in normalized and "output_ref" not in refs:
            refs["output_ref"] = normalized["output_ref"]
        if refs:
            normalized["refs"] = refs

    dataclass_fields = {f.name for f in fields(cls)}
    kwargs = {k: v for k, v in normalized.items() if k in dataclass_fields}
    return cls(**kwargs)  # type: ignore[arg-type]


__all__ = [
    "SCHEMA_VERSION",
    "PolicyVerdict",
    "ExecutionOutcome",
    "VerifierResult",
    "EventLog",
    "ValidationResult",
    "RunLog",
    "TraceBundle",
    "pass_from",
    "normalize_eventlog_dict",
    "is_pass",
    "is_confirmed_pass",
    "to_dict",
    "from_dict",
]
