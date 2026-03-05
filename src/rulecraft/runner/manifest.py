"""Manifest helpers for reproducible evolve/replay runs."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..contracts import SCHEMA_VERSION

MANIFEST_VERSION = 1

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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def detect_git_state(cwd: str | Path | None = None) -> dict[str, Any]:
    root = Path(cwd) if cwd is not None else Path.cwd()
    commit = "unknown"
    dirty = False

    try:
        commit_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
        )
        if commit_proc.returncode == 0:
            commit_candidate = commit_proc.stdout.strip()
            if commit_candidate:
                commit = commit_candidate
    except Exception:
        commit = "unknown"

    try:
        dirty_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
        )
        if dirty_proc.returncode == 0:
            dirty = bool(dirty_proc.stdout.strip())
    except Exception:
        dirty = False

    return {"commit": commit, "dirty": dirty}


def build_manifest(
    *,
    tasks_path: str,
    baseline_policy_profile_path: str | None,
    baseline_rulebook_path: str | None,
    adapter: str,
    run_batch_params: Mapping[str, Any],
    regpack_params: Mapping[str, Any],
    promote_params: Mapping[str, Any],
    promote_rules_params: Mapping[str, Any],
    outputs: Mapping[str, str] | None = None,
    created_utc: str | None = None,
    git_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    output_map = dict(DEFAULT_OUTPUT_FILENAMES)
    if outputs is not None:
        output_map.update(dict(outputs))

    manifest = {
        "version": MANIFEST_VERSION,
        "created_utc": created_utc or _utc_now_iso(),
        "schema_version": SCHEMA_VERSION,
        "git": dict(git_state) if isinstance(git_state, Mapping) else detect_git_state(),
        "inputs": {
            "tasks_path": tasks_path,
            "baseline_policy_profile_path": baseline_policy_profile_path,
            "baseline_rulebook_path": baseline_rulebook_path,
        },
        "params": {
            "adapter": adapter,
            "run_batch": dict(run_batch_params),
            "regpack": dict(regpack_params),
            "promote": dict(promote_params),
            "promote_rules": dict(promote_rules_params),
        },
        "outputs": output_map,
    }
    return manifest


def write_manifest(path: str | Path, manifest: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(dict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_manifest(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Manifest must be a JSON object.")
    return dict(payload)


__all__ = [
    "MANIFEST_VERSION",
    "DEFAULT_OUTPUT_FILENAMES",
    "build_manifest",
    "detect_git_state",
    "load_manifest",
    "write_manifest",
]
