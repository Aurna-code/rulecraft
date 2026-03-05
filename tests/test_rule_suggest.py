from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.cli import main
from rulecraft.rulebook.store import RulebookStore
from rulecraft.rulebook.suggest import suggest_rules


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def _event(
    *,
    trace_id: str,
    task_id: str,
    bucket_key: str,
    reason_codes: list[str] | None,
    violated_constraints: list[str] | None,
    failure_cluster_id: str,
) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "x_ref": f"x-{trace_id}",
        "bucket_key": bucket_key,
        "selected_rules": [],
        "run": {"mode": "batch", "task_id": task_id, "extra": {"task_id": task_id, "attempt_idx": 0, "phase": "primary"}},
        "verifier": {
            "verifier_id": "vf_l1_v1",
            "verdict": "FAIL",
            "outcome": "FAIL",
            "pass": 0,
            "reason_codes": reason_codes,
            "violated_constraints": violated_constraints,
            "failure_cluster_id": failure_cluster_id,
        },
        "cost": {"meta": {"backend": "stub", "model": "stub", "cost_usd": 0.0, "error": None}},
    }


def test_suggest_rules_produces_loadable_rulebook_and_deterministic_ids(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    eventlog_path = tmp_path / "eventlog.jsonl"
    _write_jsonl(
        tasks_path,
        [
            {"task_id": "task-fmt", "prompt": "Return JSON with key status.", "mode": "json", "bucket_key": "alpha"},
            {
                "task_id": "task-schema",
                "prompt": "Return JSON with status and count.",
                "mode": "json",
                "bucket_key": "beta",
                "contract": {
                    "type": "jsonschema",
                    "schema_id": "contract.status_count.v1",
                    "schema": {"type": "object"},
                },
            },
        ],
    )
    _write_jsonl(
        eventlog_path,
        [
            _event(
                trace_id="fmt-1",
                task_id="task-fmt",
                bucket_key="alpha",
                reason_codes=["FORMAT_LEAK", "JSON_PARSE"],
                violated_constraints=["FORMAT:JSON_PARSE"],
                failure_cluster_id="fc_format",
            ),
            _event(
                trace_id="schema-1",
                task_id="task-schema",
                bucket_key="beta",
                reason_codes=["SCHEMA_VIOLATION"],
                violated_constraints=["SCHEMA:JSONSCHEMA:$.count:type"],
                failure_cluster_id="fc_schema",
            ),
        ],
    )

    first = suggest_rules(str(tasks_path), str(eventlog_path), max_rules=20)
    second = suggest_rules(str(tasks_path), str(eventlog_path), max_rules=20)

    first_ids = [rule["rule_id"] for rule in first["rules"]]
    second_ids = [rule["rule_id"] for rule in second["rules"]]
    assert first_ids == second_ids
    assert any(rule_id.startswith("rs_fc_format_") for rule_id in first_ids)
    assert any(rule_id.startswith("rs_fc_schema_") for rule_id in first_ids)

    rulebook_path = tmp_path / "suggested_rulebook.json"
    rulebook_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    store = RulebookStore.load_from_json(rulebook_path)
    assert store.list(status="active")


def test_rule_suggest_cli_writes_summary_and_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tasks_path = tmp_path / "tasks_cli.jsonl"
    eventlog_path = tmp_path / "eventlog_cli.jsonl"
    out_path = tmp_path / "rulebook.json"
    _write_jsonl(
        tasks_path,
        [{"task_id": "task-fmt", "prompt": "Return JSON with key status.", "mode": "json", "bucket_key": "alpha"}],
    )
    _write_jsonl(
        eventlog_path,
        [
            _event(
                trace_id="fmt-cli-1",
                task_id="task-fmt",
                bucket_key="alpha",
                reason_codes=["FORMAT_LEAK"],
                violated_constraints=["FORMAT:JSON_ONLY"],
                failure_cluster_id="fc_format",
            )
        ],
    )

    exit_code = main(
        [
            "rule-suggest",
            "--tasks",
            str(tasks_path),
            "--eventlog",
            str(eventlog_path),
            "--out",
            str(out_path),
        ]
    )
    assert exit_code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["rules"]
    assert "Top templates:" in capsys.readouterr().err
