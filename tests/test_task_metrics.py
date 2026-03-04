from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.cli import main
from rulecraft.metrics.eventlog_metrics import summarize_jsonl


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def test_task_metrics_summary(tmp_path: Path) -> None:
    path = tmp_path / "task_metrics.jsonl"
    _write_jsonl(
        path,
        [
            {
                "trace_id": "trace-a",
                "x_ref": "x-a",
                "bucket_key": "support",
                "selected_rules": [],
                "run": {"mode": "batch", "extra": {"task_id": "task-a", "attempt_idx": 0, "phase": "primary"}},
                "verifier": {"verdict": "FAIL", "outcome": "UNKNOWN", "reason_codes": ["format_leak"]},
                "cost": {"meta": {"backend": "stub", "model": "stub", "cost_usd": 0.0, "error": None}},
            },
            {
                "trace_id": "trace-a",
                "x_ref": "x-a",
                "bucket_key": "support",
                "selected_rules": [],
                "run": {"mode": "batch", "extra": {"task_id": "task-a", "attempt_idx": 1, "phase": "repair"}},
                "verifier": {"verdict": "PASS", "outcome": "OK", "pass": 1},
                "cost": {"meta": {"backend": "stub", "model": "stub", "cost_usd": 0.0, "error": None}},
            },
            {
                "trace_id": "trace-b",
                "x_ref": "x-b",
                "bucket_key": "support",
                "selected_rules": [],
                "run": {"mode": "batch", "extra": {"task_id": "task-b", "attempt_idx": 0, "phase": "primary"}},
                "verifier": {"verdict": "PASS", "outcome": "OK", "pass": 1},
                "cost": {"meta": {"backend": "stub", "model": "stub", "cost_usd": 0.0, "error": None}},
            },
        ],
    )

    summary = summarize_jsonl(path, task_metrics=True)
    task_summary = summary["task_metrics"]

    assert task_summary["tasks_total"] == 2
    assert task_summary["task_pass_rate"] == pytest.approx(1.0)
    assert task_summary["repair_success_rate"] == pytest.approx(0.5)
    assert task_summary["avg_attempts_per_task"] == pytest.approx(1.5)
    assert task_summary["attempts_distribution"] == {"1": 1, "2": 1}


def test_task_metrics_cli_with_group_by(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "task_metrics_grouped.jsonl"
    _write_jsonl(
        path,
        [
            {
                "trace_id": "trace-c",
                "x_ref": "x-c",
                "bucket_key": "support",
                "selected_rules": [],
                "run": {"mode": "batch", "extra": {"task_id": "task-c", "attempt_idx": 0, "phase": "primary"}},
                "verifier": {"verdict": "PASS", "outcome": "OK", "pass": 1},
                "cost": {"meta": {"backend": "stub", "model": "stub", "cost_usd": 0.0, "error": None}},
            }
        ],
    )

    exit_code = main(["metrics", "--path", str(path), "--group-by", "bucket_key", "--task-metrics"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "overall_event_metrics" in payload
    assert "overall_task_metrics" in payload
    assert payload["overall_task_metrics"]["tasks_total"] == 1
    assert payload["by_bucket_key"]["support"]["task_metrics"]["tasks_total"] == 1
