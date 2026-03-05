from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.cli import main
from rulecraft.policy.suggest import suggest_policy


def _event(
    *,
    trace_id: str,
    task_id: str,
    bucket_key: str,
    attempt_idx: int,
    phase: str,
    verdict: str,
    outcome: str,
    pass_value: int,
    reason_codes: list[str] | None = None,
    cost_usd: float = 0.01,
) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "x_ref": f"x-{trace_id}",
        "bucket_key": bucket_key,
        "selected_rules": [],
        "run": {"mode": "batch", "task_id": task_id, "extra": {"task_id": task_id, "attempt_idx": attempt_idx, "phase": phase}},
        "verifier": {
            "verifier_id": "vf_l1_v1",
            "verdict": verdict,
            "outcome": outcome,
            "pass": pass_value,
            "reason_codes": reason_codes,
        },
        "cost": {
            "tokens_in": 10,
            "tokens_out": 10,
            "meta": {"backend": "stub", "model": "stub", "cost_usd": cost_usd, "error": None},
        },
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def test_suggest_policy_heuristics_from_eventlog(tmp_path: Path) -> None:
    path = tmp_path / "eventlog_suggest.jsonl"
    _write_jsonl(
        path,
        [
            _event(
                trace_id="a-0",
                task_id="task-a",
                bucket_key="alpha.fast",
                attempt_idx=0,
                phase="primary",
                verdict="FAIL",
                outcome="UNKNOWN",
                pass_value=0,
                reason_codes=["JSON_PARSE"],
            ),
            _event(
                trace_id="a-1",
                task_id="task-a",
                bucket_key="alpha.fast",
                attempt_idx=1,
                phase="repair",
                verdict="PASS",
                outcome="OK",
                pass_value=1,
                reason_codes=["FIXED"],
            ),
            _event(
                trace_id="b-0",
                task_id="task-b0",
                bucket_key="beta",
                attempt_idx=0,
                phase="primary",
                verdict="FAIL",
                outcome="UNKNOWN",
                pass_value=0,
                reason_codes=["TIMEOUT"],
            ),
            _event(
                trace_id="b-1",
                task_id="task-b1",
                bucket_key="beta",
                attempt_idx=0,
                phase="primary",
                verdict="FAIL",
                outcome="UNKNOWN",
                pass_value=0,
                reason_codes=["TIMEOUT"],
            ),
        ],
    )

    profile = suggest_policy(str(path))
    rules_by_bucket = {rule["bucket_match"]: rule["overrides"] for rule in profile["rules"]}

    assert rules_by_bucket["alpha.fast"]["max_attempts"] >= 2
    assert rules_by_bucket["beta"]["scale"] != "off"


def test_suggest_policy_cli_writes_profile(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    eventlog_path = tmp_path / "eventlog_cli.jsonl"
    out_path = tmp_path / "profile.json"
    _write_jsonl(
        eventlog_path,
        [
            _event(
                trace_id="cli-0",
                task_id="task-cli",
                bucket_key="beta",
                attempt_idx=0,
                phase="primary",
                verdict="FAIL",
                outcome="UNKNOWN",
                pass_value=0,
                reason_codes=["TIMEOUT"],
            )
        ],
    )

    exit_code = main(["suggest-policy", "--path", str(eventlog_path), "--out", str(out_path)])
    assert exit_code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert isinstance(payload["rules"], list)

    stderr = capsys.readouterr().err
    assert "Suggested policy profile" in stderr
