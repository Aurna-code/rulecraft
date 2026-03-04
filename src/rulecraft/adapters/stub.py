"""Stub LLM adapter for runner and verifier tests."""

from __future__ import annotations

import json
from typing import Any


class StubAdapter:
    def __init__(self, mode: str = "json") -> None:
        self.mode = mode

    def generate(self, prompt: str) -> tuple[str, dict[str, Any]]:
        if self.mode == "json":
            text = json.dumps({"status": "ok", "echo": prompt[:80]})
        elif self.mode == "text":
            text = f"stub-text: {prompt[:80]}"
        else:
            raise ValueError(f"Unsupported StubAdapter mode: {self.mode!r}")

        meta = {
            "backend": "stub",
            "model": "stub",
            "latency_ms": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0.0,
            "error": None,
        }
        return text, meta

