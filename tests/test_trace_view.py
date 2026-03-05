from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.analysis.trace_view import render_task_trace
from rulecraft.cli import main
from rulecraft.contracts import SCHEMA_VERSION


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def _event(
    *,
    trace_id: str,
    task_id: str,
    attempt_idx: int,
    phase: str,
    verdict: str,
    outcome: str,
    reason_codes: list[str] | None,
    violated_constraints: list[str] | None,
    failure_cluster_id: str | None,
    cost_usd: float,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "x_ref": f"x-{trace_id}",
        "bucket_key": "alpha",
        "flow_tags": ["batch"],
        "selected_rules": [
            {"rule_id": "RULE-1", "version": "1", "type": "GuardrailRule"},
            {"rule_id": "RULE-2", "version": "1", "type": "StrategyRule"},
        ],
        "run": {
            "mode": "batch",
            "task_id": task_id,
            "extra": {
                "task_id": task_id,
                "attempt_idx": attempt_idx,
                "phase": phase,
            },
        },
        "outputs": {"task_id": task_id},
        "verifier": {
            "verifier_id": "vf_l1_v1",
            "verdict": verdict,
            "outcome": outcome,
            "reason_codes": reason_codes,
            "violated_constraints": violated_constraints,
            "failure_cluster_id": failure_cluster_id,
            "pass": 1 if verdict == "PASS" and outcome != "FAIL" else 0,
            "layers": {"l1": {"verdict": verdict, "outcome": outcome, "reason_codes": reason_codes}},
        },
        "cost": {
            "latency_ms": 12,
            "tokens_in": 10,
            "tokens_out": 5,
            "tool_calls": 0,
            "meta": {
                "backend": "stub",
                "model": "stub",
                "cost_usd": cost_usd,
                "error": None,
                "error_class": None,
                "status_code": None,
                "attempts": 1,
                "retries": 0,
                "retry_sleep_s_total": 0.0,
            },
        },
    }


def test_render_task_trace_outputs_sorted_timeline(tmp_path: Path) -> None:
    path = tmp_path / "eventlog.jsonl"
    _write_jsonl(
        path,
        [
            _event(
                trace_id="t-repair",
                task_id="task-1",
                attempt_idx=1,
                phase="repair",
                verdict="FAIL",
                outcome="UNKNOWN",
                reason_codes=["FORMAT_LEAK"],
                violated_constraints=["FORMAT:JSON_PARSE"],
                failure_cluster_id="format_cluster",
                cost_usd=0.002,
            ),
            _event(
                trace_id="t-other",
                task_id="task-2",
                attempt_idx=0,
                phase="primary",
                verdict="PASS",
                outcome="OK",
                reason_codes=None,
                violated_constraints=None,
                failure_cluster_id=None,
                cost_usd=0.001,
            ),
            _event(
                trace_id="t-primary",
                task_id="task-1",
                attempt_idx=0,
                phase="primary",
                verdict="FAIL",
                outcome="FAIL",
                reason_codes=["SCHEMA_VIOLATION"],
                violated_constraints=["SCHEMA:TYPE_MISMATCH"],
                failure_cluster_id="schema_cluster",
                cost_usd=0.003,
            ),
            _event(
                trace_id="t-probe",
                task_id="task-1",
                attempt_idx=2,
                phase="scale_probe",
                verdict="PASS",
                outcome="OK",
                reason_codes=None,
                violated_constraints=None,
                failure_cluster_id=None,
                cost_usd=0.004,
            ),
        ],
    )

    rendered = render_task_trace(str(path), "task-1")
    assert "Task Trace: task-1" in rendered
    assert "Events: 3" in rendered

    primary_pos = rendered.index("attempt=0 phase=primary")
    repair_pos = rendered.index("attempt=1 phase=repair")
    probe_pos = rendered.index("attempt=2 phase=scale_probe")
    assert primary_pos < repair_pos < probe_pos

    assert "reason_codes=SCHEMA_VIOLATION" in rendered
    assert "violated_constraints=SCHEMA:TYPE_MISMATCH" in rendered
    assert "failure_cluster_id=schema_cluster" in rendered
    assert "selected_rules=RULE-1,RULE-2" in rendered
    assert "cost=latency_ms=12 tokens=10/5 cost_usd=0.003000" in rendered


def test_trace_cli_supports_max_lines(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "eventlog_cli.jsonl"
    _write_jsonl(
        path,
        [
            _event(
                trace_id="t-primary",
                task_id="task-cli",
                attempt_idx=0,
                phase="primary",
                verdict="PASS",
                outcome="OK",
                reason_codes=None,
                violated_constraints=None,
                failure_cluster_id=None,
                cost_usd=0.001,
            )
        ],
    )

    exit_code = main(["trace", "--path", str(path), "--task-id", "task-cli", "--max-lines", "2"])
    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert lines[0] == "Task Trace: task-cli"

