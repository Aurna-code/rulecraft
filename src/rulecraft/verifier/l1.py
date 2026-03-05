"""Minimal L1 verifier for text and JSON task modes."""

from __future__ import annotations

import json
from typing import Literal

from ..contracts import VerifierResult
from .taxonomy import FORMAT_LEAK, JSON_PARSE, VC_FORMAT_JSON_PARSE, normalize_codes


def verify_text(task_mode: Literal["text", "json"], y: str) -> VerifierResult:
    if task_mode == "json":
        try:
            json.loads(y)
        except json.JSONDecodeError:
            return VerifierResult(
                verdict="FAIL",
                outcome="UNKNOWN",
                reason_codes=normalize_codes([FORMAT_LEAK, JSON_PARSE]),
                violated_constraints=normalize_codes([VC_FORMAT_JSON_PARSE]),
            )

    return VerifierResult(
        verdict="PASS",
        outcome="OK",
        reason_codes=None,
        violated_constraints=None,
    )
