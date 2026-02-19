from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.rulebook.injection import build_injection_plan
from rulecraft.rulebook.select import RuleSelectRequest, select_rules
from rulecraft.rulebook.store import RulebookStore


def _write_sample_rulebook(path: Path) -> None:
    payload = {
        "rulebook_name": "Rulebook",
        "rules": [
            {
                "schema_version": "0.1.0",
                "rule_id": "R1",
                "version": "0.1.0",
                "status": "active",
                "type": "GuardrailRule",
                "title": "Safety first",
                "body": "Safety first",
                "applicability": {
                    "domain_tag": "payments",
                    "task_family": "answer",
                    "bucket_ids": ["support"],
                },
                "priority": {"guardrail_first": True, "rank": 3},
                "evidence": {"run_ids": [], "validator_ids": [], "regression_ids": []},
                "tests": {"regression_tests": [], "counterexample_tests": []},
                "metrics": {"utility_q_ema": 0.0, "pass_p_hat": None, "pass_p_lb95": None, "pass_p_K": None},
            },
            {
                "schema_version": "0.1.0",
                "rule_id": "R2",
                "version": "0.1.0",
                "status": "active",
                "type": "StrategyRule",
                "title": "Procedure ranked first among equals",
                "body": "Procedure ranked first among equals",
                "applicability": {
                    "domain_tag": "payments",
                    "task_family": "answer",
                    "bucket_ids": ["support"],
                },
                "priority": {"guardrail_first": False, "rank": 1},
                "evidence": {"run_ids": [], "validator_ids": [], "regression_ids": []},
                "tests": {"regression_tests": [], "counterexample_tests": []},
                "metrics": {"utility_q_ema": 0.0, "pass_p_hat": None, "pass_p_lb95": None, "pass_p_K": None},
            },
            {
                "schema_version": "0.1.0",
                "rule_id": "R3",
                "version": "0.1.0",
                "status": "temporary",
                "type": "StrategyRule",
                "title": "Temporary rule",
                "body": "Temporary rule",
                "applicability": {
                    "domain_tag": "payments",
                    "task_family": "answer",
                    "bucket_ids": ["support"],
                },
                "priority": {"guardrail_first": False, "rank": 2},
                "evidence": {"run_ids": [], "validator_ids": [], "regression_ids": []},
                "tests": {"regression_tests": [], "counterexample_tests": []},
                "metrics": {"utility_q_ema": 0.0, "pass_p_hat": None, "pass_p_lb95": None, "pass_p_K": None},
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_store_load_and_filter(tmp_path: Path) -> None:
    rulebook_path = tmp_path / "rulebook.json"
    _write_sample_rulebook(rulebook_path)

    store = RulebookStore.load_from_json(rulebook_path)
    assert len(store.list()) == 3
    assert len(store.list(status="active")) == 2
    assert len(store.list(status="temporary")) == 1


def test_select_rules_scoring_and_max_rules(tmp_path: Path) -> None:
    rulebook_path = tmp_path / "rulebook.json"
    _write_sample_rulebook(rulebook_path)
    store = RulebookStore.load_from_json(rulebook_path)

    request = RuleSelectRequest(
        request_id="req-test-1",
        input_ref="sha1:test",
        bucket_id="support",
        context={"domain_tag": "payments", "task_family": "answer"},
        constraints={"max_rules": 2, "allow_types": ["StrategyRule", "GuardrailRule"]},
        status=None,
    )
    response = select_rules(request, store)

    assert [rule["rule_id"] for rule in response.applied_rules] == ["R1", "R2"]
    assert [rule["type"] for rule in response.applied_rules] == ["GuardrailRule", "StrategyRule"]
    assert response.applied_rules[0]["injection_mode"] == "system_guard"
    assert response.applied_rules[1]["injection_mode"] == "prepend"
    assert len(response.applied_rules) == 2


def test_build_injection_plan() -> None:
    applied_rules = [
        {
            "rule_id": "R1",
            "version": "0.1.0",
            "type": "GuardrailRule",
            "injection_mode": "system_guard",
            "body": "Do not request card secrets.",
        },
        {
            "rule_id": "R2",
            "version": "0.1.0",
            "type": "StrategyRule",
            "injection_mode": "prepend",
            "body": "Respond with 3 steps.",
        },
        {
            "rule_id": "R3",
            "version": "0.1.0",
            "type": "StrategyRule",
            "injection_mode": "inline",
            "body": "Mention delivery timeline.",
        },
    ]

    plan = build_injection_plan(applied_rules, "sample input")

    assert plan["system"] == ["Do not request card secrets."]
    assert plan["prepend"] == ["Respond with 3 steps."]
    assert plan["inline"] == ["Mention delivery timeline."]
