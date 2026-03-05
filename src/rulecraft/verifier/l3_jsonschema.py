"""L3 verifier for JSON Schema task contracts."""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ..contracts import VerifierResult
from .taxonomy import JSON_PARSE, SCHEMA_VIOLATION, VC_FORMAT_JSON_PARSE, normalize_codes, vc_jsonschema


def _path_string(error: ValidationError) -> str:
    if not error.path:
        return "$"
    return "$." + ".".join(str(part) for part in error.path)


def _constraint(error: ValidationError) -> str:
    validator_name = error.validator or "validation"
    return vc_jsonschema(_path_string(error), str(validator_name))


def verify_jsonschema(y_text: str, schema: dict[str, Any]) -> VerifierResult:
    """Validate JSON text against a JSON Schema contract."""
    try:
        payload = json.loads(y_text)
    except json.JSONDecodeError:
        return VerifierResult(
            verdict="FAIL",
            outcome="UNKNOWN",
            reason_codes=normalize_codes([JSON_PARSE]),
            violated_constraints=normalize_codes([VC_FORMAT_JSON_PARSE]),
        )

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda err: (_path_string(err), str(err.validator)))
    if errors:
        constraints = []
        for error in errors[:8]:
            constraints.append(_constraint(error))
        return VerifierResult(
            verdict="FAIL",
            outcome="FAIL",
            reason_codes=normalize_codes([SCHEMA_VIOLATION]),
            violated_constraints=normalize_codes(constraints),
        )

    return VerifierResult(
        verdict="PASS",
        outcome="OK",
        reason_codes=None,
        violated_constraints=None,
    )


__all__ = ["verify_jsonschema"]
