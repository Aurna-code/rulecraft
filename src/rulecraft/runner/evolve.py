"""End-to-end evolution orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..adapters.openai_adapter import OpenAIAdapter
from ..adapters.scripted import ScriptedAdapter
from ..adapters.stub import StubAdapter
from ..analysis.flowmap import analyze_flowmap
from ..analysis.regpack import build_regpack
from ..metrics.eventlog_metrics import summarize_jsonl
from ..policy.profile import load_profile
from ..policy.suggest import suggest_policy
from ..rulebook.store import RulebookStore
from ..rulebook.suggest import suggest_rules
from .batch import run_batch
from .manifest import DEFAULT_OUTPUT_FILENAMES, build_manifest, write_manifest
from .promote import run_promotion
from .promote_rules import run_rule_promotion


def _write_json(path: Path, payload: Mapping[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _adapter_script_config(scripted: Mapping[str, Any] | None, label: str) -> dict[str, Any]:
    if not isinstance(scripted, Mapping):
        return {"scripts": {}}

    scoped = scripted.get(label)
    raw = scoped if isinstance(scoped, Mapping) else scripted
    config = dict(raw)

    scripts = config.get("scripts")
    if not isinstance(scripts, Mapping):
        config["scripts"] = {}
    else:
        config["scripts"] = dict(scripts)

    phase_scripts = config.get("phase_scripts")
    if isinstance(phase_scripts, Mapping):
        config["phase_scripts"] = dict(phase_scripts)
    else:
        config.pop("phase_scripts", None)
    return config


def _adapter_factory(adapter: str, scripted: Mapping[str, Any] | None = None):
    adapter_name = str(adapter).lower()
    if adapter_name == "stub":
        return lambda _label: StubAdapter(mode="text")
    if adapter_name == "openai":
        return lambda _label: OpenAIAdapter()
    if adapter_name == "scripted":
        return lambda label: ScriptedAdapter(**_adapter_script_config(scripted, label))
    raise ValueError(f"Unsupported adapter: {adapter!r}")


def _baseline_policy_profile(path: str | None) -> dict[str, Any]:
    if path is None:
        return {"version": 1, "rules": []}
    return load_profile(path)


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
    except TypeError:
        return None
    return value


def _baseline_rulebook_path(path: str | None, outdir: Path) -> str:
    if path is not None:
        return path

    default_path = outdir / "_baseline_rulebook.json"
    if not default_path.exists():
        _write_json(default_path, {"rulebook_name": "Rulebook", "rules": []})
    return str(default_path)


def _cluster_rows(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping):
            rows.append(dict(item))
    return rows


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def run_evolve(
    *,
    outdir: str,
    tasks_path: str,
    adapter: str,
    baseline_policy_profile_path: str | None = None,
    baseline_rulebook_path: str | None = None,
    scale: str = "off",
    repair: bool = False,
    max_attempts: int = 1,
    expand_counterexamples: bool = False,
    seed: int = 1337,
    fail_on_regression: bool = False,
    limit: int | None = None,
    instructions: str | None = None,
    budget_usd: float | None = None,
    budget_tokens: int | None = None,
    k_probe: int = 3,
    k_full: int = 8,
    top_m: int = 2,
    synth: bool = True,
    regpack_per_cluster: int = 2,
    regpack_max_total: int = 100,
    regpack_counterexamples_per_cluster: int = 2,
    scripted_adapter: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run baseline->suggest->regpack->gates and return summary payload."""
    outdir_path = Path(outdir).resolve()
    outdir_path.mkdir(parents=True, exist_ok=True)
    tasks_path_resolved = str(Path(tasks_path).resolve())
    baseline_policy_resolved = str(Path(baseline_policy_profile_path).resolve()) if baseline_policy_profile_path else None
    baseline_rulebook_resolved = str(Path(baseline_rulebook_path).resolve()) if baseline_rulebook_path else None

    outputs = dict(DEFAULT_OUTPUT_FILENAMES)
    output_paths = {key: outdir_path / rel_path for key, rel_path in outputs.items()}

    for key, path in output_paths.items():
        if key != "summary" and path.exists():
            path.unlink()

    run_batch_params = {
        "limit": limit,
        "instructions": instructions,
        "repair": bool(repair),
        "max_attempts": int(max_attempts),
        "scale": str(scale),
        "k_probe": int(k_probe),
        "k_full": int(k_full),
        "top_m": int(top_m),
        "synth": bool(synth),
        "budget_usd": budget_usd,
        "budget_tokens": budget_tokens,
        "seed": int(seed),
    }
    regpack_params = {
        "per_cluster": int(regpack_per_cluster),
        "max_total": int(regpack_max_total),
        "expand_counterexamples": bool(expand_counterexamples),
        "counterexamples_per_cluster": int(regpack_counterexamples_per_cluster),
        "seed": int(seed),
    }
    promote_params = {
        "fail_on_regression": bool(fail_on_regression),
        "seed": int(seed),
    }
    promote_rules_params = {
        "fail_on_regression": bool(fail_on_regression),
        "seed": int(seed),
    }

    manifest = build_manifest(
        tasks_path=tasks_path_resolved,
        baseline_policy_profile_path=baseline_policy_resolved,
        baseline_rulebook_path=baseline_rulebook_resolved,
        adapter=str(adapter),
        run_batch_params=run_batch_params,
        regpack_params=regpack_params,
        promote_params=promote_params,
        promote_rules_params=promote_rules_params,
        outputs=outputs,
    )
    if str(adapter).lower() == "scripted":
        manifest["params"]["scripted_adapter"] = _json_safe(scripted_adapter)
    write_manifest(outdir_path / "manifest.json", manifest)

    adapter_for = _adapter_factory(adapter, scripted_adapter)
    baseline_policy = _baseline_policy_profile(baseline_policy_resolved)
    baseline_rulebook_for_gate = _baseline_rulebook_path(baseline_rulebook_resolved, outdir_path)
    baseline_rulebook_store = (
        RulebookStore.load_from_json(baseline_rulebook_resolved) if baseline_rulebook_resolved is not None else None
    )
    baseline_run_profile = load_profile(baseline_policy_resolved) if baseline_policy_resolved is not None else None

    run_batch(
        tasks_path=tasks_path_resolved,
        adapter=adapter_for("baseline"),
        out_path=output_paths["baseline_eventlog"],
        instructions=instructions,
        limit=limit,
        repair=bool(repair),
        max_attempts=int(max_attempts),
        budget_usd=budget_usd,
        budget_tokens=budget_tokens,
        rulebook_store=baseline_rulebook_store,
        scale=str(scale),
        k_probe=int(k_probe),
        k_full=int(k_full),
        top_m=int(top_m),
        synth=bool(synth),
        policy_profile=baseline_run_profile,
        seed=int(seed),
    )

    metrics = summarize_jsonl(output_paths["baseline_eventlog"], task_metrics=True)
    flowmap = analyze_flowmap(str(output_paths["baseline_eventlog"]), group_by="bucket_key")
    candidate_policy = suggest_policy(str(output_paths["baseline_eventlog"]), group_by="bucket_key")
    candidate_rulebook = suggest_rules(
        tasks_path=tasks_path_resolved,
        eventlog_path=str(output_paths["baseline_eventlog"]),
    )
    regpack_summary = build_regpack(
        tasks_path=tasks_path_resolved,
        eventlog_path=output_paths["baseline_eventlog"],
        out_path=output_paths["regpack"],
        per_cluster=int(regpack_per_cluster),
        max_total=int(regpack_max_total),
        expand_counterexamples=bool(expand_counterexamples),
        counterexamples_per_cluster=int(regpack_counterexamples_per_cluster),
        seed=int(seed),
    )

    _write_json(output_paths["metrics"], metrics)
    _write_json(output_paths["flowmap"], flowmap)
    _write_json(output_paths["candidate_policy"], candidate_policy)
    _write_json(output_paths["candidate_rulebook"], candidate_rulebook)

    policy_report = run_promotion(
        tasks_path=output_paths["regpack"],
        adapter=adapter_for,
        baseline_profile=baseline_policy,
        candidate_profile=output_paths["candidate_policy"],
        tmp_dir=outdir_path,
        seed=int(seed),
    )
    _write_json(output_paths["policy_report"], policy_report)

    rules_report = run_rule_promotion(
        tasks_path=output_paths["regpack"],
        adapter=adapter_for,
        baseline_rulebook_path=baseline_rulebook_for_gate,
        candidate_rulebook_path=output_paths["candidate_rulebook"],
        policy_profile_path=baseline_policy_resolved,
        tmp_dir=outdir_path,
        seed=int(seed),
    )
    _write_json(output_paths["rules_report"], rules_report)

    policy_deltas = policy_report.get("deltas") if isinstance(policy_report.get("deltas"), Mapping) else {}
    rules_deltas = rules_report.get("deltas") if isinstance(rules_report.get("deltas"), Mapping) else {}
    event_metrics = _mapping(_mapping(metrics).get("event_metrics", metrics))

    policy_ok = bool(policy_report.get("ok"))
    rules_ok = bool(rules_report.get("ok"))

    improved_clusters = _cluster_rows(
        rules_report.get("rule_impact", {}).get("improvements", {}).get("top_clusters_improved")
        if isinstance(rules_report.get("rule_impact"), Mapping)
        else None
    )
    worsened_clusters = _cluster_rows(
        rules_report.get("rule_impact", {}).get("regressions", {}).get("top_clusters_worsened")
        if isinstance(rules_report.get("rule_impact"), Mapping)
        else None
    )
    if not worsened_clusters:
        worsened_clusters = _cluster_rows(rules_report.get("top_worsened_clusters"))

    summary = {
        "ok": policy_ok and rules_ok,
        "gates": {
            "policy": {"ok": policy_ok, "exit_code": int(policy_report.get("exit_code", 1))},
            "rules": {"ok": rules_ok, "exit_code": int(rules_report.get("exit_code", 1))},
        },
        "key_deltas": {
            "task_pass_rate": _as_float(policy_deltas.get("task_pass_rate")),
            "strong_pass_rate": _as_float(rules_deltas.get("strong_pass_rate")),
            "schema_violation_rate": _as_float(
                rules_deltas.get("schema_violation_rate", policy_deltas.get("schema_violation_rate"))
            ),
            "cost_usd_total": _as_float(policy_deltas.get("cost_usd_total")),
        },
        "top_clusters": {
            "improved": improved_clusters[:10],
            "worsened": worsened_clusters[:10],
        },
        "adapter_error_rate": _as_float(event_metrics.get("error_rate")),
        "rate_limit_rate": _as_float(event_metrics.get("rate_limit_rate")),
        "cache_hit_rate": _as_float(event_metrics.get("cache_hit_rate")),
        "files_written": {key: str(path) for key, path in sorted(output_paths.items())},
        "regpack": regpack_summary,
    }
    _write_json(output_paths["summary"], summary)
    return summary


__all__ = ["run_evolve"]
