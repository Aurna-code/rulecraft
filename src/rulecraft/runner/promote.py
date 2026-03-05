"""Promotion gate runner for baseline-vs-candidate policy comparisons."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..metrics.eventlog_metrics import summarize_jsonl
from ..policy.profile import load_profile
from .batch import run_batch

_PASS_RATE_MIN_DELTA = -0.01
_SCHEMA_VIOLATION_MAX_DELTA = 0.02
_AVG_ATTEMPTS_MAX_DELTA_WITHOUT_GAIN = 0.25


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _resolve_profile(profile: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(profile, Mapping):
        return dict(profile)
    return load_profile(profile)


def _resolve_adapter(adapter: Any, label: str) -> Any:
    if callable(adapter):
        try:
            candidate = adapter(label)
        except TypeError:
            candidate = adapter()
        if candidate is None:
            raise ValueError(f"Adapter factory returned None for {label!r}.")
        return candidate
    return adapter


def _metrics_from_eventlog(path: str | Path) -> dict[str, float]:
    summary = summarize_jsonl(path, task_metrics=True)
    event_metrics = summary.get("event_metrics") if isinstance(summary, Mapping) else None
    task_metrics = summary.get("task_metrics") if isinstance(summary, Mapping) else None
    if not isinstance(event_metrics, Mapping):
        event_metrics = {}
    if not isinstance(task_metrics, Mapping):
        task_metrics = {}
    return {
        "task_pass_rate": _as_float(task_metrics.get("task_pass_rate")),
        "avg_attempts_per_task": _as_float(task_metrics.get("avg_attempts_per_task")),
        "cost_usd_total": _as_float(event_metrics.get("cost_usd_total")),
        "schema_violation_rate": _as_float(event_metrics.get("schema_violation_rate")),
    }


def _delta_map(baseline: Mapping[str, float], candidate: Mapping[str, float]) -> dict[str, float]:
    keys = ("task_pass_rate", "avg_attempts_per_task", "cost_usd_total", "schema_violation_rate")
    return {key: _as_float(candidate.get(key)) - _as_float(baseline.get(key)) for key in keys}


def _evaluate_gate(deltas: Mapping[str, float]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    regressions: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    pass_rate_delta = _as_float(deltas.get("task_pass_rate"))
    schema_violation_delta = _as_float(deltas.get("schema_violation_rate"))
    avg_attempts_delta = _as_float(deltas.get("avg_attempts_per_task"))

    if pass_rate_delta < _PASS_RATE_MIN_DELTA:
        regressions.append(
            {
                "metric": "task_pass_rate",
                "delta": pass_rate_delta,
                "threshold": _PASS_RATE_MIN_DELTA,
                "message": "Task pass rate decreased more than the allowed threshold.",
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

    if avg_attempts_delta > _AVG_ATTEMPTS_MAX_DELTA_WITHOUT_GAIN:
        if pass_rate_delta <= 0.0:
            regressions.append(
                {
                    "metric": "avg_attempts_per_task",
                    "delta": avg_attempts_delta,
                    "threshold": _AVG_ATTEMPTS_MAX_DELTA_WITHOUT_GAIN,
                    "message": "Average attempts increased without any task pass-rate gain.",
                }
            )
        elif pass_rate_delta < 0.01:
            warnings.append(
                {
                    "metric": "avg_attempts_per_task",
                    "delta": avg_attempts_delta,
                    "threshold": _AVG_ATTEMPTS_MAX_DELTA_WITHOUT_GAIN,
                    "message": "Average attempts increased with only marginal pass-rate gain.",
                }
            )

    return regressions, warnings


def run_promotion(
    tasks_path: str | Path,
    adapter: Any,
    baseline_profile: Mapping[str, Any] | str | Path,
    candidate_profile: Mapping[str, Any] | str | Path,
    tmp_dir: str | Path,
    seed: int | None = None,
) -> dict[str, Any]:
    """Run baseline/candidate policy comparison and return a regression gate report."""
    tmp_root = Path(tmp_dir)
    tmp_root.mkdir(parents=True, exist_ok=True)

    baseline_out = tmp_root / "promotion_baseline_eventlog.jsonl"
    candidate_out = tmp_root / "promotion_candidate_eventlog.jsonl"
    for path in (baseline_out, candidate_out):
        if path.exists():
            path.unlink()

    baseline_adapter = _resolve_adapter(adapter, "baseline")
    candidate_adapter = _resolve_adapter(adapter, "candidate")
    baseline_profile_data = _resolve_profile(baseline_profile)
    candidate_profile_data = _resolve_profile(candidate_profile)

    baseline_summary = run_batch(
        tasks_path=tasks_path,
        adapter=baseline_adapter,
        out_path=baseline_out,
        repair=True,
        max_attempts=1,
        scale="off",
        policy_profile=baseline_profile_data,
    )
    candidate_summary = run_batch(
        tasks_path=tasks_path,
        adapter=candidate_adapter,
        out_path=candidate_out,
        repair=True,
        max_attempts=1,
        scale="off",
        policy_profile=candidate_profile_data,
    )

    baseline_metrics = _metrics_from_eventlog(baseline_out)
    candidate_metrics = _metrics_from_eventlog(candidate_out)
    deltas = _delta_map(baseline_metrics, candidate_metrics)
    regressions, warnings = _evaluate_gate(deltas)

    ok = len(regressions) == 0
    report = {
        "ok": ok,
        "exit_code": 0 if ok else 1,
        "seed": seed,
        "thresholds": {
            "task_pass_rate_min_delta": _PASS_RATE_MIN_DELTA,
            "schema_violation_rate_max_delta": _SCHEMA_VIOLATION_MAX_DELTA,
            "avg_attempts_max_delta_without_gain": _AVG_ATTEMPTS_MAX_DELTA_WITHOUT_GAIN,
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
        "regressions": regressions,
        "warnings": warnings,
    }
    return report


__all__ = ["run_promotion"]
