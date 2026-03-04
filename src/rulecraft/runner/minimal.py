"""Minimal executable runner for MVP smoke tests."""

from __future__ import annotations

import hashlib
import uuid
from typing import Literal

from ..adapters.base import LLMAdapter
from ..adapters.stub import StubAdapter
from ..contracts import EventLog, pass_from
from ..verifier.l1 import verify_text


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
            "verdict": verifier_result.verdict,
            "outcome": verifier_result.outcome,
            "reason_codes": verifier_result.reason_codes,
            "violated_constraints": verifier_result.violated_constraints,
            "pass": pass_from(verifier_result),
        },
        verdict=verifier_result.verdict,
        outcome=verifier_result.outcome,
        cost={
            "backend": meta.get("backend", "stub"),
            "model": meta.get("model", "stub"),
            "latency_ms": int(meta.get("latency_ms", 0)),
            "tokens_in": int(meta.get("tokens_in", 0)),
            "tokens_out": int(meta.get("tokens_out", 0)),
            "cost_usd": float(meta.get("cost_usd", 0.0)),
            "error": meta.get("error"),
        },
    )

    return y, event
