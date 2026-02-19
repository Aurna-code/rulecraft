"""Base backend adapter contract."""

from __future__ import annotations

from typing import Any


class BackendAdapter:
    def generate(self, messages: list[dict[str, Any]], **kwargs: Any) -> tuple[str, dict[str, Any]]:
        """Return (text, meta) for the provided prompt messages."""
        raise NotImplementedError("BackendAdapter.generate must be implemented by subclasses.")
