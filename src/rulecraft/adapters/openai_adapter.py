"""OpenAI Responses API adapter."""

from __future__ import annotations

import os
import time
from typing import Any, Mapping

from .openai_cost import estimate_openai_cost_usd


def _usage_value(usage: Any, key: str) -> int | None:
    if usage is None:
        return None

    value: Any
    if isinstance(usage, Mapping):
        value = usage.get(key)
    else:
        value = getattr(usage, key, None)

    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _response_value(response: Any, key: str) -> Any:
    if isinstance(response, Mapping):
        return response.get(key)
    return getattr(response, key, None)


class OpenAIAdapter:
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model or os.getenv("RULECRAFT_OPENAI_MODEL", "gpt-5-mini")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = client

    def _client_or_init(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK is not installed. Install the optional dependency: pip install 'rulecraft[openai]'."
            ) from exc

        self._client = OpenAI(api_key=self.api_key)
        return self._client

    def generate(self, prompt: str, instructions: str | None = None) -> tuple[str, dict[str, Any]]:
        started = time.perf_counter()

        request: dict[str, Any] = {"model": self.model, "input": prompt}
        if instructions:
            request["instructions"] = instructions

        try:
            response = self._client_or_init().responses.create(**request)
            usage = _response_value(response, "usage")
            tokens_in = _usage_value(usage, "input_tokens")
            tokens_out = _usage_value(usage, "output_tokens")
            latency_ms = int((time.perf_counter() - started) * 1000)
            cost_usd = estimate_openai_cost_usd(self.model, tokens_in, tokens_out)

            text = str(_response_value(response, "output_text") or "")
            meta = {
                "backend": "openai",
                "model": self.model,
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "error": None,
                "response_id": _response_value(response, "id"),
            }
            return text, meta
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            meta = {
                "backend": "openai",
                "model": self.model,
                "latency_ms": latency_ms,
                "tokens_in": None,
                "tokens_out": None,
                "cost_usd": None,
                "error": str(exc),
                "response_id": None,
            }
            return "", meta
