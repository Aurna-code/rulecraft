from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.cli import main
from rulecraft.rulebook.prune import compute_rule_stats, prune_rulebook
from rulecraft.rulebook.store import RulebookStore


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def _rulebook_payload() -> dict[str, object]:
    return {
        "rulebook_name": "Rulebook",
        "rules": [
            {
                "rule_id": "A",
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "body": "Strategy A.",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 1},
            },
            {
                "rule_id": "B",
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "body": "Strategy B.",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 2},
            },
            {
                "rule_id": "C",
                "version": "0.1.0",
                "type": "FormatRule",
                "status": "active",
                "body": "Output JSON only.",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 3},
            },
            {
                "rule_id": "D",
                "version": "0.1.0",
                "type": "SchemaRule",
                "status": "active",
                "body": "Match schema.",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 4},
            },
        ],
    }


def _event(*, trace: str, task_id: str, selected_rule_ids: list[str], strong_pass: bool) -> dict[str, object]:
    selected_rules = [{"rule_id": rid, "version": "0.1.0", "type": "StrategyRule"} for rid in selected_rule_ids]
    if strong_pass:
        verifier = {"verdict": "PASS", "outcome": "OK", "pass": 1}
    else:
        verifier = {"verdict": "FAIL", "outcome": "UNKNOWN", "pass": 0}
    return {
        "trace_id": trace,
        "x_ref": f"x-{trace}",
        "selected_rules": selected_rules,
        "run": {"task_id": task_id, "extra": {"task_id": task_id, "attempt_idx": 0, "phase": "primary"}},
        "verifier": verifier,
        "cost": {"meta": {"backend": "stub", "model": "stub", "cost_usd": 0.01, "error": None}},
    }


def test_prune_rulebook_drops_unused_rules_and_keeps_safety_if_used(tmp_path: Path) -> None:
    rulebook = _rulebook_payload()
    eventlog_path = tmp_path / "eventlog.jsonl"
    _write_jsonl(
        eventlog_path,
        [
            _event(trace="e1", task_id="t1", selected_rule_ids=["A", "C"], strong_pass=True),
            _event(trace="e2", task_id="t2", selected_rule_ids=["A"], strong_pass=False),
            _event(trace="e3", task_id="t3", selected_rule_ids=["A"], strong_pass=True),
        ],
    )

    stats = compute_rule_stats(rulebook, str(eventlog_path))
    pruned, plan = prune_rulebook(rulebook, stats, min_selected=2, min_impact=None, max_remove=None)

    kept_ids = [row["rule_id"] for row in pruned["rules"]]
    assert "A" in kept_ids
    assert "C" in kept_ids  # FormatRule in use: keep
    assert "B" not in kept_ids  # Unused strategy: prune
    assert "D" not in kept_ids  # Unused safety rule: prune allowed
    assert "B" in plan["removed_rule_ids"]
    assert "D" in plan["removed_rule_ids"]


def test_rule_prune_cli_writes_loadable_rulebook_and_supports_dry_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rulebook_path = tmp_path / "rulebook.json"
    eventlog_path = tmp_path / "eventlog.jsonl"
    out_path = tmp_path / "pruned_rulebook.json"
    _write_json(rulebook_path, _rulebook_payload())
    _write_jsonl(
        eventlog_path,
        [
            _event(trace="e1", task_id="t1", selected_rule_ids=["A"], strong_pass=True),
            _event(trace="e2", task_id="t2", selected_rule_ids=["A"], strong_pass=False),
            _event(trace="e3", task_id="t3", selected_rule_ids=["A"], strong_pass=True),
        ],
    )

    exit_code = main(
        [
            "rule-prune",
            "--rulebook",
            str(rulebook_path),
            "--eventlog",
            str(eventlog_path),
            "--out",
            str(out_path),
            "--min-selected",
            "2",
        ]
    )
    assert exit_code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    store = RulebookStore.load_from_json(out_path)
    assert store.list()
    assert isinstance(payload["rules"], list)

    dry_run_out = tmp_path / "dry_run_rulebook.json"
    exit_code = main(
        [
            "rule-prune",
            "--rulebook",
            str(rulebook_path),
            "--eventlog",
            str(eventlog_path),
            "--out",
            str(dry_run_out),
            "--dry-run",
        ]
    )
    assert exit_code == 0
    assert not dry_run_out.exists()
    assert "rule-prune plan" in capsys.readouterr().err
