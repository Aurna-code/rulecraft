"""Deterministic scripted adapter for offline tests."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


class ScriptedAdapter:
    """Return scripted outputs by task id and attempt index."""

    def __init__(self, scripts: Mapping[str, Sequence[str]], default_text: str = "scripted-default-output") -> None:
        self.scripts = {str(task_id): [str(item) for item in outputs] for task_id, outputs in scripts.items()}
        self.default_text = default_text

    def generate(
        self,
        prompt: str,
        *,
        task_id: str | None = None,
        attempt_idx: int = 0,
        instructions: str | None = None,
        **_: Any,
    ) -> tuple[str, dict[str, Any]]:
        _ = instructions
        _ = prompt

        task_key = str(task_id or "")
        scripted_outputs = self.scripts.get(task_key)
        if scripted_outputs and attempt_idx < len(scripted_outputs):
            text = scripted_outputs[attempt_idx]
        elif scripted_outputs and scripted_outputs:
            text = scripted_outputs[-1]
        else:
            text = self.default_text

        meta = {
            "backend": "scripted",
            "model": "scripted",
            "latency_ms": 0,
            "tokens_in": 0,
            "tokens_out": max(len(text) // 4, 1),
            "cost_usd": 0.0,
            "error": None,
        }
        return text, meta
