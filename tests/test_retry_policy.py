from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.openai_adapter import OpenAIAdapter
from rulecraft.adapters.retry import RetryPolicy, run_with_retry


class FakeHTTPError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Response:
    def __init__(self, text: str = '{"status":"ok"}') -> None:
        self.output_text = text
        self.usage = _Usage(input_tokens=12, output_tokens=8)
        self.id = "resp_fake_1"


class FakeResponses:
    def __init__(self, failures: list[Exception]) -> None:
        self.failures = list(failures)
        self.calls = 0

    def create(self, **_: object) -> _Response:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return _Response()


class FakeClient:
    def __init__(self, failures: list[Exception]) -> None:
        self.responses = FakeResponses(failures)


def test_run_with_retry_is_deterministic_with_seed() -> None:
    sleep_a: list[float] = []
    attempts_a = {"count": 0}

    def fn_a() -> str:
        attempts_a["count"] += 1
        if attempts_a["count"] <= 2:
            raise TimeoutError("temporary timeout")
        return "ok"

    value_a, meta_a = run_with_retry(
        fn_a,
        policy=RetryPolicy(max_retries=3, base_delay_s=0.2, max_delay_s=1.0, jitter_s=0.1),
        seed=11,
        sleep_fn=lambda delay: sleep_a.append(delay),
    )
    assert value_a == "ok"
    assert meta_a["retries"] == 2
    assert len(sleep_a) == 2

    sleep_b: list[float] = []
    attempts_b = {"count": 0}

    def fn_b() -> str:
        attempts_b["count"] += 1
        if attempts_b["count"] <= 2:
            raise TimeoutError("temporary timeout")
        return "ok"

    value_b, meta_b = run_with_retry(
        fn_b,
        policy=RetryPolicy(max_retries=3, base_delay_s=0.2, max_delay_s=1.0, jitter_s=0.1),
        seed=11,
        sleep_fn=lambda delay: sleep_b.append(delay),
    )
    assert value_b == "ok"
    assert meta_b["retries"] == 2
    assert sleep_a == pytest.approx(sleep_b)


def test_run_with_retry_classifies_final_failure() -> None:
    sleep_calls: list[float] = []

    def always_rate_limited() -> str:
        raise FakeHTTPError(429, "rate limited")

    value, meta = run_with_retry(
        always_rate_limited,
        policy=RetryPolicy(max_retries=1, base_delay_s=0.1, max_delay_s=0.1, jitter_s=0.0),
        seed=7,
        sleep_fn=lambda delay: sleep_calls.append(delay),
    )
    assert value is None
    assert meta["error_class"] == "rate_limit"
    assert meta["status_code"] == 429
    assert meta["retries"] == 1
    assert meta["attempts"] == 2
    assert sleep_calls == [pytest.approx(0.1)]


def test_openai_adapter_retries_and_succeeds_offline() -> None:
    client = FakeClient([TimeoutError("first timeout")])
    sleep_calls: list[float] = []
    adapter = OpenAIAdapter(
        client=client,
        retry_policy=RetryPolicy(max_retries=2, base_delay_s=0.05, max_delay_s=0.05, jitter_s=0.0),
        retry_seed=5,
        sleep_fn=lambda delay: sleep_calls.append(delay),
    )

    text, meta = adapter.generate("Return JSON status.")
    assert text.startswith("{")
    assert meta["error"] is None
    assert meta["error_class"] is None
    assert meta["retries"] == 1
    assert meta["attempts"] == 2
    assert meta["response_id"] == "resp_fake_1"
    assert len(sleep_calls) == 1
    assert client.responses.calls == 2


def test_openai_adapter_records_error_class_after_retry_exhaustion() -> None:
    client = FakeClient([FakeHTTPError(429, "rate limited"), FakeHTTPError(429, "rate limited")])
    adapter = OpenAIAdapter(
        client=client,
        retry_policy=RetryPolicy(max_retries=1, base_delay_s=0.01, max_delay_s=0.01, jitter_s=0.0),
        retry_seed=9,
        sleep_fn=lambda _delay: None,
    )

    text, meta = adapter.generate("Return JSON status.")
    assert text == ""
    assert meta["error_class"] == "rate_limit"
    assert meta["status_code"] == 429
    assert meta["retries"] == 1
    assert meta["attempts"] == 2
