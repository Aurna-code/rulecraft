"""Injection plan builder for Rulebook-selected rules."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def build_injection_plan(applied_rules: Sequence[Mapping[str, Any]], input_text: str) -> dict[str, list[str]]:
    _ = input_text

    plan: dict[str, list[str]] = {
        "system": [],
        "prepend": [],
        "inline": [],
    }

    for applied_rule in applied_rules:
        body = str(applied_rule.get("body") or "").strip()
        if not body:
            continue

        injection_mode = applied_rule.get("injection_mode")
        if injection_mode == "system_guard":
            plan["system"].append(body)
        elif injection_mode == "inline":
            plan["inline"].append(body)
        else:
            plan["prepend"].append(body)

    return plan
