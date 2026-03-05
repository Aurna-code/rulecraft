"""Normalization helpers for EventLog records."""

from __future__ import annotations

from typing import Any, Mapping

from .ssot import SCHEMA_VERSION
from ..verifier.taxonomy import COST_META_COERCED

_DEFAULT_VERIFIER_ID = "vf_l1_v1"
_UNKNOWN_RULE_TYPE = "UnknownRule"
_COST_NUMERIC_FIELDS = ("latency_ms", "tokens_in", "tokens_out", "tool_calls")
_COST_META_FIELDS = ("backend", "model", "cost_usd", "error", "response_id")
_CANONICAL_TOP_LEVEL_KEYS = {
    "schema_version",
    "trace_id",
    "x_ref",
    "bucket_key",
    "flow_tags",
    "selected_rules",
    "run",
    "outputs",
    "verifier",
    "cost",
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
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped.lstrip("-").isdigit():
            return int(stripped)
    return None


def _coerce_optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _coerce_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None

    values = [item for item in value if isinstance(item, str) and item]
    if not values:
        return None
    return values


def _normalize_selected_rules(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str) and item:
            normalized.append(
                {
                    "rule_id": item,
                    "version": "legacy",
                    "type": _UNKNOWN_RULE_TYPE,
                }
            )
            continue
        if isinstance(item, Mapping):
            rule_id = str(item.get("rule_id", "")) if item.get("rule_id") is not None else ""
            version = str(item.get("version", SCHEMA_VERSION)) if item.get("version") is not None else SCHEMA_VERSION
            rule_type = str(item.get("type", _UNKNOWN_RULE_TYPE)) if item.get("type") is not None else _UNKNOWN_RULE_TYPE
            normalized.append(
                {
                    "rule_id": rule_id,
                    "version": version,
                    "type": rule_type,
                }
            )
    return normalized


def _append_reason_code(verifier: dict[str, Any], reason_code: str) -> None:
    reason_codes = verifier.get("reason_codes")
    if isinstance(reason_codes, list):
        normalized_codes = [code for code in reason_codes if isinstance(code, str) and code]
    else:
        normalized_codes = []

    if reason_code not in normalized_codes:
        normalized_codes.append(reason_code)
    verifier["reason_codes"] = normalized_codes


def _normalize_verifier(raw: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    verifier = dict(raw)
    top_verdict = event.get("verdict")
    top_outcome = event.get("outcome")

    verdict = verifier.get("verdict") if isinstance(verifier.get("verdict"), str) else None
    outcome = verifier.get("outcome") if isinstance(verifier.get("outcome"), str) else None

    if verdict is None and isinstance(top_verdict, str):
        verdict = top_verdict
    if outcome is None and isinstance(top_outcome, str):
        outcome = top_outcome

    verdict = verdict or "PARTIAL"
    outcome = outcome or "UNKNOWN"

    verifier_id = verifier.get("verifier_id")
    if not isinstance(verifier_id, str) or not verifier_id:
        legacy_validator_id = verifier.get("validator_id")
        if isinstance(legacy_validator_id, str) and legacy_validator_id:
            verifier_id = legacy_validator_id
        else:
            verifier_id = _DEFAULT_VERIFIER_ID

    pass_value = verifier.get("pass")
    if isinstance(pass_value, bool):
        pass_value = int(pass_value)
    elif not isinstance(pass_value, int):
        pass_value = int(verdict == "PASS" and outcome != "FAIL")

    reason_codes = _coerce_string_list(verifier.get("reason_codes"))
    violated_constraints = _coerce_string_list(verifier.get("violated_constraints"))

    normalized: dict[str, Any] = {
        "verifier_id": verifier_id,
        "verdict": verdict,
        "outcome": outcome,
        "reason_codes": reason_codes,
        "violated_constraints": violated_constraints,
        "pass": pass_value,
    }

    for key, value in verifier.items():
        if key in normalized or key == "validator_id":
            continue
        normalized[key] = value

    return normalized


def _normalize_cost(raw: Mapping[str, Any], event: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    raw_cost = dict(raw)
    raw_meta = raw_cost.get("meta")
    meta_coerced = False
    if isinstance(raw_meta, Mapping):
        meta: dict[str, Any] = dict(raw_meta)
    elif raw_meta is None:
        meta = {}
    else:
        meta = {"_raw": str(raw_meta)}
        meta_coerced = True

    for key in _COST_META_FIELDS:
        if key in raw_cost and key != "meta":
            meta[key] = raw_cost[key]
        elif key in event:
            meta[key] = event[key]

    for key, value in raw_cost.items():
        if key in _COST_NUMERIC_FIELDS or key == "meta":
            continue
        meta[key] = value

    normalized: dict[str, Any] = {
        "latency_ms": _coerce_optional_int(raw_cost.get("latency_ms", event.get("latency_ms"))),
        "tokens_in": _coerce_optional_int(raw_cost.get("tokens_in", event.get("tokens_in"))),
        "tokens_out": _coerce_optional_int(raw_cost.get("tokens_out", event.get("tokens_out"))),
        "tool_calls": _coerce_optional_int(raw_cost.get("tool_calls", event.get("tool_calls"))),
        "meta": meta or None,
    }
    return normalized, meta_coerced


def _normalize_run_with_extra(run_value: Any, event: Mapping[str, Any]) -> dict[str, Any] | None:
    run: dict[str, Any]
    if isinstance(run_value, Mapping):
        run = dict(run_value)
    else:
        run = {}

    legacy_extra: dict[str, Any] = {}
    for key, value in event.items():
        if key not in _CANONICAL_TOP_LEVEL_KEYS:
            legacy_extra[key] = value

    run_extra_raw = run.get("extra")
    if isinstance(run_extra_raw, Mapping):
        run_extra = dict(run_extra_raw)
    elif run_extra_raw is None:
        run_extra = {}
    else:
        run_extra = {"_raw": str(run_extra_raw)}

    if legacy_extra:
        run_extra.update(legacy_extra)

    if run_extra:
        run["extra"] = run_extra
    elif "extra" in run:
        del run["extra"]

    if not run:
        return None
    return run


def normalize_eventlog_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Convert mixed EventLog shapes into the canonical schema."""
    event = dict(d)
    verifier_raw = event.get("verifier")
    cost_raw = event.get("cost")

    verifier_map = verifier_raw if isinstance(verifier_raw, Mapping) else {}
    cost_map = cost_raw if isinstance(cost_raw, Mapping) else {}

    bucket_key = _coerce_optional_str(event.get("bucket_key"))
    if bucket_key is None:
        bucket_key = _coerce_optional_str(event.get("bucket_id"))

    flow_tags = _coerce_string_list(event.get("flow_tags"))
    if flow_tags is None:
        flow_tags = _coerce_string_list(event.get("run_tags"))

    run = event.get("run")
    outputs = event.get("outputs")
    normalized_verifier = _normalize_verifier(verifier_map, event)
    normalized_cost, cost_meta_coerced = _normalize_cost(cost_map, event)
    if cost_meta_coerced:
        _append_reason_code(normalized_verifier, COST_META_COERCED)

    normalized: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "trace_id": str(event.get("trace_id", "")),
        "x_ref": str(event.get("x_ref", "")),
        "bucket_key": bucket_key,
        "flow_tags": flow_tags,
        "selected_rules": _normalize_selected_rules(event.get("selected_rules")),
        "run": _normalize_run_with_extra(run, event),
        "outputs": dict(outputs) if isinstance(outputs, Mapping) else None,
        "verifier": normalized_verifier,
        "cost": normalized_cost,
    }
    return normalized
