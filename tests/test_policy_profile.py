from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.scripted import ScriptedAdapter
from rulecraft.cli import main
from rulecraft.policy.profile import apply_overrides, load_profile, match_bucket
from rulecraft.runner.batch import run_batch


def test_policy_profile_load_match_and_merge(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "version": 1,
                "rules": [
                    {"bucket_match": "alpha", "overrides": {"scale": "probe", "k_probe": 3}},
                    {"bucket_match": "regex:^beta", "overrides": {"max_attempts": 2}},
                ],
            }
        ),
        encoding="utf-8",
    )

    profile = load_profile(profile_path)
    assert match_bucket(profile, "alpha.fast") == {"scale": "probe", "k_probe": 3}
    assert match_bucket(profile, "beta.core") == {"max_attempts": 2}
    assert match_bucket(profile, "gamma") == {}

    merged = apply_overrides({"scale": "off", "k_probe": 1, "top_m": 2}, {"scale": "probe"})
    assert merged == {"scale": "probe", "k_probe": 1, "top_m": 2}


def test_run_batch_applies_policy_profile_per_bucket(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_policy.jsonl"
    out_path = tmp_path / "eventlog_policy.jsonl"
    tasks_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "task-alpha",
                        "prompt": "Return JSON for alpha.",
                        "mode": "json",
                        "bucket_key": "alpha.fast",
                    }
                ),
                json.dumps(
                    {
                        "task_id": "task-beta",
                        "prompt": "Return JSON for beta.",
                        "mode": "json",
                        "bucket_key": "beta.slow",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile = {
        "version": 1,
        "rules": [
            {
                "bucket_match": "alpha",
                "overrides": {
                    "max_attempts": 2,
                    "scale": "probe",
                    "k_probe": 2,
                    "budget_tokens": 1000,
                },
            }
        ],
    }

    adapter = ScriptedAdapter(
        scripts={
            "task-alpha": ["not-json", "still-not-json"],
            "task-beta": ["not-json", "still-not-json"],
        },
        phase_scripts={
            "task-alpha": {
                "scale_probe_candidate": ['{"status":"ok"}', "still-not-json"],
            }
        },
    )

    summary = run_batch(
        tasks_path=tasks_path,
        adapter=adapter,
        out_path=out_path,
        repair=True,
        max_attempts=1,
        scale="off",
        k_probe=1,
        top_m=1,
        synth=False,
        policy_profile=profile,
    )
    assert summary == {"total": 2, "passed": 1, "failed": 0, "unknown": 1}

    events = [json.loads(line) for line in out_path.read_text(encoding="utf-8").strip().splitlines()]
    phases_by_task: dict[str, list[str]] = {}
    policy_by_task: dict[str, dict[str, object]] = {}
    for event in events:
        task_id = event["run"]["task_id"]
        phases_by_task.setdefault(task_id, []).append(event["run"]["extra"]["phase"])
        policy_by_task[task_id] = event["run"]["extra"]["policy"]

    assert phases_by_task["task-alpha"] == ["primary", "repair", "scale_probe"]
    assert phases_by_task["task-beta"] == ["primary"]

    assert policy_by_task["task-alpha"]["matched"] is True
    assert policy_by_task["task-alpha"]["overrides"]["scale"] == "probe"
    assert policy_by_task["task-beta"]["matched"] is False


def test_run_batch_cli_accepts_policy_profile(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tasks_path = tmp_path / "tasks_cli_policy.jsonl"
    out_path = tmp_path / "eventlog_cli_policy.jsonl"
    profile_path = tmp_path / "profile_cli.json"

    tasks_path.write_text(
        json.dumps({"task_id": "task-1", "prompt": "Return JSON.", "mode": "json", "bucket_key": "alpha.fast"}) + "\n",
        encoding="utf-8",
    )
    profile_path.write_text(
        json.dumps({"version": 1, "rules": [{"bucket_match": "alpha", "overrides": {"scale": "probe", "k_probe": 2}}]}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run-batch",
            "--tasks",
            str(tasks_path),
            "--adapter",
            "stub",
            "--out",
            str(out_path),
            "--policy-profile",
            str(profile_path),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 1
