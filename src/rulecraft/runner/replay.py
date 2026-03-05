"""Manifest-driven replay runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .evolve import run_evolve
from .manifest import load_manifest


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_str_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def run_replay(manifest_path: str, outdir: str | None = None) -> dict[str, Any]:
    """Replay an evolve run from a manifest."""
    manifest_target = Path(manifest_path).resolve()
    manifest = load_manifest(manifest_target)

    inputs = manifest.get("inputs")
    params = manifest.get("params")
    if not isinstance(inputs, Mapping) or not isinstance(params, Mapping):
        raise ValueError("Manifest is missing required inputs/params sections.")

    run_batch_params = params.get("run_batch")
    regpack_params = params.get("regpack")
    promote_params = params.get("promote")
    promote_rules_params = params.get("promote_rules")
    if not isinstance(run_batch_params, Mapping):
        run_batch_params = {}
    if not isinstance(regpack_params, Mapping):
        regpack_params = {}
    if not isinstance(promote_params, Mapping):
        promote_params = {}
    if not isinstance(promote_rules_params, Mapping):
        promote_rules_params = {}

    adapter = str(params.get("adapter", "stub"))
    replay_outdir = Path(outdir).resolve() if outdir is not None else manifest_target.parent / "replay"
    scripted_adapter = params.get("scripted_adapter")
    if not isinstance(scripted_adapter, Mapping):
        scripted_adapter = None

    seed = _as_int(
        run_batch_params.get("seed"),
        _as_int(regpack_params.get("seed"), _as_int(promote_params.get("seed"), _as_int(promote_rules_params.get("seed"), 1337))),
    )
    fail_on_regression = _as_bool(promote_params.get("fail_on_regression"), False) or _as_bool(
        promote_rules_params.get("fail_on_regression"),
        False,
    )

    return run_evolve(
        outdir=str(replay_outdir),
        tasks_path=str(inputs.get("tasks_path", "")),
        adapter=adapter,
        baseline_policy_profile_path=_as_str_or_none(inputs.get("baseline_policy_profile_path")),
        baseline_rulebook_path=_as_str_or_none(inputs.get("baseline_rulebook_path")),
        scale=str(run_batch_params.get("scale", "off")),
        repair=_as_bool(run_batch_params.get("repair"), False),
        max_attempts=_as_int(run_batch_params.get("max_attempts"), 1),
        expand_counterexamples=_as_bool(regpack_params.get("expand_counterexamples"), False),
        seed=seed,
        fail_on_regression=fail_on_regression,
        limit=_as_int(run_batch_params.get("limit"), 0) if run_batch_params.get("limit") is not None else None,
        instructions=_as_str_or_none(run_batch_params.get("instructions")),
        budget_usd=_as_float_or_none(run_batch_params.get("budget_usd")),
        budget_tokens=(
            _as_int(run_batch_params.get("budget_tokens"), 0) if run_batch_params.get("budget_tokens") is not None else None
        ),
        k_probe=_as_int(run_batch_params.get("k_probe"), 3),
        k_full=_as_int(run_batch_params.get("k_full"), 8),
        top_m=_as_int(run_batch_params.get("top_m"), 2),
        synth=_as_bool(run_batch_params.get("synth"), True),
        regpack_per_cluster=_as_int(regpack_params.get("per_cluster"), 2),
        regpack_max_total=_as_int(regpack_params.get("max_total"), 100),
        regpack_counterexamples_per_cluster=_as_int(regpack_params.get("counterexamples_per_cluster"), 2),
        scripted_adapter=dict(scripted_adapter) if isinstance(scripted_adapter, Mapping) else None,
    )


__all__ = ["run_replay"]
