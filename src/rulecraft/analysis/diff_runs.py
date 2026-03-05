"""Manifest-aware run diff utility."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

DEFAULT_OUTPUT_FILENAMES = {
    "baseline_eventlog": "baseline.jsonl",
    "metrics": "metrics.json",
    "flowmap": "flowmap.json",
    "candidate_policy": "candidate_policy.json",
    "candidate_rulebook": "candidate_rulebook.json",
    "regpack": "regpack.jsonl",
    "policy_report": "policy_promote_report.json",
    "rules_report": "rules_promote_report.json",
    "summary": "summary.json",
}


def _resolve_manifest(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "manifest.json"
    return candidate.resolve()


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError("Manifest must be a JSON object.")
    return dict(payload)


def _output_path(manifest: Mapping[str, Any], manifest_path: Path, key: str) -> Path:
    outputs = manifest.get("outputs")
    if isinstance(outputs, Mapping):
        rel = outputs.get(key)
    else:
        rel = None
    if not isinstance(rel, str) or not rel:
        rel = DEFAULT_OUTPUT_FILENAMES.get(key)
    if rel is None:
        return manifest_path.parent / f"{key}.json"
    candidate = Path(rel)
    if candidate.is_absolute():
        return candidate
    return manifest_path.parent / candidate


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _extract_metrics(payload: Mapping[str, Any]) -> dict[str, float | None]:
    summary = _mapping(payload.get("summary"))
    metrics_payload = _mapping(payload.get("metrics"))
    policy_report = _mapping(payload.get("policy_report"))
    rules_report = _mapping(payload.get("rules_report"))

    key_deltas = _mapping(summary.get("key_deltas"))
    event_metrics = _mapping(metrics_payload.get("event_metrics", metrics_payload))
    task_metrics = _mapping(metrics_payload.get("task_metrics"))
    policy_deltas = _mapping(policy_report.get("deltas"))
    rules_deltas = _mapping(rules_report.get("deltas"))

    def first(*values: Any) -> float | None:
        for item in values:
            numeric = _as_float(item)
            if numeric is not None:
                return numeric
        return None

    return {
        "task_pass_rate": first(
            key_deltas.get("task_pass_rate"),
            policy_deltas.get("task_pass_rate"),
            task_metrics.get("task_pass_rate"),
        ),
        "strong_pass_rate": first(
            key_deltas.get("strong_pass_rate"),
            rules_deltas.get("strong_pass_rate"),
        ),
        "schema_violation_rate": first(
            key_deltas.get("schema_violation_rate"),
            rules_deltas.get("schema_violation_rate"),
            policy_deltas.get("schema_violation_rate"),
            event_metrics.get("schema_violation_rate"),
        ),
        "avg_attempts_per_task": first(
            policy_deltas.get("avg_attempts_per_task"),
            rules_deltas.get("avg_attempts_per_task"),
            task_metrics.get("avg_attempts_per_task"),
        ),
        "cost_usd_total": first(
            key_deltas.get("cost_usd_total"),
            policy_deltas.get("cost_usd_total"),
            event_metrics.get("cost_usd_total"),
        ),
        "tokens_in_total": first(event_metrics.get("tokens_in_total")),
        "tokens_out_total": first(event_metrics.get("tokens_out_total")),
    }


def _top_failure_clusters(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics_payload = _mapping(payload.get("metrics"))
    event_metrics = _mapping(metrics_payload.get("event_metrics", metrics_payload))
    rows = _list_of_mappings(event_metrics.get("top_failure_clusters"))
    output: list[dict[str, Any]] = []
    for row in rows:
        cluster_id = row.get("cluster_id")
        count = _as_int(row.get("count"))
        if isinstance(cluster_id, str) and cluster_id and count is not None:
            output.append({"cluster_id": cluster_id, "count": count})
    return output


def _cluster_deltas(a_rows: list[dict[str, Any]], b_rows: list[dict[str, Any]]) -> dict[str, Any]:
    a_count = {str(row["cluster_id"]): int(row["count"]) for row in a_rows}
    b_count = {str(row["cluster_id"]): int(row["count"]) for row in b_rows}
    a_rank = {str(row["cluster_id"]): idx + 1 for idx, row in enumerate(a_rows)}
    b_rank = {str(row["cluster_id"]): idx + 1 for idx, row in enumerate(b_rows)}

    changes: list[dict[str, Any]] = []
    for cluster_id in sorted(set(a_count) | set(b_count)):
        count_a = int(a_count.get(cluster_id, 0))
        count_b = int(b_count.get(cluster_id, 0))
        rank_a = a_rank.get(cluster_id)
        rank_b = b_rank.get(cluster_id)
        rank_delta = None if rank_a is None or rank_b is None else int(rank_a - rank_b)
        if count_a == count_b and rank_delta in {0, None}:
            continue
        changes.append(
            {
                "cluster_id": cluster_id,
                "count_a": count_a,
                "count_b": count_b,
                "delta_count": int(count_b - count_a),
                "rank_a": rank_a,
                "rank_b": rank_b,
                "rank_movement": rank_delta,
            }
        )

    improved = sorted((row for row in changes if int(row["delta_count"]) < 0), key=lambda row: (row["delta_count"], row["cluster_id"]))
    worsened = sorted(
        (row for row in changes if int(row["delta_count"]) > 0),
        key=lambda row: (-int(row["delta_count"]), row["cluster_id"]),
    )
    return {
        "changes": sorted(changes, key=lambda row: (-abs(int(row["delta_count"])), row["cluster_id"]))[:20],
        "improved": improved[:10],
        "worsened": worsened[:10],
    }


def _rule_impact_deltas(a_payload: Mapping[str, Any], b_payload: Mapping[str, Any]) -> dict[str, Any] | None:
    a_rules = _mapping(_mapping(a_payload.get("rules_report")).get("rule_impact"))
    b_rules = _mapping(_mapping(b_payload.get("rules_report")).get("rule_impact"))
    if not a_rules and not b_rules:
        return None

    def section_values(rules_payload: Mapping[str, Any]) -> tuple[int, int, Mapping[str, Any]]:
        improvements = _mapping(rules_payload.get("improvements"))
        regressions = _mapping(rules_payload.get("regressions"))
        candidate = _mapping(rules_payload.get("candidate"))
        return (
            int(_as_int(improvements.get("tasks_improved")) or 0),
            int(_as_int(regressions.get("tasks_regressed")) or 0),
            _mapping(candidate.get("rule_selection_counts")),
        )

    a_improved, a_regressed, a_counts = section_values(a_rules)
    b_improved, b_regressed, b_counts = section_values(b_rules)

    changes: list[dict[str, Any]] = []
    for rule_id in sorted(set(a_counts) | set(b_counts)):
        count_a = int(_as_int(a_counts.get(rule_id)) or 0)
        count_b = int(_as_int(b_counts.get(rule_id)) or 0)
        if count_a == count_b:
            continue
        changes.append(
            {
                "rule_id": rule_id,
                "count_a": count_a,
                "count_b": count_b,
                "delta_count": int(count_b - count_a),
            }
        )

    return {
        "tasks_improved_delta": int(b_improved - a_improved),
        "tasks_regressed_delta": int(b_regressed - a_regressed),
        "rule_selection_changes": sorted(changes, key=lambda row: (-abs(int(row["delta_count"])), str(row["rule_id"])))[:20],
    }


def _signed_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return float(b - a)


def diff_runs(manifest_a: str, manifest_b: str) -> dict[str, Any]:
    """Compare two evolve/replay runs by their manifests and linked artifacts."""
    path_a = _resolve_manifest(manifest_a)
    path_b = _resolve_manifest(manifest_b)
    data_a = _load_manifest(path_a)
    data_b = _load_manifest(path_b)

    payload_a = {
        "manifest": data_a,
        "summary": _load_json(_output_path(data_a, path_a, "summary")) or {},
        "policy_report": _load_json(_output_path(data_a, path_a, "policy_report")) or {},
        "rules_report": _load_json(_output_path(data_a, path_a, "rules_report")) or {},
        "metrics": _load_json(_output_path(data_a, path_a, "metrics")) or {},
        "flowmap": _load_json(_output_path(data_a, path_a, "flowmap")) or {},
    }
    payload_b = {
        "manifest": data_b,
        "summary": _load_json(_output_path(data_b, path_b, "summary")) or {},
        "policy_report": _load_json(_output_path(data_b, path_b, "policy_report")) or {},
        "rules_report": _load_json(_output_path(data_b, path_b, "rules_report")) or {},
        "metrics": _load_json(_output_path(data_b, path_b, "metrics")) or {},
        "flowmap": _load_json(_output_path(data_b, path_b, "flowmap")) or {},
    }

    metrics_a = _extract_metrics(payload_a)
    metrics_b = _extract_metrics(payload_b)
    metric_deltas = {key: _signed_delta(metrics_a.get(key), metrics_b.get(key)) for key in sorted(metrics_a)}

    cluster_deltas = _cluster_deltas(_top_failure_clusters(payload_a), _top_failure_clusters(payload_b))
    rule_impact_deltas = _rule_impact_deltas(payload_a, payload_b)

    higher_is_better = {"task_pass_rate", "strong_pass_rate"}
    lower_is_better = {
        "schema_violation_rate",
        "avg_attempts_per_task",
        "cost_usd_total",
        "tokens_in_total",
        "tokens_out_total",
    }
    improvements: dict[str, Any] = {
        "metrics": {},
        "top_failure_clusters": cluster_deltas.get("improved", []),
    }
    regressions: dict[str, Any] = {
        "metrics": {},
        "top_failure_clusters": cluster_deltas.get("worsened", []),
    }

    for key, delta in metric_deltas.items():
        if delta is None:
            continue
        if key in higher_is_better:
            if delta > 0:
                improvements["metrics"][key] = delta
            elif delta < 0:
                regressions["metrics"][key] = delta
        elif key in lower_is_better:
            if delta < 0:
                improvements["metrics"][key] = delta
            elif delta > 0:
                regressions["metrics"][key] = delta

    if isinstance(rule_impact_deltas, Mapping):
        improvements["rule_impact"] = {
            "tasks_improved_delta": rule_impact_deltas.get("tasks_improved_delta"),
            "tasks_regressed_delta": rule_impact_deltas.get("tasks_regressed_delta"),
            "positive_rule_selection_changes": [
                row for row in _list_of_mappings(rule_impact_deltas.get("rule_selection_changes")) if _as_int(row.get("delta_count")) and int(row["delta_count"]) > 0
            ][:10],
        }
        regressions["rule_impact"] = {
            "tasks_improved_delta": rule_impact_deltas.get("tasks_improved_delta"),
            "tasks_regressed_delta": rule_impact_deltas.get("tasks_regressed_delta"),
            "negative_rule_selection_changes": [
                row for row in _list_of_mappings(rule_impact_deltas.get("rule_selection_changes")) if _as_int(row.get("delta_count")) and int(row["delta_count"]) < 0
            ][:10],
        }

    return {
        "a": {
            "manifest_path": str(path_a),
            "commit": _mapping(data_a.get("git")).get("commit"),
            "created_utc": data_a.get("created_utc"),
        },
        "b": {
            "manifest_path": str(path_b),
            "commit": _mapping(data_b.get("git")).get("commit"),
            "created_utc": data_b.get("created_utc"),
        },
        "deltas": {
            "metrics": metric_deltas,
            "top_failure_clusters": cluster_deltas,
            "rule_impact": rule_impact_deltas,
        },
        "improvements": improvements,
        "regressions": regressions,
    }


__all__ = ["diff_runs"]
