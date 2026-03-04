"""Offline metrics and aggregation for EventLog JSONL files."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator

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


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


class _RunningStats:
    def __init__(self) -> None:
        self.total_events = 0
        self.pass_count = 0
        self.unknown_count = 0
        self.l1_violation_count = 0
        self.format_leak_count = 0
        self.fail_count = 0
        self.partial_count = 0
        self.error_count = 0
        self.counts_by_verdict: Counter[str] = Counter()
        self.counts_by_outcome: Counter[str] = Counter()
        self.reason_counts: Counter[str] = Counter()
        self.latencies: list[int] = []
        self.tokens_in_total = 0
        self.tokens_out_total = 0
        self.cost_usd_total = 0.0

    def update(self, event: dict[str, Any]) -> None:
        self.total_events += 1

        verifier = event.get("verifier", {})
        verdict = verifier.get("verdict") if isinstance(verifier, dict) else None
        outcome = verifier.get("outcome") if isinstance(verifier, dict) else None

        if isinstance(verdict, str):
            self.counts_by_verdict[verdict] += 1
            if verdict == "FAIL":
                self.fail_count += 1
            if verdict == "PARTIAL":
                self.partial_count += 1

        if isinstance(outcome, str):
            self.counts_by_outcome[outcome] += 1
            if outcome == "UNKNOWN":
                self.unknown_count += 1
            if outcome == "FAIL" and verdict != "FAIL":
                self.fail_count += 1

        pass_value = verifier.get("pass") if isinstance(verifier, dict) else None
        if isinstance(pass_value, int):
            self.pass_count += int(pass_value == 1)
        elif verdict == "PASS" and outcome != "FAIL":
            self.pass_count += 1

        reason_codes = verifier.get("reason_codes") if isinstance(verifier, dict) else None
        if isinstance(reason_codes, list):
            normalized_codes = [code for code in reason_codes if isinstance(code, str) and code]
            self.reason_counts.update(normalized_codes)
            if "format_leak" in normalized_codes:
                self.format_leak_count += 1

        violated_constraints = verifier.get("violated_constraints") if isinstance(verifier, dict) else None
        if isinstance(violated_constraints, list) and any(
            isinstance(constraint, str) and constraint for constraint in violated_constraints
        ):
            self.l1_violation_count += 1

        cost = event.get("cost", {})
        if not isinstance(cost, dict):
            return

        latency_ms = _coerce_optional_int(cost.get("latency_ms"))
        if latency_ms is not None:
            self.latencies.append(latency_ms)

        tokens_in = _coerce_optional_int(cost.get("tokens_in"))
        if tokens_in is not None:
            self.tokens_in_total += tokens_in

        tokens_out = _coerce_optional_int(cost.get("tokens_out"))
        if tokens_out is not None:
            self.tokens_out_total += tokens_out

        meta = cost.get("meta")
        if isinstance(meta, dict):
            if meta.get("error") is not None:
                self.error_count += 1
            cost_usd = _coerce_optional_float(meta.get("cost_usd"))
            if cost_usd is not None:
                self.cost_usd_total += cost_usd

    def to_dict(self) -> dict[str, Any]:
        top_reason_codes = [{"code": code, "count": count} for code, count in self.reason_counts.most_common(10)]
        return {
            "total_events": self.total_events,
            "pass_rate": _safe_rate(self.pass_count, self.total_events),
            "unknown_rate": _safe_rate(self.unknown_count, self.total_events),
            "l1_violation_rate": _safe_rate(self.l1_violation_count, self.total_events),
            "format_leak_rate": _safe_rate(self.format_leak_count, self.total_events),
            "fail_rate": _safe_rate(self.fail_count, self.total_events),
            "partial_rate": _safe_rate(self.partial_count, self.total_events),
            "error_rate": _safe_rate(self.error_count, self.total_events),
            "counts_by_verdict": dict(self.counts_by_verdict),
            "counts_by_outcome": dict(self.counts_by_outcome),
            "top_reason_codes": top_reason_codes,
            "latency_ms_p50": _percentile(self.latencies, 50),
            "latency_ms_p95": _percentile(self.latencies, 95),
            "tokens_in_total": self.tokens_in_total,
            "tokens_out_total": self.tokens_out_total,
            "cost_usd_total": self.cost_usd_total,
        }


def iter_normalized_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return

    with target.open("r", encoding="utf-8") as fp:
        for line in fp:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                yield normalize_eventlog_dict(payload)


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return list(iter_normalized_jsonl(path))


def summarize_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    stats = _RunningStats()
    for event in events:
        stats.update(normalize_eventlog_dict(event))
    return stats.to_dict()


def summarize_jsonl(path: str | Path, group_by: str | None = None) -> dict[str, Any]:
    if group_by is None:
        stats = _RunningStats()
        for event in iter_normalized_jsonl(path):
            stats.update(event)
        return stats.to_dict()

    if group_by != "bucket_key":
        raise ValueError(f"Unsupported group_by value: {group_by!r}")

    overall = _RunningStats()
    grouped: dict[str, _RunningStats] = {}
    for event in iter_normalized_jsonl(path):
        overall.update(event)
        bucket_key = event.get("bucket_key")
        group_key = bucket_key if isinstance(bucket_key, str) else "(null)"
        if group_key not in grouped:
            grouped[group_key] = _RunningStats()
        grouped[group_key].update(event)

    by_bucket_key = {key: grouped[key].to_dict() for key in sorted(grouped)}
    return {"overall": overall.to_dict(), "by_bucket_key": by_bucket_key}
