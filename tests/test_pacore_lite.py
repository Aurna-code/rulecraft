from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.scripted import ScriptedAdapter
from rulecraft.runner.batch import run_batch


def _write_single_json_task(path: Path, task_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "prompt": "Return JSON with key status.",
                "mode": "json",
                "bucket_key": "support",
                "flow_tags": ["batch", "scale"],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _load_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").strip().splitlines()]


def test_probe_success_skips_full_rollout(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_probe_success.jsonl"
    out_path = tmp_path / "eventlog_probe_success.jsonl"
    _write_single_json_task(tasks_path, task_id="task-probe-success")

    adapter = ScriptedAdapter(
        scripts={"task-probe-success": ["not-json"]},
        phase_scripts={
            "task-probe-success": {
                "scale_probe_candidate": ['{"status":"ok"}', "still-not-json", "still-not-json-2"],
            }
        },
    )

    summary = run_batch(
        tasks_path=tasks_path,
        adapter=adapter,
        out_path=out_path,
        scale="probe",
        k_probe=3,
        top_m=2,
        synth=False,
    )
    assert summary == {"total": 1, "passed": 1, "failed": 0, "unknown": 0}

    events = _load_events(out_path)
    phases = [event["run"]["extra"]["phase"] for event in events]
    assert phases == ["primary", "scale_probe"]

    probe_event = events[-1]
    assert probe_event["run"]["extra"]["scale"]["k"] == 3
    assert probe_event["run"]["extra"]["scale"]["top_m"] == 2
    assert probe_event["run"]["extra"]["scale"]["used_synth"] is False
    assert "candidate_verdict_counts" in probe_event["outputs"]["rollout"]
    assert "candidates" not in probe_event["outputs"]["rollout"]


def test_probe_failure_escalates_to_full_and_succeeds(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_probe_to_full.jsonl"
    out_path = tmp_path / "eventlog_probe_to_full.jsonl"
    _write_single_json_task(tasks_path, task_id="task-probe-to-full")

    adapter = ScriptedAdapter(
        scripts={"task-probe-to-full": ["not-json"]},
        phase_scripts={
            "task-probe-to-full": {
                "scale_probe_candidate": ["bad-a", "bad-b"],
                "scale_full_candidate": ["bad-c", '{"status":"ok"}', "bad-d", "bad-e"],
            }
        },
    )

    summary = run_batch(
        tasks_path=tasks_path,
        adapter=adapter,
        out_path=out_path,
        scale="probe",
        k_probe=2,
        k_full=4,
        top_m=2,
        synth=False,
    )
    assert summary == {"total": 1, "passed": 1, "failed": 0, "unknown": 0}

    events = _load_events(out_path)
    phases = [event["run"]["extra"]["phase"] for event in events]
    assert phases == ["primary", "scale_probe", "scale_full"]

    probe_event = events[1]
    assert probe_event["verifier"]["verdict"] == "FAIL"
    assert probe_event["run"]["extra"]["scale"]["k"] == 2
    assert probe_event["outputs"]["rollout"]["candidate_verdict_counts"]

    full_event = events[2]
    assert full_event["verifier"]["verdict"] == "PASS"
    assert full_event["verifier"]["outcome"] == "OK"
    assert full_event["run"]["extra"]["scale"]["k"] == 4
    assert full_event["outputs"]["rollout"]["candidate_verdict_counts"]


def test_budget_can_block_full_after_probe(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_budget_block.jsonl"
    out_path = tmp_path / "eventlog_budget_block.jsonl"
    _write_single_json_task(tasks_path, task_id="task-budget-block")

    adapter = ScriptedAdapter(
        scripts={"task-budget-block": ["not-json"]},
        phase_scripts={
            "task-budget-block": {
                "scale_probe_candidate": ["bad-a", "bad-b"],
                "scale_full_candidate": ['{"status":"ok"}'],
            }
        },
    )

    summary = run_batch(
        tasks_path=tasks_path,
        adapter=adapter,
        out_path=out_path,
        scale="probe",
        k_probe=2,
        k_full=4,
        top_m=2,
        synth=False,
        budget_tokens=1,
    )
    assert summary == {"total": 1, "passed": 0, "failed": 0, "unknown": 1}

    events = _load_events(out_path)
    phases = [event["run"]["extra"]["phase"] for event in events]
    assert phases == ["primary", "scale_probe"]

    probe_event = events[-1]
    assert probe_event["run"]["extra"]["scale"]["k"] == 2
    assert probe_event["run"]["extra"]["scale"]["top_m"] == 2
    assert probe_event["run"]["extra"]["scale"]["used_synth"] is False
