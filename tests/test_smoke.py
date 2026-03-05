from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.stub import StubAdapter
from rulecraft.contracts import SCHEMA_VERSION, VerifierResult, pass_from
from rulecraft.runner.minimal import run_once


def test_run_once_returns_minimal_eventlog() -> None:
    _, event = run_once("smoke input")
    payload = event.to_dict()

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["trace_id"]
    assert payload["x_ref"]
    assert "selected_rules" in payload
    assert isinstance(payload["selected_rules"], list)
    assert payload["verifier"]["verifier_id"] == "vf_l1_v1"
    assert payload["verifier"]["verdict"] == "PASS"
    assert payload["verifier"]["outcome"] == "OK"
    assert payload["verifier"]["pass"] == 1
    assert payload["cost"]["meta"]["backend"] == "stub"
    assert "verdict" not in payload
    assert "outcome" not in payload


def test_pass_from_pass_ok_is_one() -> None:
    assert pass_from(VerifierResult(verdict="PASS", outcome="OK")) == 1


def test_pass_from_pass_fail_is_zero() -> None:
    assert pass_from(VerifierResult(verdict="PASS", outcome="FAIL")) == 0


def test_json_mode_parse_failure_records_reason_codes() -> None:
    _, event = run_once("return json please", task_mode="json", adapter=StubAdapter(mode="text"))
    payload = event.to_dict()
    verifier = payload["verifier"]

    assert verifier["verdict"] == "FAIL"
    assert verifier["outcome"] in {"UNKNOWN", "FAIL"}
    assert "FORMAT_LEAK" in (verifier["reason_codes"] or [])
    assert "FORMAT:JSON_PARSE" in (verifier["violated_constraints"] or [])
