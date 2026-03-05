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
    constraint_list = violated_constraints if isinstance(violated_constraints, list) else []
    reason_code_list = reason_codes if isinstance(reason_codes, list) else []
    contract_violations = [
        str(item)
        for item in constraint_list
        if isinstance(item, str) and item and item.startswith("jsonschema:")
    ]
    has_contract_violation = bool(contract_violations) or "schema_violation" in reason_code_list

    verifier_context = {
        "reason_codes": reason_code_list,
        "violated_constraints": constraint_list,
    }

    if mode == "json":
        if has_contract_violation:
            instructions = "Return JSON that satisfies the contract. Output JSON only."
        else:
            instructions = "Output JSON only. No prose."
    else:
        instructions = "Correct format issues and comply with any injected rules."

    contract_section = ""
    if has_contract_violation:
        if contract_violations:
            bullet_lines = "\n".join(f"- {item}" for item in contract_violations)
        else:
            bullet_lines = "- schema_violation"
        contract_section = f"\nContract violations:\n{bullet_lines}\n"

    prompt = (
        "Rulecraft Repair Request\n"
        f"Mode: {mode}\n"
        f"Original task:\n{task_prompt}\n\n"
        f"Previous output:\n{last_output}\n\n"
        f"Verifier feedback:\n{json.dumps(verifier_context, ensure_ascii=False, sort_keys=True)}\n"
        f"{contract_section}"
        "Return a corrected answer."
    )
    return prompt, instructions
