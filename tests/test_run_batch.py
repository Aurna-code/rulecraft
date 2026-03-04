from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.scripted import ScriptedAdapter
from rulecraft.adapters.stub import StubAdapter
from rulecraft.cli import main
from rulecraft.contracts import normalize_eventlog_dict
from rulecraft.metrics.eventlog_metrics import summarize_jsonl
from rulecraft.runner.batch import run_batch
from rulecraft.rulebook.store import RulebookStore

CANONICAL_KEYS = {
    "schema_version",
    "trace_id",
    "x_ref",
    "bucket_key",
    "flow_tags",
    "selected_rules",
    "run",
    "outputs",
    "verifier",
    "cost",
}


def _write_tasks(path: Path) -> None:
    rows = [
        {
            "task_id": "task-text-1",
            "prompt": "Give one sentence of plain text.",
            "mode": "text",
            "bucket_key": "support",
            "flow_tags": ["batch", "text"],
        },
        {
            "task_id": "task-json-fail",
            "prompt": "Return JSON with key status.",
            "mode": "json",
            "bucket_key": "billing",
            "flow_tags": ["batch", "json"],
        },
        {
            "task_id": "task-text-2",
            "prompt": "Summarize this request in one sentence.",
            "mode": "text",
            "bucket_key": None,
            "flow_tags": ["batch"],
        },
    ]
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def test_run_batch_writes_canonical_eventlog_and_metrics(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    out_path = tmp_path / "out.jsonl"
    _write_tasks(tasks_path)

    summary = run_batch(tasks_path=tasks_path, adapter=StubAdapter(mode="text"), out_path=out_path)
    assert summary == {"total": 3, "passed": 2, "failed": 0, "unknown": 1}

    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3

    events_by_task_id: dict[str, dict[str, object]] = {}
    for line in lines:
        payload = json.loads(line)
        assert set(payload.keys()) == CANONICAL_KEYS
        assert payload == normalize_eventlog_dict(payload)
        task_id = payload["run"]["task_id"]
        events_by_task_id[task_id] = payload

    assert events_by_task_id["task-text-1"]["bucket_key"] == "support"
    assert events_by_task_id["task-text-1"]["flow_tags"] == ["batch", "text"]
    assert events_by_task_id["task-json-fail"]["bucket_key"] == "billing"
    assert events_by_task_id["task-json-fail"]["flow_tags"] == ["batch", "json"]
    assert events_by_task_id["task-text-2"]["bucket_key"] is None
    assert events_by_task_id["task-text-2"]["flow_tags"] == ["batch"]
    assert "format_leak" in (events_by_task_id["task-json-fail"]["verifier"]["reason_codes"] or [])

    metrics = summarize_jsonl(out_path)
    assert metrics["total_events"] == 3
    assert metrics["pass_rate"] == pytest.approx(2 / 3)


def test_run_batch_cli_stub_writes_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tasks_path = tmp_path / "tasks_cli.jsonl"
    out_path = tmp_path / "out_cli.jsonl"
    _write_tasks(tasks_path)

    exit_code = main(["run-batch", "--tasks", str(tasks_path), "--adapter", "stub", "--out", str(out_path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 3
    assert len(out_path.read_text(encoding="utf-8").strip().splitlines()) == 3


def test_run_batch_cli_openai_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    exit_code = main(["run-batch", "--tasks", "missing.jsonl", "--adapter", "openai"])
    assert exit_code == 2
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().out


def test_run_batch_budget_router_can_stop_repair_attempts(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_budget.jsonl"
    out_path = tmp_path / "out_budget.jsonl"
    tasks_path.write_text(
        json.dumps({"task_id": "task-budget", "prompt": "Return JSON.", "mode": "json"}) + "\n",
        encoding="utf-8",
    )
    adapter = ScriptedAdapter(scripts={"task-budget": ["not-json", '{"status":"ok"}']})

    summary = run_batch(
        tasks_path=tasks_path,
        adapter=adapter,
        out_path=out_path,
        repair=True,
        max_attempts=3,
        budget_tokens=0,
    )

    assert summary == {"total": 1, "passed": 0, "failed": 0, "unknown": 1}
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_run_batch_rulebook_selects_and_injects_context(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_rulebook.jsonl"
    out_path = tmp_path / "out_rulebook.jsonl"
    tasks_path.write_text(
        json.dumps(
            {
                "task_id": "task-rulebook",
                "prompt": "The customer asked about card replacement and card number safety.",
                "mode": "text",
                "bucket_key": "support",
                "flow_tags": ["payments", "safety"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    store = RulebookStore.load_from_json(ROOT / "rules" / "sample_rulebook.json")
    adapter = ScriptedAdapter(scripts={"task-rulebook": ["safe response"]})

    summary = run_batch(tasks_path=tasks_path, adapter=adapter, out_path=out_path, rulebook_store=store)
    assert summary == {"total": 1, "passed": 1, "failed": 0, "unknown": 0}

    assert adapter.calls
    assert "Rulecraft Context" in adapter.calls[0]["prompt"]

    payload = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert payload["selected_rules"]
    for rule in payload["selected_rules"]:
        assert set(rule.keys()) == {"rule_id", "version", "type"}
