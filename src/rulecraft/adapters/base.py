"""Base backend adapter contract."""

from __future__ import annotations

from typing import Any, Protocol


class BackendAdapter:
    def generate(self, messages: list[dict[str, Any]], **kwargs: Any) -> tuple[str, dict[str, Any]]:
        """Return (text, meta) for the provided prompt messages."""
        raise NotImplementedError("BackendAdapter.generate must be implemented by subclasses.")


class LLMAdapter(Protocol):
    """Minimal single-prompt LLM adapter contract for runner MVP."""

    def generate(self, prompt: str) -> tuple[str, dict[str, Any]]:
        """Return (text, meta) for a single prompt."""
        ...
