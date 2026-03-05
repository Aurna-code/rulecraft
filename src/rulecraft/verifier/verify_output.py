"""Unified verifier entrypoint with optional contract-based L3 checks."""

from __future__ import annotations

import hashlib
import json
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


def _failure_cluster_id(
    *,
    mode: str,
    contract: Mapping[str, Any] | None,
    reason_codes: list[str] | None,
    violated_constraints: list[str] | None,
) -> str:
    contract_type = contract.get("type") if isinstance(contract, Mapping) else None
    schema_id = contract.get("schema_id") if isinstance(contract, Mapping) else None
    tuple_payload = (
        str(mode),
        str(contract_type) if contract_type is not None else None,
        str(schema_id) if schema_id is not None else None,
        sorted(reason_codes or []),
        sorted(violated_constraints or []),
    )
    digest = hashlib.sha1(json.dumps(tuple_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return f"fc_{digest[:12]}"


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
    if overall.verdict != "PASS" or overall.outcome != "OK":
        failure_cluster_id: str | None = _failure_cluster_id(
            mode=mode,
            contract=contract,
            reason_codes=reason_codes,
            violated_constraints=violated_constraints,
        )
    else:
        failure_cluster_id = None
    return {
        "verifier_id": verifier_id,
        "verdict": overall.verdict,
        "outcome": overall.outcome,
        "reason_codes": reason_codes,
        "violated_constraints": violated_constraints,
        "pass": pass_from(overall),
        "failure_cluster_id": failure_cluster_id,
        "layers": layers,
    }


__all__ = ["verify_output"]
