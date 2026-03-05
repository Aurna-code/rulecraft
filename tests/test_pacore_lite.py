from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.scripted import ScriptedAdapter
from rulecraft.contracts import VerifierResult
from rulecraft.runner import batch as batch_runner
from rulecraft.runner.batch import estimate_full_cost_usd
from rulecraft.runner.batch import run_batch
from rulecraft.runner.pacore_lite import run_pacore_lite


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


def test_probe_pass_unknown_escalates_to_full_when_budget_allows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_path = tmp_path / "tasks_probe_pass_unknown.jsonl"
    out_path = tmp_path / "eventlog_probe_pass_unknown.jsonl"
    _write_single_json_task(tasks_path, task_id="task-probe-pass-unknown")

    original_verify_text = batch_runner.verify_text

    def _verify_text_with_weak_probe(task_mode: str, y: str) -> VerifierResult:
        if y == "probe-weak-pass":
            return VerifierResult(verdict="PASS", outcome="UNKNOWN", reason_codes=None, violated_constraints=None)
        if y == "full-strong-pass":
            return VerifierResult(verdict="PASS", outcome="OK", reason_codes=None, violated_constraints=None)
        return original_verify_text(task_mode=task_mode, y=y)

    monkeypatch.setattr(batch_runner, "verify_text", _verify_text_with_weak_probe)

    adapter = ScriptedAdapter(
        scripts={"task-probe-pass-unknown": ["not-json"]},
        phase_scripts={
            "task-probe-pass-unknown": {
                "scale_probe_candidate": ["probe-weak-pass", "not-json-probe"],
                "scale_full_candidate": ["full-strong-pass", "not-json-full"],
            }
        },
    )

    summary = run_batch(
        tasks_path=tasks_path,
        adapter=adapter,
        out_path=out_path,
        scale="probe",
        k_probe=2,
        k_full=2,
        top_m=2,
        synth=False,
        budget_usd=1.0,
    )
    assert summary == {"total": 1, "passed": 1, "failed": 0, "unknown": 0}

    events = _load_events(out_path)
    phases = [event["run"]["extra"]["phase"] for event in events]
    assert phases == ["primary", "scale_probe", "scale_full"]
    assert events[1]["verifier"]["verdict"] == "PASS"
    assert events[1]["verifier"]["outcome"] == "UNKNOWN"
    assert events[2]["verifier"]["verdict"] == "PASS"
    assert events[2]["verifier"]["outcome"] == "OK"


def test_projected_full_cost_can_block_escalation(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_budget_projection_block.jsonl"
    out_path = tmp_path / "eventlog_budget_projection_block.jsonl"
    _write_single_json_task(tasks_path, task_id="task-budget-projection-block")

    adapter = ScriptedAdapter(
        scripts={"task-budget-projection-block": ["not-json"]},
        phase_scripts={
            "task-budget-projection-block": {
                "scale_probe_candidate": ["bad-a", "bad-b"],
                "scale_full_candidate": ['{"status":"ok"}'],
            }
        },
        cost_usd=0.1,
    )

    budget_usd = 0.55
    summary = run_batch(
        tasks_path=tasks_path,
        adapter=adapter,
        out_path=out_path,
        scale="probe",
        k_probe=2,
        k_full=8,
        top_m=2,
        synth=False,
        budget_usd=budget_usd,
    )
    assert summary == {"total": 1, "passed": 0, "failed": 0, "unknown": 1}

    events = _load_events(out_path)
    phases = [event["run"]["extra"]["phase"] for event in events]
    assert phases == ["primary", "scale_probe"]

    spent_usd = 0.0
    for event in events:
        meta = event["cost"].get("meta", {})
        event_cost = meta.get("cost_usd")
        if isinstance(event_cost, (int, float)):
            spent_usd += float(event_cost)
    probe_cost_usd = float(events[1]["cost"]["meta"]["cost_usd"])

    # Old one-step budget gating would allow one more probe-sized attempt.
    assert (spent_usd + probe_cost_usd) <= budget_usd
    projected_full_usd = estimate_full_cost_usd(probe_cost_usd, k_probe=2, k_full=8, used_synth=False)
    assert (spent_usd + projected_full_usd) > budget_usd


def test_synth_prompt_includes_rule_context_block() -> None:
    adapter = ScriptedAdapter(
        scripts={"task-synth-context": ["fallback"]},
        phase_scripts={
            "task-synth-context": {
                "scale_probe_candidate": ['{"status":"candidate-a"}', '{"status":"candidate-b"}'],
                "scale_probe_synth": ['{"status":"synth"}'],
            }
        },
    )

    selected_rules = [
        {
            "rule_id": "RULE-42",
            "type": "GuardrailRule",
            "injection_mode": "prepend",
            "body": "Always return safe JSON.",
        }
    ]

    _, meta = run_pacore_lite(
        prompt="Return JSON with status.",
        mode="json",
        adapter=adapter,
        k=2,
        top_m=2,
        use_synth=True,
        instructions=None,
        selected_rules=selected_rules,
        tier="probe",
        task_id="task-synth-context",
        attempt_idx=1,
    )
    assert meta["used_synth"] is True

    synth_calls = [call for call in adapter.calls if call.get("phase") == "scale_probe_synth"]
    assert len(synth_calls) == 1
    synth_prompt = synth_calls[0]["prompt"]
    assert "Rulecraft Context" in synth_prompt
    assert "RULE-42" in synth_prompt
