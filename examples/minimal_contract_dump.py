"""Minimal contract and JSONL logging example for Rulecraft v0.1."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.contracts import (  # noqa: E402
    RunLog,
    TraceBundle,
    ValidationResult,
    is_confirmed_pass,
    is_pass,
)
from rulecraft.ids import new_run_id, stable_hash_id  # noqa: E402
from rulecraft.logging.jsonl import append_runlog  # noqa: E402


def main() -> None:
    run_id = new_run_id()
    input_ref = f"sha1:{stable_hash_id('example input payload')}"
    output_ref = f"sha1:{stable_hash_id('example output payload')}"

    validation_result = ValidationResult(
        validator_id="validator.l1.default",
        verdict="PASS",
        outcome="OK",
        score=0.97,
        reason_codes=["RULESET_OK"],
        violated_constraints=[],
        score_evidence={"signals": ["syntax", "safety"]},
        fgfc={"family": "default"},
        failure_cluster_id=None,
        notes="v0.1 sample",
    )

    runlog = RunLog(
        run_id=run_id,
        input_ref=input_ref,
        bucket_id="bucket-example",
        run_tags=["example", "v0.1"],
        control_signals={"trust_mode": "untrusted"},
        applied_rules=[
            {
                "rule_id": "RB-0001",
                "version": "0.1.0",
                "type": "GuardrailRule",
                "injection_mode": "system_guard",
            }
        ],
        run={"mode": "main", "cfg": {"temperature": 0.0}},
        exec={"mode": "untrusted", "config": {"advanced_modules": False}},
        outputs={"output_ref": output_ref},
        validator={
            "validator_id": validation_result.validator_id,
            "verdict": validation_result.verdict,
            "outcome": validation_result.outcome,
            "reason_codes": validation_result.reason_codes,
            "violated_constraints": validation_result.violated_constraints,
            "failure_cluster_id": validation_result.failure_cluster_id,
        },
        cost={"unit": "tokens", "value": 0},
        context_select={
            "enabled": False,
            "version": "context_select_v1",
            "policy": "l0_only",
            "candidate_context_ids": [],
            "injected_context_ids": [],
        },
    )

    trace_bundle = TraceBundle(
        run_id=run_id,
        bucket_id="bucket-example",
        refs={"input_ref": input_ref, "output_ref": output_ref},
        used_rule_ids=["RB-0001"],
        notes="Refs only; never store raw PII/secrets.",
    )

    print("ValidationResult")
    print(json.dumps(validation_result.to_dict(), ensure_ascii=False, sort_keys=True, indent=2))
    print(f"is_pass={is_pass(validation_result)}")
    print(f"is_confirmed_pass={is_confirmed_pass(validation_result)}")
    print()

    print("RunLog")
    print(json.dumps(runlog.to_dict(), ensure_ascii=False, sort_keys=True, indent=2))
    print()

    print("TraceBundle")
    print(json.dumps(trace_bundle.to_dict(), ensure_ascii=False, sort_keys=True, indent=2))

    append_runlog(str(ROOT / "logs" / "runlog.jsonl"), runlog)
    print("Appended logs/runlog.jsonl")


if __name__ == "__main__":
    main()
