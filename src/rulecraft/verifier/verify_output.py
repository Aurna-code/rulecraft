"""Unified verifier entrypoint with optional contract-based L3 checks."""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import VerifierResult, pass_from
from .l1 import verify_text
from .l3_jsonschema import verify_jsonschema
from .taxonomy import EXEC_UNAVAILABLE, normalize_codes, vc_jsonschema


def _layer_payload(result: VerifierResult) -> dict[str, Any]:
    return {
        "verdict": result.verdict,
        "outcome": result.outcome,
        "reason_codes": normalize_codes(result.reason_codes),
        "violated_constraints": normalize_codes(result.violated_constraints),
    }


def _is_pass(result: VerifierResult) -> bool:
    return pass_from(result) == 1


def verify_output(mode: str, y_text: str, contract: Mapping[str, Any] | None) -> dict[str, Any]:
    """Run L1 and optional L3 verification and return canonical verifier payload."""
    l1_result = verify_text(task_mode="json" if mode == "json" else "text", y=y_text)
    layers: dict[str, Any] = {"l1": _layer_payload(l1_result)}

    overall = l1_result
    verifier_id = "vf_l1_v1"

    use_l3 = mode == "json" and isinstance(contract, Mapping) and contract.get("type") == "jsonschema"
    if use_l3:
        verifier_id = "vf_l1_l3_jsonschema_v1"
        if _is_pass(l1_result):
            schema = contract.get("schema")
            if isinstance(schema, Mapping):
                l3_result = verify_jsonschema(y_text=y_text, schema=dict(schema))
            else:
                l3_result = VerifierResult(
                    verdict="FAIL",
                    outcome="FAIL",
                    reason_codes=normalize_codes([EXEC_UNAVAILABLE]),
                    violated_constraints=normalize_codes([vc_jsonschema("$", "missing_schema")]),
                )
            layers["l3"] = _layer_payload(l3_result)
            if not _is_pass(l3_result):
                overall = l3_result

    reason_codes = normalize_codes(overall.reason_codes)
    violated_constraints = normalize_codes(overall.violated_constraints)
    return {
        "verifier_id": verifier_id,
        "verdict": overall.verdict,
        "outcome": overall.outcome,
        "reason_codes": reason_codes,
        "violated_constraints": violated_constraints,
        "pass": pass_from(overall),
        "layers": layers,
    }


__all__ = ["verify_output"]
