from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.contracts import SCHEMA_VERSION, normalize_eventlog_dict
from rulecraft.logging import append_event

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


@pytest.fixture
def old_shape_minimal_event() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": "trace-minimal",
        "x_ref": "x-minimal",
        "selected_rules": [],
        "verifier": {
            "verdict": "PASS",
            "outcome": "OK",
            "reason_codes": None,
            "violated_constraints": None,
        },
        "cost": {
            "meta": {
                "backend": "stub",
                "model": "stub",
                "cost_usd": 0.0,
                "error": None,
            }
        },
    }


@pytest.fixture
def old_shape_rich_event() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": "trace-rich",
        "x_ref": "x-rich",
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
            "latency_ms": 42,
            "tokens_in": 12,
            "tokens_out": 34,
            "cost_usd": 0.001,
            "error": "timeout",
        },
    }


def test_normalize_minimal_shape_has_canonical_keys(old_shape_minimal_event: dict[str, object]) -> None:
    normalized = normalize_eventlog_dict(old_shape_minimal_event)

    assert set(normalized.keys()) == CANONICAL_KEYS
    assert normalized["schema_version"] == SCHEMA_VERSION
    assert normalized["verifier"]["verifier_id"] == "vf_l1_v1"
    assert normalized["verifier"]["pass"] == 1
    assert normalized["cost"]["meta"]["backend"] == "stub"
    assert normalized["cost"]["latency_ms"] is None


def test_normalize_rich_shape_moves_flat_fields_into_cost_meta(old_shape_rich_event: dict[str, object]) -> None:
    normalized = normalize_eventlog_dict(old_shape_rich_event)

    assert set(normalized.keys()) == CANONICAL_KEYS
    assert normalized["selected_rules"] == [{"rule_id": "RULE-1", "version": SCHEMA_VERSION, "type": "UnknownRule"}]

    verifier = normalized["verifier"]
    assert verifier["verifier_id"] == "vf_l1_v1"
    assert verifier["verdict"] == "FAIL"
    assert verifier["outcome"] == "UNKNOWN"
    assert verifier["pass"] == 0

    cost = normalized["cost"]
    assert cost["latency_ms"] == 42
    assert cost["tokens_in"] == 12
    assert cost["tokens_out"] == 34
    assert cost["meta"]["backend"] == "openai"
    assert cost["meta"]["model"] == "gpt-5-mini"
    assert cost["meta"]["cost_usd"] == 0.001
    assert cost["meta"]["error"] == "timeout"


def test_normalize_prefers_verifier_fields_over_top_level() -> None:
    normalized = normalize_eventlog_dict(
        {
            "trace_id": "trace-prefer",
            "x_ref": "x-prefer",
            "selected_rules": [],
            "verdict": "FAIL",
            "outcome": "FAIL",
            "verifier": {"verdict": "PASS", "outcome": "OK"},
        }
    )

    assert normalized["verifier"]["verdict"] == "PASS"
    assert normalized["verifier"]["outcome"] == "OK"
    assert normalized["verifier"]["pass"] == 1


def test_append_event_writes_canonical_shape(tmp_path: Path, old_shape_rich_event: dict[str, object]) -> None:
    path = tmp_path / "eventlog.jsonl"
    append_event(str(path), old_shape_rich_event)

    line = path.read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert set(payload.keys()) == CANONICAL_KEYS
    assert payload["verifier"]["verifier_id"] == "vf_l1_v1"
    assert payload["cost"]["meta"]["backend"] == "openai"
