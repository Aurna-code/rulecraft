"""Dummy adapter for local runtime smoke tests."""

from __future__ import annotations

import json
from typing import Any

from .base import BackendAdapter


class DummyAdapter(BackendAdapter):
    def __init__(self, mode: str = "json_ok") -> None:
        self.mode = mode

    def generate(self, messages: list[dict[str, Any]], **kwargs: Any) -> tuple[str, dict[str, Any]]:
        _ = kwargs

        last_user_content = ""
        for message in messages:
            if message.get("role") == "user":
                last_user_content = str(message.get("content", ""))

        if self.mode == "json_ok":
            text = json.dumps({"status": "ok", "answer": "dummy", "input_echo": last_user_content[:80]})
        elif self.mode == "echo":
            text = last_user_content
        else:
            raise ValueError(f"Unsupported DummyAdapter mode: {self.mode!r}")

        tokens_in = max(sum(len(str(message.get("content", ""))) for message in messages) // 4, 1)
        tokens_out = max(len(text) // 4, 1)
        meta = {
            "latency_ms": 1,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "model_name": f"dummy:{self.mode}",
            "adapter_mode": self.mode,
        }
        return text, meta
