"""Static L1 validation checks for v0.1 core runtime."""

from __future__ import annotations

import json
from typing import Any

from ..contracts import ExecutionOutcome, PolicyVerdict, ValidationResult
from ..ids import stable_hash_id


def _build_failure_cluster_id(reason_codes: list[str], violated_constraints: list[str]) -> str | None:
    if not reason_codes and not violated_constraints:
        return None

    payload = "|".join(
        [
            "L1",
            ",".join(sorted(reason_codes)),
            ",".join(sorted(violated_constraints)),
        ]
    )
    return stable_hash_id(payload)


def validate_l1(candidate_text: str, constraints: dict[str, Any]) -> ValidationResult:
    reason_codes: list[str] = []
    violated_constraints: list[str] = []
    verdict: PolicyVerdict = "PASS"
    outcome: ExecutionOutcome = "OK"

    json_only = bool(constraints.get("json_only"))
    if json_only:
        try:
            json.loads(candidate_text)
        except json.JSONDecodeError:
            verdict = "FAIL"
            outcome = "UNKNOWN"
            reason_codes.append("format_violation")
            violated_constraints.append("FORMAT:JSON_ONLY")

    length_lte = constraints.get("length_lte")
    if isinstance(length_lte, int) and len(candidate_text) > length_lte:
        if verdict == "PASS":
            verdict = "PARTIAL"
        outcome = "UNKNOWN"
        reason_codes.append("length_violation")
        violated_constraints.append("FORMAT:LENGTH_LTE")

    failure_cluster_id = _build_failure_cluster_id(reason_codes, violated_constraints)
    score = 1.0 if verdict == "PASS" and outcome == "OK" else 0.0

    return ValidationResult(
        validator_id="validator.l1.static",
        verdict=verdict,
        outcome=outcome,
        score=score,
        reason_codes=reason_codes or None,
        violated_constraints=violated_constraints or None,
        failure_cluster_id=failure_cluster_id,
        notes="Static L1 checks only; advanced validation is disabled in v0.1.",
    )
