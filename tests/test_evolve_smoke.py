from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.cli import main


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def test_evolve_smoke_creates_expected_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    outdir = tmp_path / "run1"
    _write_jsonl(
        tasks_path,
        [
            {"task_id": "task-json", "prompt": "Return JSON status.", "mode": "json", "bucket_key": "alpha"},
            {"task_id": "task-text", "prompt": "One short sentence.", "mode": "text", "bucket_key": "alpha"},
        ],
    )

    exit_code = main(
        [
            "evolve",
            "--tasks",
            str(tasks_path),
            "--adapter",
            "stub",
            "--outdir",
            str(outdir),
        ]
    )
    assert exit_code == 0

    expected_files = [
        "manifest.json",
        "baseline.jsonl",
        "metrics.json",
        "flowmap.json",
        "candidate_policy.json",
        "candidate_rulebook.json",
        "regpack.jsonl",
        "policy_promote_report.json",
        "rules_promote_report.json",
        "summary.json",
    ]
    for rel_path in expected_files:
        assert (outdir / rel_path).exists(), rel_path

    summary = json.loads((outdir / "summary.json").read_text(encoding="utf-8"))
    assert set(summary.keys()) >= {
        "ok",
        "gates",
        "key_deltas",
        "top_clusters",
        "adapter_error_rate",
        "rate_limit_rate",
        "cache_hit_rate",
        "files_written",
    }
    assert set(summary["gates"].keys()) == {"policy", "rules"}
    assert set(summary["key_deltas"].keys()) >= {
        "task_pass_rate",
        "strong_pass_rate",
        "schema_violation_rate",
        "cost_usd_total",
    }
    assert set(summary["top_clusters"].keys()) == {"improved", "worsened"}
    assert isinstance(summary["adapter_error_rate"], (int, float))
    assert isinstance(summary["rate_limit_rate"], (int, float))
    assert isinstance(summary["cache_hit_rate"], (int, float))

    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["inputs"]["tasks_path"] == str(tasks_path.resolve())
    assert manifest["params"]["adapter"] == "stub"

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload["gates"]["policy"]["ok"] in {True, False}
