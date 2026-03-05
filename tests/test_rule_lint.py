from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.cli import main
from rulecraft.rulebook.lint import lint_rulebook


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _rulebook_payload() -> dict[str, object]:
    return {
        "rulebook_name": "Rulebook",
        "rules": [
            {
                "rule_id": "R1",
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "body": "Output JSON only. No prose.",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 1},
                "injection_mode": "prepend",
            },
            {
                "rule_id": "R1",
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "body": "Output JSON only. No prose.",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 1},
                "injection_mode": "prepend",
            },
            {
                "rule_id": "R3",
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "body": "",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 2},
                "injection_mode": "prepend",
            },
            {
                "rule_id": "R4",
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "body": "Output text only.",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 1},
                "injection_mode": "prepend",
            },
        ],
    }


def test_lint_rulebook_detects_errors_duplicates_and_conflicts() -> None:
    result = lint_rulebook(_rulebook_payload())

    error_codes = {item["code"] for item in result["errors"]}
    warning_codes = {item["code"] for item in result["warnings"]}

    assert "RULE_ID_DUPLICATE" in error_codes
    assert "INJECTION_PAYLOAD_EMPTY" in error_codes
    assert "DUPLICATE_PAYLOAD" in warning_codes
    assert "POTENTIAL_CONFLICT" in warning_codes
    assert result["duplicates"]
    assert result["conflicts"]


def test_lint_rulebook_eventlog_warns_for_unused_rules(tmp_path: Path) -> None:
    eventlog_path = tmp_path / "eventlog.jsonl"
    eventlog_path.write_text(
        json.dumps(
            {
                "trace_id": "trace-1",
                "x_ref": "x-1",
                "selected_rules": [{"rule_id": "R1", "version": "0.1.0", "type": "StrategyRule"}],
                "verifier": {"verdict": "PASS", "outcome": "OK"},
                "cost": {"meta": {"backend": "stub", "model": "stub", "cost_usd": 0.0, "error": None}},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    result = lint_rulebook(_rulebook_payload(), eventlog_path=str(eventlog_path))
    unused_warnings = [item for item in result["warnings"] if item.get("code") == "RULE_UNUSED_IN_EVENTLOG"]
    warned_ids = {item["rule_id"] for item in unused_warnings}
    assert "R3" in warned_ids
    assert "R4" in warned_ids


def test_rule_lint_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rulebook_path = tmp_path / "rulebook.json"
    _write_json(rulebook_path, _rulebook_payload())

    exit_code = main(["rule-lint", "--rulebook", str(rulebook_path)])
    assert exit_code == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"]

    clean_rulebook = {
        "rulebook_name": "Rulebook",
        "rules": [
            {
                "rule_id": "R10",
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "body": "Output JSON only.",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 1},
                "injection_mode": "prepend",
            }
        ],
    }
    _write_json(rulebook_path, clean_rulebook)
    exit_code = main(["rule-lint", "--rulebook", str(rulebook_path), "--strict"])
    assert exit_code == 0

    warning_only_rulebook = {
        "rulebook_name": "Rulebook",
        "rules": [
            {
                "rule_id": "R20",
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "body": "Output JSON only.",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 1},
                "injection_mode": "prepend",
            },
            {
                "rule_id": "R21",
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "body": "Output JSON only.",
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"rank": 2},
                "injection_mode": "prepend",
            },
        ],
    }
    _write_json(rulebook_path, warning_only_rulebook)
    assert main(["rule-lint", "--rulebook", str(rulebook_path)]) == 0
    assert main(["rule-lint", "--rulebook", str(rulebook_path), "--strict"]) == 4
