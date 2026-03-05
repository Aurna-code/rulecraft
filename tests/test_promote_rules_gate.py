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
from rulecraft.runner.promote_rules import run_rule_promotion


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def _write_rulebook(path: Path, *, body: str, rule_id: str = "RB-1") -> None:
    payload = {
        "rulebook_name": "Rulebook",
        "rules": [
            {
                "schema_version": "0.1.0",
                "rule_id": rule_id,
                "version": "0.1.0",
                "type": "StrategyRule",
                "status": "active",
                "title": "JSON policy",
                "body": body,
                "applicability": {"bucket_ids": ["alpha"]},
                "priority": {"guardrail_first": False, "rank": 1},
                "injection_mode": "prepend",
                "evidence": {"run_ids": [], "validator_ids": [], "regression_ids": []},
                "tests": {"regression_tests": [], "counterexample_tests": []},
                "metrics": {"utility_q_ema": 0.0, "pass_p_hat": None, "pass_p_lb95": None, "pass_p_K": None},
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _adapter_factory(*, baseline_json: bool, candidate_json: bool):
    def factory(label: str) -> ScriptedAdapter:
        if label == "baseline":
            as_json = baseline_json
        else:
            as_json = candidate_json
        if as_json:
            scripts = {"task-1": ['{"status":"ok"}'], "task-2": ['{"status":"ok"}']}
        else:
            scripts = {"task-1": ["not-json"], "task-2": ["still-not-json"]}
        return ScriptedAdapter(scripts=scripts)

    return factory


def test_run_rule_promotion_passes_when_candidate_improves(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.jsonl"
    baseline_rulebook_path = tmp_path / "baseline_rulebook.json"
    candidate_rulebook_path = tmp_path / "candidate_rulebook.json"
    _write_jsonl(
        tasks_path,
        [
            {"task_id": "task-1", "prompt": "Return JSON status.", "mode": "json", "bucket_key": "alpha"},
            {"task_id": "task-2", "prompt": "Return JSON status.", "mode": "json", "bucket_key": "alpha"},
        ],
    )
    _write_rulebook(baseline_rulebook_path, body="Respond as usual.", rule_id="RB-BASE")
    _write_rulebook(candidate_rulebook_path, body="Output JSON only.", rule_id="RB-CAND")

    report = run_rule_promotion(
        tasks_path=tasks_path,
        adapter=_adapter_factory(baseline_json=False, candidate_json=True),
        baseline_rulebook_path=baseline_rulebook_path,
        candidate_rulebook_path=candidate_rulebook_path,
        policy_profile_path=None,
        tmp_dir=tmp_path / "tmp_gate",
    )

    assert report["ok"] is True
    assert report["deltas"]["task_pass_rate"] > 0.01
    assert report["deltas"]["strong_pass_rate"] > 0.01
    assert report["regressions"] == []
    assert report["rule_impact"]["improvements"]["tasks_improved"] == 2
    assert report["rule_impact"]["improvements"]["top_rules_on_improvements"][0]["rule_id"] == "RB-CAND"
    assert report["rule_impact"]["candidate"]["rule_selection_counts"]["RB-CAND"] > 0


def test_run_rule_promotion_fails_when_candidate_regresses(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks_regress.jsonl"
    baseline_rulebook_path = tmp_path / "baseline_regress_rulebook.json"
    candidate_rulebook_path = tmp_path / "candidate_regress_rulebook.json"
    _write_jsonl(
        tasks_path,
        [
            {"task_id": "task-1", "prompt": "Return JSON status.", "mode": "json", "bucket_key": "alpha"},
            {"task_id": "task-2", "prompt": "Return JSON status.", "mode": "json", "bucket_key": "alpha"},
        ],
    )
    _write_rulebook(baseline_rulebook_path, body="Output JSON only.", rule_id="RB-BASE")
    _write_rulebook(candidate_rulebook_path, body="Respond as usual.", rule_id="RB-CAND")

    report = run_rule_promotion(
        tasks_path=tasks_path,
        adapter=_adapter_factory(baseline_json=True, candidate_json=False),
        baseline_rulebook_path=baseline_rulebook_path,
        candidate_rulebook_path=candidate_rulebook_path,
        policy_profile_path=None,
        tmp_dir=tmp_path / "tmp_gate_regress",
    )

    assert report["ok"] is False
    assert any(item["metric"] == "strong_pass_rate" for item in report["regressions"])
    assert any(item["metric"] == "task_pass_rate" for item in report["regressions"])
    assert report["rule_impact"]["regressions"]["tasks_regressed"] == 2
    assert report["rule_impact"]["regressions"]["top_rules_on_regressions"][0]["rule_id"] == "RB-CAND"


def test_promote_rules_cli_fail_on_regression_returns_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tasks_path = tmp_path / "tasks_cli.jsonl"
    baseline_rulebook_path = tmp_path / "baseline_cli_rulebook.json"
    candidate_rulebook_path = tmp_path / "candidate_cli_rulebook.json"
    report_path = tmp_path / "report_cli.json"
    _write_jsonl(tasks_path, [{"task_id": "task-1", "prompt": "Return JSON status.", "mode": "json", "bucket_key": "alpha"}])
    _write_rulebook(baseline_rulebook_path, body="Output JSON only.")
    _write_rulebook(candidate_rulebook_path, body="Respond as usual.")

    monkeypatch.setattr(
        cli_module,
        "_build_batch_adapter",
        lambda _spec: _adapter_factory(baseline_json=True, candidate_json=False),
    )
    exit_code = main(
        [
            "promote-rules",
            "--tasks",
            str(tasks_path),
            "--adapter",
            "stub",
            "--baseline-rulebook",
            str(baseline_rulebook_path),
            "--candidate-rulebook",
            str(candidate_rulebook_path),
            "--report",
            str(report_path),
            "--fail-on-regression",
        ]
    )

    assert exit_code == 3
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["ok"] is False


def test_promote_rules_cli_openai_requires_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tasks_path = tmp_path / "tasks_openai.jsonl"
    baseline_rulebook_path = tmp_path / "baseline_openai_rulebook.json"
    candidate_rulebook_path = tmp_path / "candidate_openai_rulebook.json"
    _write_jsonl(tasks_path, [{"task_id": "task-1", "prompt": "x", "mode": "text", "bucket_key": "alpha"}])
    _write_rulebook(baseline_rulebook_path, body="Output JSON only.")
    _write_rulebook(candidate_rulebook_path, body="Output JSON only.")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "promote-rules",
            "--tasks",
            str(tasks_path),
            "--adapter",
            "openai",
            "--baseline-rulebook",
            str(baseline_rulebook_path),
            "--candidate-rulebook",
            str(candidate_rulebook_path),
        ]
    )
    assert exit_code == 2
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().out
