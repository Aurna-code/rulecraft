from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.verifier.verify_output import verify_output


def _sample_contract() -> dict[str, object]:
    return {
        "type": "jsonschema",
        "schema_id": "contract.status.v1",
        "schema": {
            "type": "object",
            "required": ["status"],
            "properties": {"status": {"type": "string"}},
            "additionalProperties": False,
        },
    }


def test_verify_output_without_contract_uses_l1_only() -> None:
    verifier = verify_output(mode="json", y_text='{"status":"ok"}', contract=None)
    assert verifier["verdict"] == "PASS"
    assert verifier["outcome"] == "OK"
    assert verifier["verifier_id"] == "vf_l1_v1"
    assert "l1" in verifier["layers"]
    assert "l3" not in verifier["layers"]


def test_verify_output_with_contract_fails_parseable_schema_invalid() -> None:
    verifier = verify_output(mode="json", y_text='{"status":1}', contract=_sample_contract())
    assert verifier["verdict"] == "FAIL"
    assert verifier["outcome"] == "FAIL"
    assert "schema_violation" in (verifier["reason_codes"] or [])
    assert verifier["verifier_id"] == "vf_l1_l3_jsonschema_v1"
    assert verifier["layers"]["l1"]["verdict"] == "PASS"
    assert verifier["layers"]["l3"]["verdict"] == "FAIL"


def test_verify_output_with_contract_keeps_l1_failure_when_json_invalid() -> None:
    verifier = verify_output(mode="json", y_text="not-json", contract=_sample_contract())
    assert verifier["verdict"] == "FAIL"
    assert verifier["outcome"] == "UNKNOWN"
    assert "format_leak" in (verifier["reason_codes"] or [])
    assert "l1" in verifier["layers"]
    assert "l3" not in verifier["layers"]
