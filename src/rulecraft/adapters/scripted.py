"""Deterministic scripted adapter for offline tests."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


class ScriptedAdapter:
    """Return scripted outputs by task id and attempt index."""

    def __init__(
        self,
        scripts: Mapping[str, Sequence[str]],
        default_text: str = "scripted-default-output",
        phase_scripts: Mapping[str, Mapping[str, Sequence[str]]] | None = None,
    ) -> None:
        self.scripts = {str(task_id): [str(item) for item in outputs] for task_id, outputs in scripts.items()}
        self.phase_scripts = {
            str(task_id): {str(phase): [str(item) for item in outputs] for phase, outputs in phases.items()}
            for task_id, phases in (phase_scripts or {}).items()
        }
        self.default_text = default_text
        self.calls: list[dict[str, Any]] = []
        self._phase_indices: dict[tuple[str, str], int] = {}

    def generate(
        self,
        prompt: str,
        *,
        task_id: str | None = None,
        attempt_idx: int = 0,
        instructions: str | None = None,
        phase: str | None = None,
        **_: Any,
    ) -> tuple[str, dict[str, Any]]:
        self.calls.append(
            {
                "task_id": task_id,
                "attempt_idx": attempt_idx,
                "phase": phase,
                "instructions": instructions,
                "prompt": prompt,
            }
        )

        task_key = str(task_id or "")
        phase_key = str(phase or "")
        phase_outputs = self.phase_scripts.get(task_key, {}).get(phase_key)
        if phase_outputs:
            phase_ref = (task_key, phase_key)
            phase_idx = self._phase_indices.get(phase_ref, 0)
            if phase_idx < len(phase_outputs):
                text = phase_outputs[phase_idx]
            else:
                text = phase_outputs[-1]
            self._phase_indices[phase_ref] = phase_idx + 1
        else:
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
