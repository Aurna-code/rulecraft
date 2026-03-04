"""Minimal L1 verifier for text and JSON task modes."""

from __future__ import annotations

import json
from typing import Literal

from ..contracts import VerifierResult


def verify_text(task_mode: Literal["text", "json"], y: str) -> VerifierResult:
    if task_mode == "json":
        try:
            json.loads(y)
        except json.JSONDecodeError:
            return VerifierResult(
                verdict="FAIL",
                outcome="UNKNOWN",
                reason_codes=["format_leak"],
                violated_constraints=["json_parse"],
            )

    return VerifierResult(
        verdict="PASS",
        outcome="OK",
        reason_codes=None,
        violated_constraints=None,
    )

