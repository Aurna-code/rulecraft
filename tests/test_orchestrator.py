from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.base import BackendAdapter
from rulecraft.adapters.dummy import DummyAdapter
from rulecraft.orchestrator import Orchestrator
from rulecraft.rulebook.store import RulebookStore


def _default_context() -> dict[str, str]:
    return {
        "bucket_id": "support",
        "domain_tag": "payments",
        "task_family": "answer",
        "impact_level": "low",
        "user_clarity": "high",
    }


def _write_inline_rulebook(path: Path) -> None:
    payload = {
        "rulebook_name": "InlineRulebook",
        "rules": [
            {
                "schema_version": "0.1.0",
                "rule_id": "INLINE-1",
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "title": "Inline guidance",
                "body": "INLINE_RULE:XYZ",
                "injection_mode": "inline",
                "applicability": {
                    "domain_tag": "payments",
                    "task_family": "answer",
                    "bucket_ids": ["support"],
                },
                "priority": {"guardrail_first": False, "rank": 1},
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class SpyDummyAdapter(DummyAdapter):
    def __init__(self, mode: str = "json_ok") -> None:
        super().__init__(mode=mode)
        self.messages_seen: list[dict[str, str]] = []

    def generate(self, messages: list[dict[str, Any]], **kwargs: Any) -> tuple[str, dict[str, Any]]:
        self.messages_seen = [
            {"role": str(message.get("role", "")), "content": str(message.get("content", ""))}
            for message in messages
        ]
        return super().generate(messages, **kwargs)


class SequenceAdapter(BackendAdapter):
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.call_count = 0
        self.calls: list[list[dict[str, str]]] = []
        self.call_metas: list[dict[str, Any]] = []

    def generate(self, messages: list[dict[str, Any]], **kwargs: Any) -> tuple[str, dict[str, Any]]:
        _ = kwargs
        if self.call_count >= len(self.outputs):
            raise AssertionError("SequenceAdapter received more calls than configured outputs.")

        normalized_messages = [
            {"role": str(message.get("role", "")), "content": str(message.get("content", ""))}
            for message in messages
        ]
        self.calls.append(normalized_messages)

        output = self.outputs[self.call_count]
        self.call_count += 1
        meta = {
            "latency_ms": 1,
            "tokens_in": max(sum(len(message["content"]) for message in normalized_messages) // 4, 1),
            "tokens_out": max(len(output) // 4, 1),
            "adapter_mode": "sequence",
        }
        self.call_metas.append(meta)
        return output, meta


def test_orchestrator_hot_loop_json_ok(tmp_path: Path) -> None:
    store = RulebookStore.load_from_json(ROOT / "rules" / "sample_rulebook.json")
    orchestrator = Orchestrator()
    runlog_path = tmp_path / "runlog.jsonl"

    output, runlog = orchestrator.run(
        input_text="Return JSON.",
        context=_default_context(),
        constraints={"json_only": True, "length_lte": 4000},
        rulebook_store=store,
        adapter=DummyAdapter(mode="json_ok"),
        runlog_path=str(runlog_path),
    )

    assert output
    assert runlog["schema_version"] == "0.1.0"
    assert runlog["run_id"]
    assert runlog["validator"]["verdict"]
    assert runlog["validator"]["outcome"]
    assert runlog["control_signals"]["budget_tier"] == "hot"
    assert runlog["control_signals"]["adapter_calls"] == 1
    assert runlog["control_signals"]["exit_stage"] == "l1"

    lines = runlog_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["run_id"] == runlog["run_id"]


def test_orchestrator_includes_inline_in_adapter_messages(tmp_path: Path) -> None:
    rulebook_path = tmp_path / "inline_rulebook.json"
    _write_inline_rulebook(rulebook_path)
    store = RulebookStore.load_from_json(rulebook_path)
    orchestrator = Orchestrator()
    runlog_path = tmp_path / "runlog.jsonl"
    adapter = SpyDummyAdapter(mode="json_ok")

    orchestrator.run(
        input_text="Return JSON.",
        context=_default_context(),
        constraints={"json_only": True, "length_lte": 4000},
        rulebook_store=store,
        adapter=adapter,
        runlog_path=str(runlog_path),
    )

    assert any(
        message["role"] == "user" and "INLINE_RULE:XYZ" in message["content"] for message in adapter.messages_seen
    )


def test_orchestrator_json_only_repair_success(tmp_path: Path) -> None:
    store = RulebookStore.load_from_json(ROOT / "rules" / "sample_rulebook.json")
    orchestrator = Orchestrator()
    runlog_path = tmp_path / "runlog.jsonl"
    adapter = SequenceAdapter(outputs=["NOT JSON", '{"ok": true}'])

    output, runlog = orchestrator.run(
        input_text="Return JSON.",
        context=_default_context(),
        constraints={"json_only": True},
        rulebook_store=store,
        adapter=adapter,
        runlog_path=str(runlog_path),
    )

    assert output == '{"ok": true}'
    assert adapter.call_count == 2
    assert runlog["validator"]["verdict"] == "PASS"
    assert runlog["validator"]["outcome"] == "OK"
    assert runlog["control_signals"]["repair_attempted"] is True
    assert runlog["control_signals"]["repair_succeeded"] is True
    assert runlog["control_signals"]["adapter_calls"] == 2
    assert runlog["control_signals"]["exit_stage"] == "l1_repair"
    assert runlog["control_signals"]["exit_reason"] == "repaired_pass"
    assert runlog["control_signals"]["should_escalate"] is False
    assert runlog["run"]["cfg"]["repair_attempted"] is True
    assert runlog["cost"]["latency_ms"] == sum(int(meta["latency_ms"]) for meta in adapter.call_metas)
    assert runlog["cost"]["tokens_in"] == sum(int(meta["tokens_in"]) for meta in adapter.call_metas)
    assert runlog["cost"]["tokens_out"] == sum(int(meta["tokens_out"]) for meta in adapter.call_metas)
    assert runlog["cost"]["tool_calls"] == 0


def test_orchestrator_json_only_repair_fail(tmp_path: Path) -> None:
    store = RulebookStore.load_from_json(ROOT / "rules" / "sample_rulebook.json")
    orchestrator = Orchestrator()
    runlog_path = tmp_path / "runlog.jsonl"
    adapter = SequenceAdapter(outputs=["NOT JSON", "STILL NOT JSON"])

    output, runlog = orchestrator.run(
        input_text="Return JSON.",
        context=_default_context(),
        constraints={"json_only": True},
        rulebook_store=store,
        adapter=adapter,
        runlog_path=str(runlog_path),
    )

    assert output == "STILL NOT JSON"
    assert adapter.call_count == 2
    assert runlog["validator"]["verdict"] == "FAIL"
    assert runlog["validator"]["outcome"] == "UNKNOWN"
    assert runlog["control_signals"]["repair_attempted"] is True
    assert runlog["control_signals"]["repair_succeeded"] is False
    assert runlog["control_signals"]["adapter_calls"] == 2
    assert runlog["control_signals"]["exit_stage"] == "l1_repair"
    assert runlog["control_signals"]["exit_reason"] == "needs_escalation"
    assert runlog["control_signals"]["should_escalate"] is True
    assert runlog["run"]["cfg"]["repair_attempted"] is True
    assert runlog["cost"]["latency_ms"] == sum(int(meta["latency_ms"]) for meta in adapter.call_metas)
    assert runlog["cost"]["tokens_in"] == sum(int(meta["tokens_in"]) for meta in adapter.call_metas)
    assert runlog["cost"]["tokens_out"] == sum(int(meta["tokens_out"]) for meta in adapter.call_metas)
    assert runlog["cost"]["tool_calls"] == 0
