"""Promotion gate runner for baseline-vs-candidate rulebook comparisons."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from ..metrics.eventlog_metrics import iter_normalized_jsonl, summarize_jsonl
from ..policy.profile import load_profile
from ..rulebook.store import RulebookStore
from .batch import run_batch

_TASK_PASS_RATE_MIN_DELTA = -0.01
_STRONG_PASS_RATE_MIN_DELTA = -0.01
_SCHEMA_VIOLATION_MAX_DELTA = 0.02
_CLUSTER_WORSEN_RATIO_MAX = 0.05
_BASELINE_TOP_CLUSTER_N = 5


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _resolve_policy_profile(policy_profile_path: str | Path | None) -> dict[str, Any] | None:
    if policy_profile_path is None:
        return None
    return load_profile(policy_profile_path)


def _resolve_adapter(adapter: Any, label: str) -> Any:
    if callable(adapter):
        try:
            instance = adapter(label)
        except TypeError:
            instance = adapter()
        if instance is None:
            raise ValueError(f"Adapter factory returned None for {label!r}.")
        return instance
    return adapter


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


def _collect_strong_pass_rate(path: str | Path) -> float:
    task_strong_pass: dict[str, bool] = {}
    for event in iter_normalized_jsonl(path):
        task_id = _extract_task_id(event)
        if task_id is None:
            continue
        task_strong_pass.setdefault(task_id, False)

        verifier = event.get("verifier")
        if not isinstance(verifier, Mapping):
            continue
        if verifier.get("verdict") == "PASS" and verifier.get("outcome") == "OK":
            task_strong_pass[task_id] = True

    if not task_strong_pass:
        return 0.0
    passed = sum(1 for value in task_strong_pass.values() if value)
    return passed / len(task_strong_pass)


def _collect_cluster_counts(path: str | Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    for event in iter_normalized_jsonl(path):
        verifier = event.get("verifier")
        if not isinstance(verifier, Mapping):
            continue
        cluster_id = verifier.get("failure_cluster_id")
        if isinstance(cluster_id, str) and cluster_id:
            counts[cluster_id] += 1
    return counts


def _collect_metrics(path: str | Path) -> tuple[dict[str, float], Counter[str]]:
    summary = summarize_jsonl(path, task_metrics=True)
    event_metrics = summary.get("event_metrics") if isinstance(summary, Mapping) else None
    task_metrics = summary.get("task_metrics") if isinstance(summary, Mapping) else None
    if not isinstance(event_metrics, Mapping):
        event_metrics = {}
    if not isinstance(task_metrics, Mapping):
        task_metrics = {}

    cluster_counts = _collect_cluster_counts(path)
    top_clusters = [
        {"cluster_id": cluster_id, "count": count}
        for cluster_id, count in sorted(cluster_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]
    metrics = {
        "task_pass_rate": _as_float(task_metrics.get("task_pass_rate")),
        "strong_pass_rate": _collect_strong_pass_rate(path),
        "avg_attempts_per_task": _as_float(task_metrics.get("avg_attempts_per_task")),
        "schema_violation_rate": _as_float(event_metrics.get("schema_violation_rate")),
        "format_leak_rate": _as_float(event_metrics.get("format_leak_rate")),
        "top_failure_clusters": top_clusters,
    }
    return metrics, cluster_counts


def _delta_map(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, float]:
    keys = (
        "task_pass_rate",
        "strong_pass_rate",
        "avg_attempts_per_task",
        "schema_violation_rate",
        "format_leak_rate",
    )
    return {key: _as_float(candidate.get(key)) - _as_float(baseline.get(key)) for key in keys}


def _evaluate_cluster_regressions(
    baseline_counts: Mapping[str, int],
    candidate_counts: Mapping[str, int],
    *,
    pass_rate_delta: float,
    top_n: int = _BASELINE_TOP_CLUSTER_N,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    regressions: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    deltas: list[dict[str, Any]] = []

    baseline_top = sorted(baseline_counts.items(), key=lambda item: (-int(item[1]), item[0]))[:top_n]
    for cluster_id, baseline_count in baseline_top:
        candidate_count = int(candidate_counts.get(cluster_id, 0))
        delta_count = candidate_count - int(baseline_count)
        if int(baseline_count) <= 0:
            delta_ratio = 0.0
        else:
            delta_ratio = delta_count / int(baseline_count)
        row = {
            "cluster_id": cluster_id,
            "baseline_count": int(baseline_count),
            "candidate_count": candidate_count,
            "delta_count": delta_count,
            "delta_ratio": delta_ratio,
        }
        deltas.append(row)

        if delta_ratio > _CLUSTER_WORSEN_RATIO_MAX:
            if pass_rate_delta > 0.0:
                warnings.append(
                    {
                        "metric": "top_failure_clusters",
                        "cluster_id": cluster_id,
                        "delta_ratio": delta_ratio,
                        "threshold": _CLUSTER_WORSEN_RATIO_MAX,
                        "message": "Cluster count increased but task pass rate improved.",
                    }
                )
            else:
                regressions.append(
                    {
                        "metric": "top_failure_clusters",
                        "cluster_id": cluster_id,
                        "delta_ratio": delta_ratio,
                        "threshold": _CLUSTER_WORSEN_RATIO_MAX,
                        "message": "Top baseline failure cluster worsened beyond threshold.",
                    }
                )

    worsened = sorted((item for item in deltas if item["delta_count"] > 0), key=lambda item: (-item["delta_count"], item["cluster_id"]))
    return regressions, warnings, worsened


def _evaluate_gate(
    deltas: Mapping[str, float],
    baseline_cluster_counts: Mapping[str, int],
    candidate_cluster_counts: Mapping[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    regressions: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    task_pass_rate_delta = _as_float(deltas.get("task_pass_rate"))
    strong_pass_rate_delta = _as_float(deltas.get("strong_pass_rate"))
    schema_violation_delta = _as_float(deltas.get("schema_violation_rate"))

    if task_pass_rate_delta < _TASK_PASS_RATE_MIN_DELTA:
        regressions.append(
            {
                "metric": "task_pass_rate",
                "delta": task_pass_rate_delta,
                "threshold": _TASK_PASS_RATE_MIN_DELTA,
                "message": "Task pass rate decreased more than the allowed threshold.",
            }
        )
    if strong_pass_rate_delta < _STRONG_PASS_RATE_MIN_DELTA:
        regressions.append(
            {
                "metric": "strong_pass_rate",
                "delta": strong_pass_rate_delta,
                "threshold": _STRONG_PASS_RATE_MIN_DELTA,
                "message": "Strong pass rate decreased more than the allowed threshold.",
            }
        )
    if schema_violation_delta > _SCHEMA_VIOLATION_MAX_DELTA:
        regressions.append(
            {
                "metric": "schema_violation_rate",
                "delta": schema_violation_delta,
                "threshold": _SCHEMA_VIOLATION_MAX_DELTA,
                "message": "Schema violation rate increased more than the allowed threshold.",
            }
        )

    cluster_regressions, cluster_warnings, worsened_clusters = _evaluate_cluster_regressions(
        baseline_cluster_counts,
        candidate_cluster_counts,
        pass_rate_delta=task_pass_rate_delta,
    )
    regressions.extend(cluster_regressions)
    warnings.extend(cluster_warnings)

    return regressions, warnings, worsened_clusters


def run_rule_promotion(
    tasks_path: str | Path,
    adapter: Any,
    baseline_rulebook_path: str | Path,
    candidate_rulebook_path: str | Path,
    policy_profile_path: str | Path | None,
    tmp_dir: str | Path,
    seed: int | None = None,
) -> dict[str, Any]:
    """Run baseline/candidate rulebook comparison and return a gate report."""
    tmp_root = Path(tmp_dir)
    tmp_root.mkdir(parents=True, exist_ok=True)
    baseline_out = tmp_root / "promotion_rules_baseline_eventlog.jsonl"
    candidate_out = tmp_root / "promotion_rules_candidate_eventlog.jsonl"
    for target in (baseline_out, candidate_out):
        if target.exists():
            target.unlink()

    baseline_rulebook = RulebookStore.load_from_json(baseline_rulebook_path)
    candidate_rulebook = RulebookStore.load_from_json(candidate_rulebook_path)
    policy_profile = _resolve_policy_profile(policy_profile_path)

    baseline_summary = run_batch(
        tasks_path=tasks_path,
        adapter=_resolve_adapter(adapter, "baseline"),
        out_path=baseline_out,
        repair=True,
        max_attempts=1,
        scale="off",
        rulebook_store=baseline_rulebook,
        policy_profile=policy_profile,
    )
    candidate_summary = run_batch(
        tasks_path=tasks_path,
        adapter=_resolve_adapter(adapter, "candidate"),
        out_path=candidate_out,
        repair=True,
        max_attempts=1,
        scale="off",
        rulebook_store=candidate_rulebook,
        policy_profile=policy_profile,
    )

    baseline_metrics, baseline_clusters = _collect_metrics(baseline_out)
    candidate_metrics, candidate_clusters = _collect_metrics(candidate_out)
    deltas = _delta_map(baseline_metrics, candidate_metrics)
    regressions, warnings, worsened_clusters = _evaluate_gate(deltas, baseline_clusters, candidate_clusters)
    ok = len(regressions) == 0

    return {
        "ok": ok,
        "exit_code": 0 if ok else 1,
        "seed": seed,
        "thresholds": {
            "task_pass_rate_min_delta": _TASK_PASS_RATE_MIN_DELTA,
            "strong_pass_rate_min_delta": _STRONG_PASS_RATE_MIN_DELTA,
            "schema_violation_rate_max_delta": _SCHEMA_VIOLATION_MAX_DELTA,
            "cluster_worsen_ratio_max": _CLUSTER_WORSEN_RATIO_MAX,
            "baseline_top_clusters_n": _BASELINE_TOP_CLUSTER_N,
        },
        "deltas": deltas,
        "baseline": {
            "summary": baseline_summary,
            "metrics": baseline_metrics,
            "eventlog_path": str(baseline_out),
        },
        "candidate": {
            "summary": candidate_summary,
            "metrics": candidate_metrics,
            "eventlog_path": str(candidate_out),
        },
        "top_worsened_clusters": worsened_clusters[:10],
        "regressions": regressions,
        "warnings": warnings,
    }


__all__ = ["run_rule_promotion"]
