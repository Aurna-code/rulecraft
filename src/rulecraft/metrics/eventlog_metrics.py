"""Offline metrics and aggregation for EventLog JSONL files."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from ..contracts import normalize_eventlog_dict


def _coerce_optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _coerce_optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None

    ordered = sorted(values)
    rank = max(math.ceil((p / 100) * len(ordered)), 1)
    return ordered[rank - 1]


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []

    events: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as fp:
        for line in fp:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                events.append(normalize_eventlog_dict(payload))
    return events


def summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_eventlog_dict(event) for event in events]
    total_events = len(normalized)

    pass_count = 0
    unknown_count = 0
    counts_by_verdict: Counter[str] = Counter()
    counts_by_outcome: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    latencies: list[int] = []
    tokens_in_total = 0
    tokens_out_total = 0
    cost_usd_total = 0.0

    for event in normalized:
        verifier = event.get("verifier", {})
        verdict = verifier.get("verdict") if isinstance(verifier, dict) else None
        outcome = verifier.get("outcome") if isinstance(verifier, dict) else None

        if isinstance(verdict, str):
            counts_by_verdict[verdict] += 1
        if isinstance(outcome, str):
            counts_by_outcome[outcome] += 1
            if outcome == "UNKNOWN":
                unknown_count += 1

        pass_value = verifier.get("pass") if isinstance(verifier, dict) else None
        if isinstance(pass_value, int):
            pass_count += int(pass_value == 1)
        elif verdict == "PASS" and outcome != "FAIL":
            pass_count += 1

        reason_codes = verifier.get("reason_codes") if isinstance(verifier, dict) else None
        if isinstance(reason_codes, list):
            reason_counts.update(code for code in reason_codes if isinstance(code, str) and code)

        cost = event.get("cost", {})
        if not isinstance(cost, dict):
            continue

        latency_ms = _coerce_optional_int(cost.get("latency_ms"))
        if latency_ms is not None:
            latencies.append(latency_ms)

        tokens_in = _coerce_optional_int(cost.get("tokens_in"))
        if tokens_in is not None:
            tokens_in_total += tokens_in

        tokens_out = _coerce_optional_int(cost.get("tokens_out"))
        if tokens_out is not None:
            tokens_out_total += tokens_out

        meta = cost.get("meta")
        if isinstance(meta, dict):
            cost_usd = _coerce_optional_float(meta.get("cost_usd"))
            if cost_usd is not None:
                cost_usd_total += cost_usd

    top_reason_codes = [
        {"code": code, "count": count}
        for code, count in reason_counts.most_common(10)
    ]

    return {
        "total_events": total_events,
        "pass_rate": (pass_count / total_events) if total_events else 0.0,
        "unknown_rate": (unknown_count / total_events) if total_events else 0.0,
        "counts_by_verdict": dict(counts_by_verdict),
        "counts_by_outcome": dict(counts_by_outcome),
        "top_reason_codes": top_reason_codes,
        "latency_ms_p50": _percentile(latencies, 50),
        "latency_ms_p95": _percentile(latencies, 95),
        "tokens_in_total": tokens_in_total,
        "tokens_out_total": tokens_out_total,
        "cost_usd_total": cost_usd_total,
    }


def summarize_jsonl(path: str | Path) -> dict[str, Any]:
    return summarize_events(load_jsonl(path))

