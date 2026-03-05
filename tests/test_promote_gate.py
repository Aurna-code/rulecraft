from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.scripted import ScriptedAdapter
from rulecraft.cli import main
import rulecraft.cli as cli_module
from rulecraft.runner.promote import run_promotion


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def _write_profile(path: Path, max_attempts: int) -> None:
    payload = {
        "version": 1,
        "rules": [{"bucket_match": "alpha", "overrides": {"max_attempts": max_attempts, "scale": "off"}}],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_run_promotion_passes_when_candidate_improves(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    _write_jsonl(
        tasks_path,
        [{"task_id": "task-1", "prompt": "Return JSON status.", "mode": "json", "bucket_key": "alpha"}],
    )
    baseline_profile = {"version": 1, "rules": [{"bucket_match": "alpha", "overrides": {"max_attempts": 1}}]}
    candidate_profile = {"version": 1, "rules": [{"bucket_match": "alpha", "overrides": {"max_attempts": 2}}]}
    adapter = ScriptedAdapter(scripts={"task-1": ["not-json", '{"status":"ok"}']})

    report = run_promotion(
        tasks_path=tasks_path,
        adapter=adapter,
        baseline_profile=baseline_profile,
        candidate_profile=candidate_profile,
        tmp_dir=tmp_path / "promote_tmp",
    )

    assert report["ok"] is True
    assert report["deltas"]["task_pass_rate"] > 0.01
    assert "avg_attempts_per_task" in report["deltas"]
    assert "cost_usd_total" in report["deltas"]
    assert "schema_violation_rate" in report["deltas"]


def test_run_promotion_fails_when_candidate_regresses(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_regress.jsonl"
    _write_jsonl(
        tasks_path,
        [{"task_id": "task-1", "prompt": "Return JSON status.", "mode": "json", "bucket_key": "alpha"}],
    )
    baseline_profile = {"version": 1, "rules": [{"bucket_match": "alpha", "overrides": {"max_attempts": 2}}]}
    candidate_profile = {"version": 1, "rules": [{"bucket_match": "alpha", "overrides": {"max_attempts": 1}}]}
    adapter = ScriptedAdapter(scripts={"task-1": ["not-json", '{"status":"ok"}']})

    report = run_promotion(
        tasks_path=tasks_path,
        adapter=adapter,
        baseline_profile=baseline_profile,
        candidate_profile=candidate_profile,
        tmp_dir=tmp_path / "promote_tmp_regress",
    )

    assert report["ok"] is False
    assert report["exit_code"] == 1
    assert any(item["metric"] == "task_pass_rate" for item in report["regressions"])


def test_promote_cli_fail_on_regression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tasks_path = tmp_path / "tasks_cli.jsonl"
    baseline_profile_path = tmp_path / "baseline.json"
    candidate_profile_path = tmp_path / "candidate.json"
    report_path = tmp_path / "report.json"
    _write_jsonl(
        tasks_path,
        [{"task_id": "task-1", "prompt": "Return JSON status.", "mode": "json", "bucket_key": "alpha"}],
    )
    _write_profile(baseline_profile_path, max_attempts=2)
    _write_profile(candidate_profile_path, max_attempts=1)
    monkeypatch.setattr(
        cli_module,
        "_build_batch_adapter",
        lambda _spec: ScriptedAdapter(scripts={"task-1": ["not-json", '{"status":"ok"}']}),
    )

    exit_code = main(
        [
            "promote",
            "--tasks",
            str(tasks_path),
            "--adapter",
            "stub",
            "--baseline-profile",
            str(baseline_profile_path),
            "--candidate-profile",
            str(candidate_profile_path),
            "--report",
            str(report_path),
            "--fail-on-regression",
        ]
    )

    assert exit_code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["deltas"]["task_pass_rate"] < 0.0


def test_promote_cli_openai_requires_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tasks_path = tmp_path / "tasks_openai.jsonl"
    baseline_profile_path = tmp_path / "baseline_openai.json"
    candidate_profile_path = tmp_path / "candidate_openai.json"
    _write_jsonl(tasks_path, [{"task_id": "task-1", "prompt": "x", "mode": "text", "bucket_key": "alpha"}])
    _write_profile(baseline_profile_path, max_attempts=1)
    _write_profile(candidate_profile_path, max_attempts=1)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "promote",
            "--tasks",
            str(tasks_path),
            "--adapter",
            "openai",
            "--baseline-profile",
            str(baseline_profile_path),
            "--candidate-profile",
            str(candidate_profile_path),
        ]
    )

    assert exit_code == 2
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().out
