from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.scripted import ScriptedAdapter
from rulecraft.runner.batch import run_batch
from rulecraft.verifier.cache import InMemoryVerifierCache, SqliteVerifierCache, make_cache_key
from rulecraft.verifier.verify_output import verify_output


def test_verify_output_cache_hit_on_second_call() -> None:
    cache = InMemoryVerifierCache()
    meta_first: dict[str, object] = {}
    meta_second: dict[str, object] = {}

    first = verify_output(mode="json", y_text="not-json", contract=None, cache=cache, meta_out=meta_first)
    second = verify_output(mode="json", y_text="not-json", contract=None, cache=cache, meta_out=meta_second)

    assert first["verdict"] == second["verdict"]
    assert first["outcome"] == second["outcome"]
    assert meta_first["cache_hit"] is False
    assert meta_second["cache_hit"] is True
    expected_y_ref = hashlib.sha256("not-json".encode("utf-8")).hexdigest()
    assert first["layers"]["meta"]["y_ref"] == expected_y_ref
    assert second["layers"]["meta"]["y_ref"] == expected_y_ref


def test_make_cache_key_and_sqlite_cache_round_trip(tmp_path: Path) -> None:
    cache = SqliteVerifierCache(tmp_path / "verifier_cache.db")
    key = make_cache_key(
        schema_version="ssot-10",
        verifier_id="vf_l1_v1",
        mode="json",
        contract_id=None,
        y_ref="abc123",
    )
    value = {"verdict": "FAIL", "outcome": "UNKNOWN"}
    cache.set(key, value)
    assert cache.get(key) == value


def test_run_batch_logs_verifier_cache_hit_in_run_extra_only(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_cache.jsonl"
    out_path = tmp_path / "eventlog_cache.jsonl"
    tasks_path.write_text(
        json.dumps({"task_id": "task-cache", "prompt": "Return JSON.", "mode": "json"}) + "\n",
        encoding="utf-8",
    )

    adapter = ScriptedAdapter(scripts={"task-cache": ["not-json", "not-json"]})
    cache = InMemoryVerifierCache()

    summary = run_batch(
        tasks_path=tasks_path,
        adapter=adapter,
        out_path=out_path,
        repair=True,
        max_attempts=2,
        verifier_cache=cache,
    )
    assert summary == {"total": 1, "passed": 0, "failed": 0, "unknown": 1}

    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])

    assert first["run"]["extra"].get("verifier_cache_hit") is None
    assert second["run"]["extra"].get("verifier_cache_hit") is True
    assert "cache_hit" not in second["verifier"]
