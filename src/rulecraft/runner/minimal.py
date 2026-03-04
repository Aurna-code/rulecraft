"""Minimal executable runner for MVP smoke tests."""

from __future__ import annotations

import hashlib
import uuid
from typing import Literal

from ..adapters.base import LLMAdapter
from ..adapters.stub import StubAdapter
from ..contracts import EventLog, pass_from
from ..verifier.l1 import verify_text


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped.lstrip("-").isdigit():
            return int(stripped)
    return None


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def run_once(
    x: str,
    task_mode: Literal["text", "json"] = "text",
    adapter: LLMAdapter | None = None,
) -> tuple[str, EventLog]:
    llm = adapter or StubAdapter(mode="json" if task_mode == "json" else "text")
    y, meta = llm.generate(x)
    verifier_result = verify_text(task_mode=task_mode, y=y)

    event = EventLog(
        trace_id=str(uuid.uuid4()),
        x_ref=hashlib.sha256(x.encode("utf-8")).hexdigest(),
        selected_rules=[],
        verifier={
            "verifier_id": "vf_l1_v1",
            "verdict": verifier_result.verdict,
            "outcome": verifier_result.outcome,
            "reason_codes": verifier_result.reason_codes,
            "violated_constraints": verifier_result.violated_constraints,
            "pass": pass_from(verifier_result),
        },
        cost={
            "latency_ms": _coerce_optional_int(meta.get("latency_ms")),
            "tokens_in": _coerce_optional_int(meta.get("tokens_in")),
            "tokens_out": _coerce_optional_int(meta.get("tokens_out")),
            "tool_calls": _coerce_optional_int(meta.get("tool_calls")),
            "meta": {
                "backend": meta.get("backend", "stub"),
                "model": meta.get("model", "stub"),
                "cost_usd": _coerce_optional_float(meta.get("cost_usd")),
                "error": meta.get("error"),
            },
        },
    )

    return y, event
