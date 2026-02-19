"""Repair helpers for hot-tier JSON-only retries."""

from __future__ import annotations

from typing import Any


def build_json_repair_messages(
    base_messages: list[dict[str, Any]],
    bad_output: str,
    constraints: dict[str, Any],
) -> list[dict[str, str]]:
    repaired_messages: list[dict[str, str]] = [
        {
            "role": str(message.get("role", "")),
            "content": str(message.get("content", "")),
        }
        for message in base_messages
    ]

    lines = [
        "Your previous output was not valid JSON. Return ONLY valid JSON that satisfies the constraints.",
        "Do not include any commentary or extra text.",
    ]
    length_lte = constraints.get("length_lte")
    if isinstance(length_lte, int) and length_lte > 0:
        lines.append(f"Keep the output length at most {length_lte} characters.")

    lines.append("Previous invalid output:")
    lines.append(str(bad_output))

    repaired_messages.append({"role": "user", "content": "\n".join(lines)})
    return repaired_messages
