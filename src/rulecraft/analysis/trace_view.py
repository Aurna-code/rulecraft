"""Per-task trace rendering from EventLog JSONL."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..metrics.eventlog_metrics import iter_normalized_jsonl

_PHASE_ORDER = {
    "primary": 0,
    "repair": 1,
    "scale_probe": 2,
    "scale_full": 3,
}


def _extract_task_id(event: Mapping[str, Any]) -> str | None:
    run = event.get("run")
    if not isinstance(run, Mapping):
        return None
    extra = run.get("extra")
    if isinstance(extra, Mapping):
        task_id = extra.get("task_id")
        if isinstance(task_id, str) and task_id:
            return task_id
    task_id = run.get("task_id")
    if isinstance(task_id, str) and task_id:
        return task_id
    return None


def _extract_attempt_idx(event: Mapping[str, Any]) -> int:
    run = event.get("run")
    if not isinstance(run, Mapping):
        return 10_000
    extra = run.get("extra")
    if not isinstance(extra, Mapping):
        return 10_000
    raw = extra.get("attempt_idx")
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    return 10_000


def _extract_phase(event: Mapping[str, Any]) -> str:
    run = event.get("run")
    if not isinstance(run, Mapping):
        return "unknown"
    extra = run.get("extra")
    if not isinstance(extra, Mapping):
        return "unknown"
    phase = extra.get("phase")
    if isinstance(phase, str) and phase:
        return phase
    return "unknown"


def _list_text(value: Any) -> str:
    if not isinstance(value, list):
        return "-"
    normalized = [str(item) for item in value if isinstance(item, str) and item]
    if not normalized:
        return "-"
    return ",".join(normalized)


def _rule_ids(value: Any) -> str:
    if not isinstance(value, list):
        return "-"
    rule_ids: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        rule_id = item.get("rule_id")
        if isinstance(rule_id, str) and rule_id:
            rule_ids.append(rule_id)
    if not rule_ids:
        return "-"
    return ",".join(rule_ids)


def _cost_text(event: Mapping[str, Any]) -> str:
    cost = event.get("cost")
    if not isinstance(cost, Mapping):
        return "-"

    fields: list[str] = []
    latency_ms = cost.get("latency_ms")
    if isinstance(latency_ms, bool):
        fields.append(f"latency_ms={int(latency_ms)}")
    elif isinstance(latency_ms, int):
        fields.append(f"latency_ms={latency_ms}")

    tokens_in = cost.get("tokens_in")
    tokens_out = cost.get("tokens_out")
    in_value: int | None
    out_value: int | None
    if isinstance(tokens_in, bool):
        in_value = int(tokens_in)
    elif isinstance(tokens_in, int):
        in_value = tokens_in
    else:
        in_value = None
    if isinstance(tokens_out, bool):
        out_value = int(tokens_out)
    elif isinstance(tokens_out, int):
        out_value = tokens_out
    else:
        out_value = None
    if in_value is not None or out_value is not None:
        fields.append(f"tokens={in_value or 0}/{out_value or 0}")

    meta = cost.get("meta")
    if isinstance(meta, Mapping):
        cost_usd = meta.get("cost_usd")
        if isinstance(cost_usd, bool):
            fields.append(f"cost_usd={float(int(cost_usd)):.6f}")
        elif isinstance(cost_usd, (int, float)):
            fields.append(f"cost_usd={float(cost_usd):.6f}")

    if not fields:
        return "-"
    return " ".join(fields)


def render_task_trace(eventlog_path: str, task_id: str) -> str:
    """Render a compact, human-readable timeline for one task id."""
    source = Path(eventlog_path).resolve()
    task = str(task_id)

    timeline: list[dict[str, Any]] = []
    for event in iter_normalized_jsonl(source):
        if _extract_task_id(event) != task:
            continue
        timeline.append(dict(event))

    lines = [
        f"Task Trace: {task}",
        f"Source: {source}",
    ]

    if not timeline:
        lines.append("Events: 0")
        lines.append("No matching events found.")
        return "\n".join(lines)

    timeline.sort(
        key=lambda event: (
            _extract_attempt_idx(event),
            _PHASE_ORDER.get(_extract_phase(event), 10_000),
            _extract_phase(event),
        )
    )

    lines.append(f"Events: {len(timeline)}")
    for idx, event in enumerate(timeline):
        attempt_idx = _extract_attempt_idx(event)
        phase = _extract_phase(event)
        verifier = event.get("verifier")
        if isinstance(verifier, Mapping):
            verdict = str(verifier.get("verdict", "UNKNOWN"))
            outcome = str(verifier.get("outcome", "UNKNOWN"))
            reason_codes = _list_text(verifier.get("reason_codes"))
            violated_constraints = _list_text(verifier.get("violated_constraints"))
            cluster_id = verifier.get("failure_cluster_id")
            cluster_text = str(cluster_id) if isinstance(cluster_id, str) and cluster_id else "-"
        else:
            verdict = "UNKNOWN"
            outcome = "UNKNOWN"
            reason_codes = "-"
            violated_constraints = "-"
            cluster_text = "-"

        lines.append(
            f"[{idx}] attempt={attempt_idx} phase={phase} "
            f"verifier={verdict}/{outcome} "
            f"reason_codes={reason_codes} "
            f"violated_constraints={violated_constraints} "
            f"failure_cluster_id={cluster_text} "
            f"selected_rules={_rule_ids(event.get('selected_rules'))} "
            f"cost={_cost_text(event)}"
        )
    return "\n".join(lines)


__all__ = ["render_task_trace"]

