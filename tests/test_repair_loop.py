from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.scripted import ScriptedAdapter
from rulecraft.policy.repair_loop import build_repair_prompt
from rulecraft.runner.batch import run_batch


def test_run_batch_repair_loop_writes_two_attempts_with_metadata(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    out_path = tmp_path / "eventlog.jsonl"

    tasks_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "task-repair-1",
                        "prompt": "Return JSON with key status.",
                        "mode": "json",
                        "bucket_key": "support",
                        "flow_tags": ["repair"],
                    }
                )
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    adapter = ScriptedAdapter(
        scripts={
            "task-repair-1": [
                "not json",
                '{"status":"ok"}',
            ]
        }
    )

    summary = run_batch(
        tasks_path=tasks_path,
        adapter=adapter,
        out_path=out_path,
        repair=True,
        max_attempts=2,
    )

    assert summary == {"total": 1, "passed": 1, "failed": 0, "unknown": 0}

    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])

    assert first["trace_id"] == second["trace_id"]
    assert first["verifier"]["verdict"] == "FAIL"
    assert first["verifier"]["outcome"] == "UNKNOWN"
    assert second["verifier"]["verdict"] == "PASS"
    assert second["verifier"]["outcome"] == "OK"

    assert first["run"]["extra"]["task_id"] == "task-repair-1"
    assert first["run"]["extra"]["attempt_idx"] == 0
    assert first["run"]["extra"]["phase"] == "primary"

    assert second["run"]["extra"]["task_id"] == "task-repair-1"
    assert second["run"]["extra"]["attempt_idx"] == 1
    assert second["run"]["extra"]["phase"] == "repair"


def test_build_repair_prompt_includes_contract_violation_hint() -> None:
    prompt, instructions = build_repair_prompt(
        task_prompt="Return JSON with status and count.",
        mode="json",
        last_output='{"status":"ok","count":"1"}',
        verifier={
            "verdict": "FAIL",
            "outcome": "FAIL",
            "reason_codes": ["SCHEMA_VIOLATION"],
            "violated_constraints": ["SCHEMA:JSONSCHEMA:$.count:type"],
        },
    )

    assert instructions == "Return JSON that satisfies the contract. Output JSON only."
    assert "Contract violations:" in prompt
    assert "SCHEMA:JSONSCHEMA:$.count:type" in prompt
