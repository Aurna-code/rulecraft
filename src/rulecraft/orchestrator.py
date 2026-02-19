"""Core v0.1 orchestration hot-loop."""

from __future__ import annotations

from typing import Any

from .adapters.base import BackendAdapter
from .contracts import RunLog
from .ids import new_run_id
from .logging.jsonl import append_runlog
from .policy.budget import BudgetController
from .policy.repair import build_json_repair_messages
from .rulebook.injection import build_injection_plan
from .rulebook.select import RuleSelectRequest, select_rules
from .validator.l1_static import validate_l1


class Orchestrator:
    def __init__(self, budget_controller: BudgetController | None = None) -> None:
        self.budget_controller = budget_controller or BudgetController()

    def run(
        self,
        input_text: str,
        context: dict[str, Any],
        constraints: dict[str, Any],
        rulebook_store: Any,
        adapter: BackendAdapter,
        runlog_path: str,
    ) -> tuple[str, dict[str, Any]]:
        run_id = new_run_id()
        input_ref = f"mem://input/{run_id}"
        output_ref = f"mem://output/{run_id}"

        select_constraints = {
            "max_rules": int(constraints.get("max_rules", 3)),
            "allow_types": constraints.get("allow_types") or ["StrategyRule", "GuardrailRule"],
        }
        request = RuleSelectRequest(
            request_id=f"req-{run_id}",
            input_ref=input_ref,
            bucket_id=context.get("bucket_id"),
            context=context,
            constraints=select_constraints,
            status=None,
        )
        selection = select_rules(request, rulebook_store)
        applied_rules = selection.applied_rules

        injection_plan = build_injection_plan(applied_rules=applied_rules, input_text=input_text)

        messages: list[dict[str, str]] = []
        for text in injection_plan["system"]:
            messages.append({"role": "system", "content": text})
        for text in injection_plan["prepend"]:
            messages.append({"role": "system", "content": text})
        if injection_plan["inline"]:
            inline_text = "\n".join(injection_plan["inline"])
            messages.append({"role": "user", "content": inline_text})
        messages.append({"role": "user", "content": input_text})

        first_output, first_meta = adapter.generate(messages)
        first_validation = validate_l1(first_output, constraints)
        adapter_calls = 1

        final_output = first_output
        final_validation = first_validation
        repair_attempted = False

        violated_constraints = set(first_validation.violated_constraints or [])
        if constraints.get("json_only") is True and "FORMAT:JSON_ONLY" in violated_constraints:
            repair_attempted = True
            repair_messages = build_json_repair_messages(messages, first_output, constraints)
            repaired_output, repair_meta = adapter.generate(repair_messages)
            adapter_calls += 1
            final_output = repaired_output
            final_validation = validate_l1(repaired_output, constraints)
        else:
            repair_meta = None

        early_exit = final_validation.verdict == "PASS" and final_validation.outcome == "OK"
        should_escalate = self.budget_controller.should_escalate(final_validation, context)
        repair_succeeded = repair_attempted and early_exit

        call_metas = [first_meta]
        if repair_meta is not None:
            call_metas.append(repair_meta)

        latency_values = [value for value in (meta.get("latency_ms") for meta in call_metas) if isinstance(value, int)]
        tokens_in_values = [value for value in (meta.get("tokens_in") for meta in call_metas) if isinstance(value, int)]
        tokens_out_values = [value for value in (meta.get("tokens_out") for meta in call_metas) if isinstance(value, int)]
        tool_call_values = [value for value in (meta.get("tool_calls") for meta in call_metas) if isinstance(value, int)]

        latency_ms = sum(latency_values) if latency_values else None
        tokens_in = sum(tokens_in_values) if tokens_in_values else None
        tokens_out = sum(tokens_out_values) if tokens_out_values else None
        tool_calls = sum(tool_call_values) if tool_call_values else 0

        if early_exit:
            exit_reason = "repaired_pass" if repair_attempted else "confirmed_pass"
        else:
            exit_reason = "needs_escalation"

        runlog = RunLog(
            run_id=run_id,
            input_ref=input_ref,
            bucket_id=context.get("bucket_id"),
            applied_rules=[
                {
                    "rule_id": rule.get("rule_id"),
                    "version": rule.get("version"),
                    "type": rule.get("type"),
                    "injection_mode": rule.get("injection_mode"),
                }
                for rule in applied_rules
            ],
            run={
                "mode": "main",
                "cfg": {
                    "adapter_mode": call_metas[-1].get("adapter_mode"),
                    "json_only": bool(constraints.get("json_only")),
                    "length_lte": constraints.get("length_lte"),
                    "repair_attempted": repair_attempted,
                },
            },
            outputs={"output_ref": output_ref},
            validator={
                "validator_id": final_validation.validator_id,
                "verdict": final_validation.verdict,
                "outcome": final_validation.outcome,
                "reason_codes": final_validation.reason_codes,
                "violated_constraints": final_validation.violated_constraints,
                "failure_cluster_id": final_validation.failure_cluster_id,
            },
            cost={
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "tool_calls": tool_calls,
            },
            control_signals={
                "budget_tier": self.budget_controller.tier,
                "should_escalate": should_escalate,
                "early_exit": early_exit,
                "repair_attempted": repair_attempted,
                "repair_succeeded": repair_succeeded,
                "adapter_calls": adapter_calls,
                "exit_stage": "l1_repair" if repair_attempted else "l1",
                "exit_reason": exit_reason,
            },
        )
        runlog_dict = runlog.to_dict()
        append_runlog(runlog_path, runlog_dict)
        return final_output, runlog_dict
