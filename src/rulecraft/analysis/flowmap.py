"""Offline FlowMap analyzer for bucket-level risk and opportunity views."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from ..contracts import normalize_eventlog_dict, pass_from


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


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
    attempt_idx = extra.get("attempt_idx")
    if isinstance(attempt_idx, bool):
        return int(attempt_idx)
    if isinstance(attempt_idx, int):
        return attempt_idx
    if isinstance(attempt_idx, float) and attempt_idx.is_integer():
        return int(attempt_idx)
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


def _extract_scale_meta(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    run = event.get("run")
    if not isinstance(run, Mapping):
        return None
    extra = run.get("extra")
    if not isinstance(extra, Mapping):
        return None
    scale = extra.get("scale")
    if isinstance(scale, Mapping):
        return scale
    return None


def _event_is_pass(event: Mapping[str, Any]) -> bool:
    verifier = event.get("verifier")
    if isinstance(verifier, Mapping):
        return pass_from(verifier) == 1
    return False


def _event_is_strong_pass(event: Mapping[str, Any]) -> bool:
    verifier = event.get("verifier")
    if not isinstance(verifier, Mapping):
        return False
    return verifier.get("verdict") == "PASS" and verifier.get("outcome") == "OK"


def _event_outcome(event: Mapping[str, Any]) -> str:
    verifier = event.get("verifier")
    if not isinstance(verifier, Mapping):
        return "UNKNOWN"
    outcome = verifier.get("outcome")
    if isinstance(outcome, str) and outcome:
        return outcome
    return "UNKNOWN"


def _event_cluster_id(event: Mapping[str, Any]) -> str | None:
    verifier = event.get("verifier")
    if not isinstance(verifier, Mapping):
        return None
    cluster_id = verifier.get("failure_cluster_id")
    if isinstance(cluster_id, str) and cluster_id:
        return cluster_id
    return None


def _event_reason_codes(event: Mapping[str, Any]) -> list[str] | None:
    verifier = event.get("verifier")
    if not isinstance(verifier, Mapping):
        return None
    codes = verifier.get("reason_codes")
    if not isinstance(codes, list):
        return None
    normalized = [code for code in codes if isinstance(code, str) and code]
    return normalized or None


def _event_constraints(event: Mapping[str, Any]) -> list[str] | None:
    verifier = event.get("verifier")
    if not isinstance(verifier, Mapping):
        return None
    constraints = verifier.get("violated_constraints")
    if not isinstance(constraints, list):
        return None
    normalized = [item for item in constraints if isinstance(item, str) and item]
    return normalized or None


def _event_cost(event: Mapping[str, Any]) -> tuple[float | None, int | None]:
    cost = event.get("cost")
    if not isinstance(cost, Mapping):
        return None, None

    meta = cost.get("meta")
    if isinstance(meta, Mapping):
        raw_cost = meta.get("cost_usd")
        if isinstance(raw_cost, bool):
            cost_usd = float(int(raw_cost))
        elif isinstance(raw_cost, (int, float)):
            cost_usd = float(raw_cost)
        else:
            cost_usd = None
    else:
        cost_usd = None

    raw_tokens_in = cost.get("tokens_in")
    raw_tokens_out = cost.get("tokens_out")
    if isinstance(raw_tokens_in, bool):
        tokens_in = int(raw_tokens_in)
    elif isinstance(raw_tokens_in, int):
        tokens_in = raw_tokens_in
    else:
        tokens_in = None
    if isinstance(raw_tokens_out, bool):
        tokens_out = int(raw_tokens_out)
    elif isinstance(raw_tokens_out, int):
        tokens_out = raw_tokens_out
    else:
        tokens_out = None

    if tokens_in is None and tokens_out is None:
        token_total = None
    else:
        token_total = (tokens_in or 0) + (tokens_out or 0)
    return cost_usd, token_total


def _phase_gain_map(tasks: list[list[dict[str, Any]]]) -> dict[str, float]:
    tasks_total = len(tasks)
    if tasks_total == 0:
        return {"repair_gain": 0.0, "probe_gain": 0.0, "full_gain": 0.0, "synth_gain": 0.0}

    repair_gain = 0
    probe_gain = 0
    full_gain = 0
    synth_gain = 0

    for timeline in tasks:
        sorted_timeline = sorted(timeline, key=lambda event: (event["_attempt_idx"], event["_order"]))
        if not sorted_timeline:
            continue

        attempt0 = next((event for event in sorted_timeline if event["_attempt_idx"] == 0), sorted_timeline[0])
        if not _event_is_strong_pass(attempt0):
            if any(event["_phase"] == "repair" and _event_is_strong_pass(event) for event in sorted_timeline):
                repair_gain += 1

        probe_indices = [idx for idx, event in enumerate(sorted_timeline) if event["_phase"] == "scale_probe"]
        if probe_indices:
            first_probe_idx = probe_indices[0]
            pre_probe = sorted_timeline[:first_probe_idx]
            probe_success = any(
                sorted_timeline[idx]["_phase"] == "scale_probe" and _event_is_strong_pass(sorted_timeline[idx])
                for idx in probe_indices
            )
            if not any(_event_is_strong_pass(event) for event in pre_probe) and probe_success:
                probe_gain += 1

        full_indices = [idx for idx, event in enumerate(sorted_timeline) if event["_phase"] == "scale_full"]
        if full_indices:
            first_full_idx = full_indices[0]
            pre_full = sorted_timeline[:first_full_idx]
            full_success = any(
                sorted_timeline[idx]["_phase"] == "scale_full" and _event_is_strong_pass(sorted_timeline[idx])
                for idx in full_indices
            )
            if not any(_event_is_strong_pass(event) for event in pre_full) and full_success:
                full_gain += 1

        if any(
            event["_phase"] in {"scale_probe", "scale_full"}
            and bool(event["_scale_meta"].get("used_synth") if isinstance(event["_scale_meta"], Mapping) else False)
            and event["_scale_meta"].get("synth_verdict") == "PASS"
            and event["_scale_meta"].get("synth_outcome") == "OK"
            for event in sorted_timeline
            if isinstance(event["_scale_meta"], Mapping)
        ):
            synth_gain += 1

    return {
        "repair_gain": _safe_rate(repair_gain, tasks_total),
        "probe_gain": _safe_rate(probe_gain, tasks_total),
        "full_gain": _safe_rate(full_gain, tasks_total),
        "synth_gain": _safe_rate(synth_gain, tasks_total),
    }


def _avg_map(values: Mapping[str, list[float]]) -> dict[str, float]:
    output: dict[str, float] = {}
    for key, series in values.items():
        if not series:
            continue
        output[key] = sum(series) / len(series)
    return output


def _efficiency_map(
    gains: Mapping[str, float],
    avg_cost_usd_by_phase: Mapping[str, float],
    avg_tokens_by_phase: Mapping[str, float],
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    phase_lookup = {
        "repair": gains.get("repair_gain", 0.0),
        "scale_probe": gains.get("probe_gain", 0.0),
        "scale_full": gains.get("full_gain", 0.0),
        "synth": gains.get("synth_gain", 0.0),
    }
    gain_per_usd: dict[str, float | None] = {}
    gain_per_token: dict[str, float | None] = {}

    for phase, gain in phase_lookup.items():
        avg_usd = avg_cost_usd_by_phase.get(phase)
        avg_tokens = avg_tokens_by_phase.get(phase)
        gain_per_usd[phase] = (gain / avg_usd) if avg_usd is not None and avg_usd > 0 else None
        gain_per_token[phase] = (gain / avg_tokens) if avg_tokens is not None and avg_tokens > 0 else None

    return gain_per_usd, gain_per_token


def analyze_flowmap(path: str, group_by: str = "bucket_key") -> dict[str, Any]:
    """Analyze EventLog records into bucket-level risk and opportunity maps."""
    if group_by != "bucket_key":
        raise ValueError(f"Unsupported group_by value: {group_by!r}")

    grouped_tasks: dict[str, dict[str, list[dict[str, Any]]]] = {}
    cluster_counts: dict[str, Counter[str]] = {}
    cluster_samples: dict[str, dict[str, dict[str, Any]]] = {}
    phase_cost_usd: dict[str, dict[str, list[float]]] = {}
    phase_tokens: dict[str, dict[str, list[float]]] = {}

    source = Path(path)
    if source.exists():
        with source.open("r", encoding="utf-8") as fp:
            order = 0
            for line in fp:
                stripped = line.strip()
                if not stripped:
                    continue
                raw = json.loads(stripped)
                if not isinstance(raw, dict):
                    continue
                event = normalize_eventlog_dict(raw)

                task_id = _extract_task_id(event)
                if task_id is None:
                    continue
                bucket_key = event.get("bucket_key")
                bucket = bucket_key if isinstance(bucket_key, str) else "(null)"

                grouped_tasks.setdefault(bucket, {}).setdefault(task_id, [])
                cluster_counts.setdefault(bucket, Counter())
                cluster_samples.setdefault(bucket, {})
                phase_cost_usd.setdefault(bucket, {})
                phase_tokens.setdefault(bucket, {})

                phase = _extract_phase(event)
                attempt_idx = _extract_attempt_idx(event)
                scale_meta = _extract_scale_meta(event)
                cost_usd, token_total = _event_cost(event)

                row = dict(event)
                row["_phase"] = phase
                row["_attempt_idx"] = attempt_idx
                row["_order"] = order
                row["_scale_meta"] = dict(scale_meta) if isinstance(scale_meta, Mapping) else {}
                grouped_tasks[bucket][task_id].append(row)
                order += 1

                cluster_id = _event_cluster_id(event)
                if cluster_id is not None:
                    cluster_counts[bucket][cluster_id] += 1
                    if cluster_id not in cluster_samples[bucket]:
                        cluster_samples[bucket][cluster_id] = {
                            "sample_reason_codes": _event_reason_codes(event),
                            "sample_constraints": _event_constraints(event),
                        }

                if cost_usd is not None:
                    phase_cost_usd[bucket].setdefault(phase, []).append(cost_usd)
                if token_total is not None:
                    phase_tokens[bucket].setdefault(phase, []).append(float(token_total))

                if isinstance(scale_meta, Mapping) and bool(scale_meta.get("used_synth")):
                    k = scale_meta.get("k")
                    if isinstance(k, bool):
                        k_count = int(k)
                    elif isinstance(k, int):
                        k_count = k
                    else:
                        k_count = 0
                    denom = k_count + 1 if k_count >= 1 else None
                    if denom:
                        if cost_usd is not None:
                            phase_cost_usd[bucket].setdefault("synth", []).append(cost_usd / denom)
                        if token_total is not None:
                            phase_tokens[bucket].setdefault("synth", []).append(float(token_total) / denom)

    risk_map: dict[str, dict[str, Any]] = {}
    opportunity_map: dict[str, dict[str, Any]] = {}

    for bucket in sorted(grouped_tasks):
        task_map = grouped_tasks[bucket]
        task_timelines = [timeline for timeline in task_map.values()]
        tasks_total = len(task_timelines)
        passed_tasks = 0
        strong_pass_tasks = 0
        unknown_tasks = 0
        failed_tasks = 0

        for timeline in task_timelines:
            ordered = sorted(timeline, key=lambda event: (event["_attempt_idx"], event["_order"]))
            if any(_event_is_pass(event) for event in ordered):
                passed_tasks += 1
            if any(_event_is_strong_pass(event) for event in ordered):
                strong_pass_tasks += 1

            final = ordered[-1]
            final_outcome = _event_outcome(final)
            if final_outcome == "UNKNOWN":
                unknown_tasks += 1
            elif not _event_is_pass(final):
                failed_tasks += 1

        top_clusters = []
        for cluster_id, count in cluster_counts[bucket].most_common(10):
            sample = cluster_samples[bucket].get(cluster_id, {})
            top_clusters.append(
                {
                    "cluster_id": cluster_id,
                    "count": count,
                    "sample_reason_codes": sample.get("sample_reason_codes"),
                    "sample_constraints": sample.get("sample_constraints"),
                }
            )

        gains = _phase_gain_map(task_timelines)
        avg_cost = _avg_map(phase_cost_usd.get(bucket, {}))
        avg_tokens = _avg_map(phase_tokens.get(bucket, {}))
        gain_per_usd, gain_per_token = _efficiency_map(gains, avg_cost, avg_tokens)

        risk_map[bucket] = {
            "tasks_total": tasks_total,
            "task_pass_rate": _safe_rate(passed_tasks, tasks_total),
            "strong_pass_rate": _safe_rate(strong_pass_tasks, tasks_total),
            "unknown_rate": _safe_rate(unknown_tasks, tasks_total),
            "fail_rate": _safe_rate(failed_tasks, tasks_total),
            "top_failure_clusters": top_clusters,
        }
        opportunity_map[bucket] = {
            "repair_gain": gains["repair_gain"],
            "probe_gain": gains["probe_gain"],
            "full_gain": gains["full_gain"],
            "synth_gain": gains["synth_gain"],
            "avg_cost_usd_by_phase": avg_cost,
            "avg_tokens_by_phase": avg_tokens,
            "gain_per_usd": gain_per_usd,
            "gain_per_token": gain_per_token,
        }

    return {
        "group_by": group_by,
        "risk_map": risk_map,
        "opportunity_map": opportunity_map,
    }


__all__ = ["analyze_flowmap"]
