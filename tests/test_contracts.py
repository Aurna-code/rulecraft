from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.contracts import TraceBundle, ValidationResult, is_confirmed_pass, is_pass


def test_validation_result_uses_ssot_fields() -> None:
    vr = ValidationResult(
        validator_id="validator.l1.default",
        verdict="PASS",
        outcome="OK",
        violated_constraints=["FORMAT:JSON_ONLY"],
    )

    payload = vr.to_dict()

    assert payload["verdict"] == "PASS"
    assert payload["outcome"] == "OK"
    assert payload["violated_constraints"] == ["FORMAT:JSON_ONLY"]
    assert "policy_verdict" not in payload
    assert "execution_outcome" not in payload
    assert "violation_keys" not in payload
    assert is_pass(vr)
    assert is_confirmed_pass(vr)


def test_pass_logic_treats_fail_outcome_as_not_pass() -> None:
    vr = ValidationResult(validator_id="validator.l1.default", verdict="PASS", outcome="FAIL")

    assert is_pass(vr) is False
    assert is_confirmed_pass(vr) is False


def test_trace_bundle_collects_refs_from_input_output_fields() -> None:
    bundle = TraceBundle.from_dict(
        {
            "run_id": "run-1",
            "input_ref": "sha1:in",
            "output_ref": "sha1:out",
        }
    )

    assert bundle.run_id == "run-1"
    assert bundle.refs == {"input_ref": "sha1:in", "output_ref": "sha1:out"}
