"""Deterministic repair prompt helpers for batch execution."""

from __future__ import annotations

import json
from typing import Any


def build_repair_prompt(
    task_prompt: str,
    mode: str,
    last_output: str,
    verifier: dict[str, Any],
) -> tuple[str, str | None]:
    violated_constraints = verifier.get("violated_constraints")
    reason_codes = verifier.get("reason_codes")

    verifier_context = {
        "reason_codes": reason_codes if isinstance(reason_codes, list) else [],
        "violated_constraints": violated_constraints if isinstance(violated_constraints, list) else [],
    }

    if mode == "json":
        instructions = "Output JSON only. No prose."
    else:
        instructions = "Correct format issues and comply with any injected rules."

    prompt = (
        "Rulecraft Repair Request\n"
        f"Mode: {mode}\n"
        f"Original task:\n{task_prompt}\n\n"
        f"Previous output:\n{last_output}\n\n"
        f"Verifier feedback:\n{json.dumps(verifier_context, ensure_ascii=False, sort_keys=True)}\n"
        "Return a corrected answer."
    )
    return prompt, instructions
