from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.stub import StubAdapter
from rulecraft.adapters.tape import TapeRecorderAdapter, TapeReplayAdapter, TapeReplayMissError


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_tape_recorder_and_replay_round_trip_with_stub(tmp_path: Path) -> None:
    tape_path = tmp_path / "adapter.tape.jsonl"
    recorder = TapeRecorderAdapter(StubAdapter(mode="text"), tape_path=tape_path, backend_name="stub")

    expected_first = recorder.generate("alpha prompt")
    expected_second = recorder.generate("beta prompt")

    rows = _read_jsonl(tape_path)
    assert len(rows) == 2
    assert rows[0]["tape_version"] == 1
    assert rows[0]["request"]["backend"] == "stub"
    assert rows[0]["request"]["prompt"] == "alpha prompt"
    assert rows[1]["request"]["prompt"] == "beta prompt"
    assert isinstance(rows[0]["request_hash"], str) and rows[0]["request_hash"]

    replay = TapeReplayAdapter(tape_path)
    replay_first = replay.generate("alpha prompt")
    replay_second = replay.generate("beta prompt")
    assert replay_first == expected_first
    assert replay_second == expected_second


def test_tape_replay_raises_for_missing_hash(tmp_path: Path) -> None:
    tape_path = tmp_path / "adapter.tape.jsonl"
    recorder = TapeRecorderAdapter(StubAdapter(mode="text"), tape_path=tape_path, backend_name="stub")
    recorder.generate("known prompt")

    replay = TapeReplayAdapter(tape_path)
    with pytest.raises(TapeReplayMissError) as exc:
        replay.generate("unknown prompt")
    assert "request_hash=" in str(exc.value)

