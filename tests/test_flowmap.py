from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.analysis.flowmap import analyze_flowmap
from rulecraft.cli import main


def _event(
    *,
    trace_id: str,
    task_id: str,
    bucket_key: str | None,
    attempt_idx: int,
    phase: str,
    verdict: str,
    outcome: str,
    pass_value: int,
    cluster_id: str | None = None,
    reason_codes: list[str] | None = None,
    violated_constraints: list[str] | None = None,
    scale: dict[str, object] | None = None,
    cost_usd: float | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
) -> dict[str, object]:
    run_extra: dict[str, object] = {"task_id": task_id, "attempt_idx": attempt_idx, "phase": phase}
    if scale is not None:
        run_extra["scale"] = scale
    return {
        "trace_id": trace_id,
        "x_ref": f"x-{trace_id}",
        "bucket_key": bucket_key,
        "selected_rules": [],
        "run": {"task_id": task_id, "extra": run_extra},
        "verifier": {
            "verifier_id": "vf_l1_v1",
            "verdict": verdict,
            "outcome": outcome,
            "reason_codes": reason_codes,
            "violated_constraints": violated_constraints,
            "pass": pass_value,
            "failure_cluster_id": cluster_id,
        },
        "cost": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "meta": {"backend": "stub", "model": "stub", "cost_usd": cost_usd, "error": None},
        },
    }


def test_analyze_flowmap_computes_phase_gains_and_efficiency(tmp_path: Path) -> None:
    path = tmp_path / "flowmap.jsonl"
    rows = [
        _event(
            trace_id="a1-0",
            task_id="a1",
            bucket_key="alpha",
            attempt_idx=0,
            phase="primary",
            verdict="FAIL",
            outcome="UNKNOWN",
            pass_value=0,
            cluster_id="fc_parse",
            reason_codes=["FORMAT_LEAK", "JSON_PARSE"],
            violated_constraints=["FORMAT:JSON_PARSE"],
            cost_usd=0.1,
            tokens_in=50,
            tokens_out=50,
        ),
        _event(
            trace_id="a1-1",
            task_id="a1",
            bucket_key="alpha",
            attempt_idx=1,
            phase="repair",
            verdict="PASS",
            outcome="OK",
            pass_value=1,
            cost_usd=0.2,
            tokens_in=40,
            tokens_out=60,
        ),
        _event(
            trace_id="a2-0",
            task_id="a2",
            bucket_key="alpha",
            attempt_idx=0,
            phase="primary",
            verdict="FAIL",
            outcome="FAIL",
            pass_value=0,
            cluster_id="fc_schema",
            reason_codes=["SCHEMA_VIOLATION"],
            violated_constraints=["SCHEMA:JSONSCHEMA:$.count:type"],
            cost_usd=0.1,
            tokens_in=60,
            tokens_out=40,
        ),
        _event(
            trace_id="a2-1",
            task_id="a2",
            bucket_key="alpha",
            attempt_idx=1,
            phase="scale_probe",
            verdict="PASS",
            outcome="OK",
            pass_value=1,
            scale={"k": 3, "used_synth": False, "synth_verdict": None, "synth_outcome": None},
            cost_usd=0.3,
            tokens_in=120,
            tokens_out=180,
        ),
        _event(
            trace_id="a3-0",
            task_id="a3",
            bucket_key="alpha",
            attempt_idx=0,
            phase="primary",
            verdict="FAIL",
            outcome="FAIL",
            pass_value=0,
            cluster_id="fc_schema",
            reason_codes=["SCHEMA_VIOLATION"],
            violated_constraints=["SCHEMA:JSONSCHEMA:$.count:type"],
            cost_usd=0.1,
            tokens_in=60,
            tokens_out=40,
        ),
        _event(
            trace_id="a3-1",
            task_id="a3",
            bucket_key="alpha",
            attempt_idx=1,
            phase="scale_probe",
            verdict="FAIL",
            outcome="FAIL",
            pass_value=0,
            cluster_id="fc_schema",
            reason_codes=["SCHEMA_VIOLATION"],
            violated_constraints=["SCHEMA:JSONSCHEMA:$.count:type"],
            scale={"k": 3, "used_synth": False, "synth_verdict": None, "synth_outcome": None},
            cost_usd=0.3,
            tokens_in=120,
            tokens_out=180,
        ),
        _event(
            trace_id="a3-2",
            task_id="a3",
            bucket_key="alpha",
            attempt_idx=2,
            phase="scale_full",
            verdict="PASS",
            outcome="OK",
            pass_value=1,
            scale={"k": 8, "used_synth": True, "synth_verdict": "PASS", "synth_outcome": "OK"},
            cost_usd=0.9,
            tokens_in=240,
            tokens_out=360,
        ),
        _event(
            trace_id="b1-0",
            task_id="b1",
            bucket_key="beta",
            attempt_idx=0,
            phase="primary",
            verdict="FAIL",
            outcome="UNKNOWN",
            pass_value=0,
            cluster_id="fc_parse",
            reason_codes=["FORMAT_LEAK", "JSON_PARSE"],
            violated_constraints=["FORMAT:JSON_PARSE"],
            cost_usd=0.1,
            tokens_in=50,
            tokens_out=50,
        ),
    ]

    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")

    summary = analyze_flowmap(str(path))
    assert set(summary.keys()) == {"group_by", "risk_map", "opportunity_map"}
    assert set(summary["risk_map"].keys()) == {"alpha", "beta"}

    alpha_risk = summary["risk_map"]["alpha"]
    alpha_opp = summary["opportunity_map"]["alpha"]
    assert alpha_risk["tasks_total"] == 3
    assert alpha_risk["task_pass_rate"] == 1.0
    assert alpha_risk["strong_pass_rate"] == 1.0
    assert alpha_risk["top_failure_clusters"]

    assert alpha_opp["repair_gain"] > 0.0
    assert alpha_opp["probe_gain"] > 0.0
    assert alpha_opp["full_gain"] > 0.0
    assert alpha_opp["synth_gain"] > 0.0
    assert "repair" in alpha_opp["gain_per_usd"]
    assert alpha_opp["gain_per_usd"]["repair"] is not None
    assert "scale_probe" in alpha_opp["gain_per_token"]
    assert alpha_opp["gain_per_token"]["scale_probe"] is not None

    beta_risk = summary["risk_map"]["beta"]
    assert beta_risk["tasks_total"] == 1
    assert beta_risk["unknown_rate"] == 1.0


def test_flowmap_cli_prints_json(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "flowmap_cli.jsonl"
    path.write_text(
        json.dumps(
            _event(
                trace_id="cli-1",
                task_id="task-cli",
                bucket_key="alpha",
                attempt_idx=0,
                phase="primary",
                verdict="PASS",
                outcome="OK",
                pass_value=1,
                cost_usd=0.0,
                tokens_in=1,
                tokens_out=1,
            )
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(["flowmap", "--path", str(path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "risk_map" in payload
    assert "opportunity_map" in payload
