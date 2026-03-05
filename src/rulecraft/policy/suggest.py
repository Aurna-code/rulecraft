"""Suggest conservative policy profile overrides from EventLog analytics."""

from __future__ import annotations

from typing import Any, Mapping

from ..analysis.flowmap import analyze_flowmap
from ..metrics.eventlog_metrics import summarize_jsonl

_HIGH_REPAIR_GAIN = 0.25
_LOW_REPAIR_COST_USD = 0.05
_HIGH_UNKNOWN_RATE = 0.30
_LOW_FORMAT_LEAK_RATE = 0.15
_HIGH_SCHEMA_VIOLATION_RATE = 0.20
_LOW_FULL_GAIN = 0.05
_VERY_LOW_FULL_GAIN = 0.01
_HIGH_FULL_COST_USD = 0.25
_VERY_HIGH_FULL_COST_USD = 0.50
_K_FULL_CAP = 4


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _bucket_specificity(bucket_key: str) -> tuple[int, int, str]:
    return (bucket_key.count("."), len(bucket_key), bucket_key)


def _event_metrics_for_bucket(metrics_group: Mapping[str, Any]) -> Mapping[str, Any]:
    event_metrics = metrics_group.get("event_metrics")
    if isinstance(event_metrics, Mapping):
        return event_metrics
    return metrics_group


def _suggest_bucket_overrides(
    risk: Mapping[str, Any],
    opportunity: Mapping[str, Any],
    event_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    overrides: dict[str, Any] = {}

    unknown_rate = _as_float(risk.get("unknown_rate")) or 0.0
    repair_gain = _as_float(opportunity.get("repair_gain")) or 0.0
    full_gain = _as_float(opportunity.get("full_gain")) or 0.0
    format_leak_rate = _as_float(event_metrics.get("format_leak_rate")) or 0.0
    schema_violation_rate = _as_float(event_metrics.get("schema_violation_rate")) or 0.0

    avg_costs = opportunity.get("avg_cost_usd_by_phase")
    avg_costs_map = avg_costs if isinstance(avg_costs, Mapping) else {}
    repair_cost = _as_float(avg_costs_map.get("repair"))
    full_cost = _as_float(avg_costs_map.get("scale_full"))

    if schema_violation_rate >= _HIGH_SCHEMA_VIOLATION_RATE:
        overrides["max_attempts"] = max(int(overrides.get("max_attempts", 1)), 2)
        overrides["synth"] = True

    if repair_gain >= _HIGH_REPAIR_GAIN and (repair_cost is None or repair_cost <= _LOW_REPAIR_COST_USD):
        current_attempts = int(overrides.get("max_attempts", 1))
        overrides["max_attempts"] = min(max(current_attempts, 1) + 1, 3)

    if unknown_rate >= _HIGH_UNKNOWN_RATE and format_leak_rate <= _LOW_FORMAT_LEAK_RATE:
        overrides["scale"] = "auto"
        overrides.setdefault("k_probe", 3)
        overrides.setdefault("top_m", 2)
        overrides.setdefault("synth", True)

    if full_cost is not None:
        if full_gain <= _VERY_LOW_FULL_GAIN or full_cost >= _VERY_HIGH_FULL_COST_USD:
            overrides["scale"] = "probe" if unknown_rate >= _HIGH_UNKNOWN_RATE else "off"
            overrides["k_full"] = 2
        elif full_gain <= _LOW_FULL_GAIN or full_cost >= _HIGH_FULL_COST_USD:
            if overrides.get("scale") == "full":
                overrides["scale"] = "probe"
            elif "scale" not in overrides and unknown_rate < _HIGH_UNKNOWN_RATE:
                overrides["scale"] = "probe"
            current_k_full = int(overrides.get("k_full", _K_FULL_CAP))
            overrides["k_full"] = min(current_k_full, _K_FULL_CAP)

    return overrides


def suggest_policy(eventlog_path: str, group_by: str = "bucket_key") -> dict[str, Any]:
    """Generate a conservative policy profile from EventLog analytics."""
    if group_by != "bucket_key":
        raise ValueError(f"Unsupported group_by value: {group_by!r}")

    flowmap = analyze_flowmap(eventlog_path, group_by=group_by)
    metrics = summarize_jsonl(eventlog_path, group_by=group_by)

    risk_map = flowmap.get("risk_map")
    opportunity_map = flowmap.get("opportunity_map")
    grouped_metrics = metrics.get("by_bucket_key") if isinstance(metrics, Mapping) else None
    if not isinstance(risk_map, Mapping) or not isinstance(opportunity_map, Mapping):
        return {"version": 1, "rules": []}
    if not isinstance(grouped_metrics, Mapping):
        grouped_metrics = {}

    candidate_buckets: set[str] = set()
    for key in risk_map.keys():
        if isinstance(key, str) and key:
            candidate_buckets.add(key)
    for key in opportunity_map.keys():
        if isinstance(key, str) and key:
            candidate_buckets.add(key)

    ordered_buckets = sorted(
        (bucket for bucket in candidate_buckets if bucket != "(null)"),
        key=_bucket_specificity,
        reverse=True,
    )

    rules: list[dict[str, Any]] = []
    for bucket in ordered_buckets:
        risk = risk_map.get(bucket)
        opportunity = opportunity_map.get(bucket)
        metrics_for_bucket = grouped_metrics.get(bucket, {})
        if not isinstance(risk, Mapping) or not isinstance(opportunity, Mapping):
            continue
        if not isinstance(metrics_for_bucket, Mapping):
            metrics_for_bucket = {}
        event_metrics = _event_metrics_for_bucket(metrics_for_bucket)
        overrides = _suggest_bucket_overrides(risk, opportunity, event_metrics)
        if not overrides:
            continue
        rules.append({"bucket_match": bucket, "overrides": overrides})

    return {"version": 1, "rules": rules}


__all__ = ["suggest_policy"]
