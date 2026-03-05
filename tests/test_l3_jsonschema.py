from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.verifier.l3_jsonschema import verify_jsonschema


def test_verify_jsonschema_passes_for_valid_payload() -> None:
    schema = {
        "type": "object",
        "required": ["status"],
        "properties": {
            "status": {"type": "string"},
        },
        "additionalProperties": False,
    }

    result = verify_jsonschema('{"status":"ok"}', schema)
    assert result.verdict == "PASS"
    assert result.outcome == "OK"
    assert result.reason_codes is None
    assert result.violated_constraints is None


def test_verify_jsonschema_fails_for_parse_errors() -> None:
    schema = {"type": "object"}
    result = verify_jsonschema("not-json", schema)
    assert result.verdict == "FAIL"
    assert result.outcome == "UNKNOWN"
    assert "JSON_PARSE" in (result.reason_codes or [])
    assert "FORMAT:JSON_PARSE" in (result.violated_constraints or [])


def test_verify_jsonschema_fails_for_schema_violations() -> None:
    schema = {
        "type": "object",
        "required": ["status", "count"],
        "properties": {
            "status": {"type": "string"},
            "count": {"type": "integer"},
        },
        "additionalProperties": False,
    }

    result = verify_jsonschema('{"status":"ok","count":"3"}', schema)
    assert result.verdict == "FAIL"
    assert result.outcome == "FAIL"
    assert "SCHEMA_VIOLATION" in (result.reason_codes or [])
    constraints = result.violated_constraints or []
    assert constraints
    assert all(item.startswith("SCHEMA:JSONSCHEMA:") for item in constraints)
