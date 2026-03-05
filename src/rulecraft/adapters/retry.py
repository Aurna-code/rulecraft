"""Retry policy helpers for adapter calls."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable


def _status_code(exc: BaseException) -> int | None:
    direct = getattr(exc, "status_code", None)
    if isinstance(direct, int):
        return direct
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status
    return None


def classify_error(exc: BaseException, retry_on_statuses: Iterable[int]) -> tuple[str, int | None, bool]:
    """Return (error_class, status_code, retryable)."""
    status = _status_code(exc)
    if status == 429:
        return "rate_limit", status, True
    if isinstance(status, int) and 500 <= status <= 599:
        return "server_error", status, status in set(retry_on_statuses)
    if isinstance(status, int) and 400 <= status <= 499:
        return "client_error", status, status in set(retry_on_statuses)

    exc_name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in exc_name or "timed out" in message or "timeout" in message:
        return "timeout", status, True
    return "unknown", status, False


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    base_delay_s: float = 0.2
    max_delay_s: float = 2.0
    jitter_s: float = 0.1
    retry_on_statuses: tuple[int, ...] = (429, 500, 501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511)

    def delay(self, attempt_index: int, rnd: random.Random) -> float:
        raw = min(self.max_delay_s, self.base_delay_s * (2 ** max(attempt_index, 0)))
        jitter = rnd.uniform(0.0, max(self.jitter_s, 0.0))
        return max(raw + jitter, 0.0)


def run_with_retry(
    fn: Callable[[], Any],
    *,
    policy: RetryPolicy | None = None,
    seed: int | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> tuple[Any | None, dict[str, Any]]:
    """Execute fn with retry/backoff. Returns (value_or_none, metadata)."""
    resolved_policy = policy or RetryPolicy()
    sleeper = sleep_fn or time.sleep
    rnd = random.Random(0 if seed is None else int(seed))

    retries = 0
    sleeps: list[float] = []
    last_exc: BaseException | None = None
    last_error_class = None
    last_status_code = None

    while True:
        attempts = retries + 1
        try:
            value = fn()
            return (
                value,
                {
                    "attempts": attempts,
                    "retries": retries,
                    "sleep_s": list(sleeps),
                    "error_class": None,
                    "status_code": None,
                    "error": None,
                },
            )
        except Exception as exc:  # pragma: no cover - exercised in tests
            last_exc = exc
            last_error_class, last_status_code, retryable = classify_error(exc, resolved_policy.retry_on_statuses)
            if (not retryable) or retries >= int(resolved_policy.max_retries):
                return (
                    None,
                    {
                        "attempts": attempts,
                        "retries": retries,
                        "sleep_s": list(sleeps),
                        "error_class": last_error_class,
                        "status_code": last_status_code,
                        "error": str(last_exc),
                    },
                )

            delay_s = resolved_policy.delay(retries, rnd)
            sleeps.append(delay_s)
            sleeper(delay_s)
            retries += 1


__all__ = ["RetryPolicy", "classify_error", "run_with_retry"]
