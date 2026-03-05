from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.analysis.diff_runs import diff_runs
from rulecraft.cli import main


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_run(
    run_dir: Path,
    *,
    created_utc: str,
    commit: str,
    summary: dict[str, object],
    policy_report: dict[str, object],
    metrics: dict[str, object],
) -> Path:
    manifest = {
        "version": 1,
        "created_utc": created_utc,
        "schema_version": "0.5.15",
        "git": {"commit": commit, "dirty": False},
        "inputs": {"tasks_path": str(run_dir / "tasks.jsonl"), "baseline_policy_profile_path": None, "baseline_rulebook_path": None},
        "params": {
            "adapter": "stub",
            "run_batch": {"scale": "off"},
            "regpack": {"seed": 1337},
            "promote": {"seed": 1337},
            "promote_rules": {"seed": 1337},
        },
        "outputs": {
            "summary": "summary.json",
            "policy_report": "policy_promote_report.json",
            "metrics": "metrics.json",
        },
    }
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "summary.json", summary)
    _write_json(run_dir / "policy_promote_report.json", policy_report)
    _write_json(run_dir / "metrics.json", metrics)
    return run_dir / "manifest.json"


def test_diff_runs_computes_metric_and_cluster_deltas(tmp_path: Path) -> None:
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    manifest_a = _make_run(
        run_a,
        created_utc="2026-03-01T00:00:00Z",
        commit="aaa111",
        summary={
            "key_deltas": {
                "task_pass_rate": 0.02,
                "strong_pass_rate": 0.01,
                "schema_violation_rate": -0.01,
                "cost_usd_total": 0.2,
            }
        },
        policy_report={"deltas": {"avg_attempts_per_task": 0.30}},
        metrics={
            "event_metrics": {
                "tokens_in_total": 100,
                "tokens_out_total": 80,
                "top_failure_clusters": [
                    {"cluster_id": "fc_a", "count": 4},
                    {"cluster_id": "fc_b", "count": 2},
                ],
            },
            "task_metrics": {"task_pass_rate": 0.60},
        },
    )
    manifest_b = _make_run(
        run_b,
        created_utc="2026-03-02T00:00:00Z",
        commit="bbb222",
        summary={
            "key_deltas": {
                "task_pass_rate": 0.05,
                "strong_pass_rate": 0.03,
                "schema_violation_rate": -0.03,
                "cost_usd_total": 0.1,
            }
        },
        policy_report={"deltas": {"avg_attempts_per_task": 0.10}},
        metrics={
            "event_metrics": {
                "tokens_in_total": 130,
                "tokens_out_total": 70,
                "top_failure_clusters": [
                    {"cluster_id": "fc_a", "count": 1},
                    {"cluster_id": "fc_c", "count": 3},
                ],
            },
            "task_metrics": {"task_pass_rate": 0.66},
        },
    )

    payload = diff_runs(str(manifest_a), str(manifest_b))
    deltas = payload["deltas"]["metrics"]
    assert deltas["task_pass_rate"] == pytest.approx(0.03)
    assert deltas["strong_pass_rate"] == pytest.approx(0.02)
    assert deltas["schema_violation_rate"] == pytest.approx(-0.02)
    assert deltas["avg_attempts_per_task"] == pytest.approx(-0.2)
    assert deltas["cost_usd_total"] == pytest.approx(-0.1)
    assert deltas["tokens_in_total"] == pytest.approx(30.0)
    assert deltas["tokens_out_total"] == pytest.approx(-10.0)

    cluster_changes = payload["deltas"]["top_failure_clusters"]["changes"]
    by_cluster = {row["cluster_id"]: row for row in cluster_changes}
    assert by_cluster["fc_a"]["delta_count"] == -3
    assert by_cluster["fc_c"]["delta_count"] == 3
    assert payload["improvements"]["metrics"]["task_pass_rate"] == pytest.approx(0.03)
    assert payload["regressions"]["metrics"]["tokens_in_total"] == pytest.approx(30.0)


def test_diff_runs_cli_prints_and_writes_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_a = tmp_path / "run_a_cli"
    run_b = tmp_path / "run_b_cli"
    manifest_a = _make_run(
        run_a,
        created_utc="2026-03-01T00:00:00Z",
        commit="aaa111",
        summary={"key_deltas": {"task_pass_rate": 0.0}},
        policy_report={"deltas": {}},
        metrics={"event_metrics": {"top_failure_clusters": []}},
    )
    manifest_b = _make_run(
        run_b,
        created_utc="2026-03-02T00:00:00Z",
        commit="bbb222",
        summary={"key_deltas": {"task_pass_rate": 0.1}},
        policy_report={"deltas": {}},
        metrics={"event_metrics": {"top_failure_clusters": []}},
    )
    out_path = tmp_path / "diff.json"

    exit_code = main(["diff-runs", "--a", str(manifest_a), "--b", str(manifest_b), "--out", str(out_path)])
    assert exit_code == 0
    payload_stdout = json.loads(capsys.readouterr().out)
    payload_file = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload_stdout["deltas"]["metrics"]["task_pass_rate"] == pytest.approx(0.1)
    assert payload_file["deltas"]["metrics"]["task_pass_rate"] == pytest.approx(0.1)
