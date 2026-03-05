from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.analysis.regpack import build_regpack
from rulecraft.cli import main


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def _event(
    *,
    trace_id: str,
    task_id: str,
    bucket_key: str | None,
    verdict: str,
    outcome: str,
    pass_value: int,
    failure_cluster_id: str | None = None,
) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "x_ref": f"x-{trace_id}",
        "bucket_key": bucket_key,
        "selected_rules": [],
        "run": {"mode": "batch", "task_id": task_id, "extra": {"task_id": task_id, "attempt_idx": 0, "phase": "primary"}},
        "verifier": {
            "verifier_id": "vf_l1_v1",
            "verdict": verdict,
            "outcome": outcome,
            "pass": pass_value,
            "failure_cluster_id": failure_cluster_id,
        },
        "cost": {"meta": {"backend": "stub", "model": "stub", "cost_usd": 0.0, "error": None}},
    }


def test_build_regpack_selects_failure_clusters_and_pass_sample(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    eventlog_path = tmp_path / "eventlog.jsonl"
    out_path = tmp_path / "regpack.jsonl"

    _write_jsonl(
        tasks_path,
        [
            {"task_id": "task-a0", "prompt": "A0", "mode": "json", "bucket_key": "alpha", "flow_tags": ["x"]},
            {"task_id": "task-a1", "prompt": "A1", "mode": "json", "bucket_key": "alpha", "flow_tags": ["x"]},
            {"task_id": "task-b0", "prompt": "B0", "mode": "json", "bucket_key": "beta", "flow_tags": ["y"]},
            {"task_id": "task-b1", "prompt": "B1", "mode": "text", "bucket_key": "beta", "flow_tags": ["y"]},
        ],
    )
    _write_jsonl(
        eventlog_path,
        [
            _event(
                trace_id="e-a0",
                task_id="task-a0",
                bucket_key="alpha",
                verdict="FAIL",
                outcome="FAIL",
                pass_value=0,
                failure_cluster_id="fc_parse",
            ),
            _event(
                trace_id="e-a1",
                task_id="task-a1",
                bucket_key="alpha",
                verdict="FAIL",
                outcome="UNKNOWN",
                pass_value=0,
                failure_cluster_id="fc_parse",
            ),
            _event(
                trace_id="e-b0",
                task_id="task-b0",
                bucket_key="beta",
                verdict="FAIL",
                outcome="FAIL",
                pass_value=0,
                failure_cluster_id="fc_schema",
            ),
            _event(
                trace_id="e-b1",
                task_id="task-b1",
                bucket_key="beta",
                verdict="PASS",
                outcome="OK",
                pass_value=1,
            ),
        ],
    )

    summary = build_regpack(tasks_path, eventlog_path, out_path, per_cluster=1, max_total=10)
    assert summary["clusters_total"] == 2
    assert summary["selected_total"] >= 3
    assert summary["pass_bucket_samples"] >= 1

    selected_rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").strip().splitlines()]
    selected_ids = {row["task_id"] for row in selected_rows}
    assert "task-a0" in selected_ids or "task-a1" in selected_ids
    assert "task-b0" in selected_ids
    assert "task-b1" in selected_ids


def test_regpack_cli_writes_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tasks_path = tmp_path / "tasks_cli.jsonl"
    eventlog_path = tmp_path / "eventlog_cli.jsonl"
    out_path = tmp_path / "regpack_cli.jsonl"
    _write_jsonl(tasks_path, [{"task_id": "task-1", "prompt": "x", "mode": "text", "bucket_key": "alpha"}])
    _write_jsonl(
        eventlog_path,
        [_event(trace_id="cli-1", task_id="task-1", bucket_key="alpha", verdict="PASS", outcome="OK", pass_value=1)],
    )

    exit_code = main(
        [
            "regpack",
            "--tasks",
            str(tasks_path),
            "--eventlog",
            str(eventlog_path),
            "--out",
            str(out_path),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selected_total"] == 1
    assert out_path.exists()


def test_regpack_counterexample_expansion_increases_output_and_caps_total(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_expand.jsonl"
    eventlog_path = tmp_path / "eventlog_expand.jsonl"
    base_out = tmp_path / "regpack_base.jsonl"
    expanded_out = tmp_path / "regpack_expand.jsonl"

    _write_jsonl(
        tasks_path,
        [
            {"task_id": "task-a0", "prompt": "Return JSON for alpha.", "mode": "json", "bucket_key": "alpha"},
            {"task_id": "task-b0", "prompt": "Return JSON for beta.", "mode": "json", "bucket_key": "beta"},
            {"task_id": "task-pass", "prompt": "One short sentence.", "mode": "text", "bucket_key": "beta"},
        ],
    )
    _write_jsonl(
        eventlog_path,
        [
            _event(
                trace_id="ex-a0",
                task_id="task-a0",
                bucket_key="alpha",
                verdict="FAIL",
                outcome="FAIL",
                pass_value=0,
                failure_cluster_id="fc_parse",
            ),
            _event(
                trace_id="ex-b0",
                task_id="task-b0",
                bucket_key="beta",
                verdict="FAIL",
                outcome="FAIL",
                pass_value=0,
                failure_cluster_id="fc_schema",
            ),
            _event(
                trace_id="ex-pass",
                task_id="task-pass",
                bucket_key="beta",
                verdict="PASS",
                outcome="OK",
                pass_value=1,
            ),
        ],
    )

    base_summary = build_regpack(tasks_path, eventlog_path, base_out, per_cluster=1, max_total=20)
    expanded_summary = build_regpack(
        tasks_path,
        eventlog_path,
        expanded_out,
        per_cluster=1,
        max_total=5,
        expand_counterexamples=True,
        counterexamples_per_cluster=2,
        seed=1337,
    )

    base_rows = [json.loads(line) for line in base_out.read_text(encoding="utf-8").strip().splitlines()]
    expanded_rows = [json.loads(line) for line in expanded_out.read_text(encoding="utf-8").strip().splitlines()]

    assert expanded_summary["counterexamples_added"] > 0
    assert expanded_summary["selected_total"] == len(expanded_rows)
    assert expanded_summary["selected_total"] <= 5
    assert len(expanded_rows) >= len(base_rows)
    assert any("__ce_" in row["task_id"] for row in expanded_rows)
