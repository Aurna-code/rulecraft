from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.cli import main
from rulecraft.runner.evolve import run_evolve
from rulecraft.runner.replay import run_replay


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def test_replay_matches_key_summary_stats(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    run_dir = tmp_path / "run1"
    _write_jsonl(
        tasks_path,
        [
            {"task_id": "task-json-1", "prompt": "Return JSON with status.", "mode": "json", "bucket_key": "alpha"},
            {"task_id": "task-json-2", "prompt": "Return JSON with id.", "mode": "json", "bucket_key": "alpha"},
            {"task_id": "task-text-1", "prompt": "One short sentence.", "mode": "text", "bucket_key": "alpha"},
        ],
    )

    first_summary = run_evolve(
        outdir=str(run_dir),
        tasks_path=str(tasks_path),
        adapter="stub",
        scale="probe",
        expand_counterexamples=True,
        seed=77,
    )

    replay_summary = run_replay(manifest_path=str(run_dir / "manifest.json"))
    replay_outdir = run_dir / "replay"

    assert (replay_outdir / "summary.json").exists()
    assert first_summary["key_deltas"]["task_pass_rate"] == pytest.approx(replay_summary["key_deltas"]["task_pass_rate"])
    assert first_summary["key_deltas"]["strong_pass_rate"] == pytest.approx(
        replay_summary["key_deltas"]["strong_pass_rate"]
    )
    assert first_summary["key_deltas"]["schema_violation_rate"] == pytest.approx(
        replay_summary["key_deltas"]["schema_violation_rate"]
    )
    assert first_summary["top_clusters"]["improved"] == replay_summary["top_clusters"]["improved"]
    assert first_summary["top_clusters"]["worsened"] == replay_summary["top_clusters"]["worsened"]

    replay_cli_dir = run_dir / "replay_cli"
    exit_code = main(["replay", "--manifest", str(run_dir / "manifest.json"), "--outdir", str(replay_cli_dir)])
    assert exit_code == 0
    assert (replay_cli_dir / "summary.json").exists()
