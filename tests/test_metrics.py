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


def test_metrics_summary_handles_mixed_shapes(tmp_path: Path) -> None:
    eventlog_path = tmp_path / "eventlog.jsonl"
    _write_jsonl(
        eventlog_path,
        [
            {
                "trace_id": "t1",
                "x_ref": "x1",
                "selected_rules": [],
                "verifier": {
                    "verifier_id": "vf_l1_v1",
                    "verdict": "PASS",
                    "outcome": "OK",
                    "reason_codes": ["ok"],
                    "violated_constraints": None,
                    "pass": 1,
                },
                "cost": {
                    "latency_ms": 10,
                    "tokens_in": 100,
                    "tokens_out": 50,
                    "tool_calls": 0,
                    "meta": {"backend": "stub", "model": "stub", "cost_usd": 0.01, "error": None},
                },
            },
            {
                "trace_id": "t2",
                "x_ref": "x2",
                "selected_rules": ["RULE-1"],
                "verdict": "FAIL",
                "outcome": "UNKNOWN",
                "verifier": {
                    "reason_codes": ["format_leak"],
                    "violated_constraints": ["json_parse"],
                },
                "cost": {
                    "backend": "openai",
                    "model": "gpt-5-mini",
                    "latency_ms": 30,
                    "tokens_in": 70,
                    "tokens_out": 20,
                    "cost_usd": 0.002,
                    "error": "timeout",
                },
            },
            {
                "trace_id": "t3",
                "x_ref": "x3",
                "selected_rules": [],
                "verifier": {
                    "verdict": "PARTIAL",
                    "outcome": "UNKNOWN",
                    "reason_codes": ["length_violation"],
                    "violated_constraints": ["FORMAT:LENGTH_LTE"],
                },
                "cost": {
                    "meta": {"backend": "stub", "model": "stub", "cost_usd": 0.003, "error": None},
                },
            },
        ],
    )

    summary = summarize_jsonl(eventlog_path)

    assert summary["total_events"] == 3
    assert summary["pass_rate"] == pytest.approx(1 / 3)
    assert summary["unknown_rate"] == pytest.approx(2 / 3)
    assert summary["counts_by_verdict"] == {"PASS": 1, "FAIL": 1, "PARTIAL": 1}
    assert summary["counts_by_outcome"] == {"OK": 1, "UNKNOWN": 2}
    assert summary["latency_ms_p50"] is not None
    assert summary["latency_ms_p95"] is not None
    assert summary["tokens_in_total"] == 170
    assert summary["tokens_out_total"] == 70
    assert summary["cost_usd_total"] == pytest.approx(0.015)


def test_metrics_cli_prints_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    eventlog_path = tmp_path / "eventlog.jsonl"
    _write_jsonl(
        eventlog_path,
        [
            {
                "trace_id": "trace-cli",
                "x_ref": "x-cli",
                "selected_rules": [],
                "verifier": {"verdict": "PASS", "outcome": "OK"},
                "cost": {"meta": {"backend": "stub", "model": "stub", "cost_usd": 0.0, "error": None}},
            }
        ],
    )

    exit_code = main(["metrics", "--path", str(eventlog_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["total_events"] == 1
