"""Batch task runner for offline experiments."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Iterator, Literal, Mapping

from ..contracts import EventLog, pass_from
from ..logging import append_event
from ..policy.budget_router import BudgetState, should_attempt_repair
from ..policy.repair_loop import build_repair_prompt
from ..rulebook.select import RuleSelectRequest, select_rules
from ..rulebook.store import RulebookStore
from ..verifier import verify_text

TaskMode = Literal["text", "json"]


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped.lstrip("-").isdigit():
            return int(stripped)
    return None


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_flow_tags(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    tags = [tag for tag in value if isinstance(tag, str) and tag]
    if not tags:
        return None
    return tags


def _extract_terms(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) >= 4}


def _normalize_selected_rule(rule: Mapping[str, Any]) -> dict[str, Any]:
    rule_type = rule.get("type")
    normalized_type = str(rule_type) if isinstance(rule_type, str) and rule_type else "UnknownRule"
    normalized = {
        "rule_id": str(rule.get("rule_id", "")),
        "version": str(rule.get("version", "legacy")),
        "type": normalized_type,
    }
    injection_mode = rule.get("injection_mode")
    if isinstance(injection_mode, str) and injection_mode:
        normalized["injection_mode"] = injection_mode
    body = rule.get("body")
    if isinstance(body, str) and body.strip():
        normalized["body"] = body.strip()
    return normalized


def _select_rules_for_task(task: Mapping[str, Any], rulebook_store: RulebookStore | None) -> list[dict[str, Any]]:
    if rulebook_store is None:
        return []

    task_id = str(task["task_id"])
    bucket_key = task.get("bucket_key")
    prompt = str(task["prompt"])
    flow_tags = task.get("flow_tags")
    flow_tags_list = flow_tags if isinstance(flow_tags, list) else []

    request = RuleSelectRequest(
        request_id=f"batch-{task_id}",
        input_ref=f"mem://task/{task_id}",
        bucket_id=bucket_key if isinstance(bucket_key, str) else None,
        context={"flow_tags": flow_tags_list},
        constraints={"max_rules": 3, "allow_types": ["StrategyRule", "GuardrailRule"]},
        status="active",
    )
    selected = [_normalize_selected_rule(rule) for rule in select_rules(request, rulebook_store).applied_rules]
    selected_ids = {rule["rule_id"] for rule in selected}

    task_terms = set(_extract_terms(prompt))
    for tag in flow_tags_list:
        if isinstance(tag, str):
            task_terms.update(_extract_terms(tag))

    keyword_matches: list[tuple[int, str, dict[str, Any]]] = []
    for rule in rulebook_store.list(status="active"):
        normalized = _normalize_selected_rule(rule)
        rule_id = normalized.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id:
            continue
        if rule_id in selected_ids:
            continue

        rule_terms = _extract_terms(str(rule.get("title", "")) + " " + str(rule.get("body", "")))
        overlap = len(task_terms & rule_terms)
        if overlap > 0:
            keyword_matches.append((-overlap, rule_id, normalized))

    keyword_matches.sort(key=lambda item: (item[0], item[1]))
    for _, _, normalized in keyword_matches:
        if len(selected) >= 3:
            break
        selected.append(normalized)
    return selected[:3]


def _inject_rulecraft_context(prompt: str, selected_rules: list[dict[str, Any]]) -> str:
    if not selected_rules:
        return prompt

    context_payload = [
        {
            "rule_id": str(rule.get("rule_id", "")),
            "version": str(rule.get("version", "legacy")),
            "type": str(rule.get("type", "UnknownRule")),
            "injection_mode": str(rule.get("injection_mode", "prepend")),
            "body": str(rule.get("body", "")),
        }
        for rule in selected_rules
    ]
    context_json = json.dumps({"selected_rules": context_payload}, ensure_ascii=False, sort_keys=True)
    return f"Rulecraft Context\n{context_json}\n\nTask Prompt\n{prompt}"


def _event_cost_usage(event_payload: Mapping[str, Any]) -> tuple[float, int]:
    cost = event_payload.get("cost")
    if not isinstance(cost, Mapping):
        return 0.0, 0

    tokens_in = _coerce_optional_int(cost.get("tokens_in")) or 0
    tokens_out = _coerce_optional_int(cost.get("tokens_out")) or 0
    token_total = tokens_in + tokens_out

    meta = cost.get("meta")
    if isinstance(meta, Mapping):
        cost_usd = _coerce_optional_float(meta.get("cost_usd")) or 0.0
    else:
        cost_usd = 0.0
    return cost_usd, token_total


def _iter_tasks(tasks_path: str | Path, limit: int | None) -> Iterator[dict[str, Any]]:
    path = Path(tasks_path)
    with path.open("r", encoding="utf-8") as fp:
        task_count = 0
        for line_no, line in enumerate(fp, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no} in {path}.") from exc

            if not isinstance(payload, dict):
                raise ValueError(f"Task on line {line_no} must be a JSON object.")

            task_id = payload.get("task_id")
            prompt = payload.get("prompt")
            mode = payload.get("mode")
            if not isinstance(task_id, str) or not task_id:
                raise ValueError(f"Task on line {line_no} is missing required string key 'task_id'.")
            if not isinstance(prompt, str) or not prompt:
                raise ValueError(f"Task on line {line_no} is missing required string key 'prompt'.")
            if mode not in ("text", "json"):
                raise ValueError(f"Task on line {line_no} must set mode to 'text' or 'json'.")

            bucket_key = payload.get("bucket_key")
            if not isinstance(bucket_key, str) or not bucket_key:
                bucket_key = None

            flow_tags = _coerce_flow_tags(payload.get("flow_tags"))

            yield {
                "task_id": task_id,
                "prompt": prompt,
                "mode": mode,
                "bucket_key": bucket_key,
                "flow_tags": flow_tags,
            }

            task_count += 1
            if limit is not None and task_count >= limit:
                break


def _generate(
    adapter: Any,
    prompt: str,
    instructions: str | None,
    *,
    task_id: str,
    attempt_idx: int,
    phase: str,
) -> tuple[str, dict[str, Any]]:
    kwargs = {
        "instructions": instructions,
        "task_id": task_id,
        "attempt_idx": attempt_idx,
        "phase": phase,
    }

    try:
        response = adapter.generate(prompt, **kwargs)
        if isinstance(response, tuple) and len(response) == 2:
            text, meta = response
            if isinstance(meta, dict):
                return str(text), dict(meta)
    except TypeError:
        pass

    if instructions:
        try:
            response = adapter.generate(prompt, instructions=instructions)
            if isinstance(response, tuple) and len(response) == 2:
                text, meta = response
                if isinstance(meta, dict):
                    return str(text), dict(meta)
        except TypeError:
            pass

    text, meta = adapter.generate(prompt)
    if not isinstance(meta, dict):
        return str(text), {}
    return str(text), dict(meta)


def run_batch(
    tasks_path: str | Path,
    adapter: Any,
    out_path: str | Path,
    instructions: str | None = None,
    limit: int | None = None,
    repair: bool = False,
    max_attempts: int = 1,
    budget_usd: float | None = None,
    budget_tokens: int | None = None,
    rulebook_store: RulebookStore | None = None,
) -> dict[str, int]:
    summary = {"total": 0, "passed": 0, "failed": 0, "unknown": 0}
    attempts_limit = max(int(max_attempts), 1) if repair else 1

    for task in _iter_tasks(tasks_path, limit):
        prompt = str(task["prompt"])
        mode = str(task["mode"])
        trace_id = str(uuid.uuid4())
        task_id = str(task["task_id"])
        selected_rules = _select_rules_for_task(task, rulebook_store)
        selected_rule_refs = [
            {
                "rule_id": str(rule.get("rule_id", "")),
                "version": str(rule.get("version", "legacy")),
                "type": str(rule.get("type", "UnknownRule")),
            }
            for rule in selected_rules
        ]

        primary_prompt = _inject_rulecraft_context(prompt, selected_rules)
        attempt_prompt = primary_prompt
        attempt_instructions = instructions
        final_verifier_result = None
        budget_state = BudgetState(
            max_attempts=attempts_limit,
            attempts_used=0,
            budget_usd=budget_usd,
            spent_usd=0.0,
            budget_tokens=budget_tokens,
            spent_tokens=0,
        )

        while budget_state.attempts_used < budget_state.max_attempts:
            attempt_idx = budget_state.attempts_used
            phase = "primary" if attempt_idx == 0 else "repair"
            text, meta = _generate(
                adapter,
                attempt_prompt,
                attempt_instructions,
                task_id=task_id,
                attempt_idx=attempt_idx,
                phase=phase,
            )
            verifier_result = verify_text(task_mode=mode, y=text)
            final_verifier_result = verifier_result

            cost_meta = {
                "backend": meta.get("backend", "unknown"),
                "model": meta.get("model", meta.get("model_name", "unknown")),
                "cost_usd": _coerce_optional_float(meta.get("cost_usd")),
                "error": meta.get("error"),
            }
            if meta.get("response_id") is not None:
                cost_meta["response_id"] = meta.get("response_id")

            event = EventLog(
                trace_id=trace_id,
                x_ref=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                bucket_key=task["bucket_key"],
                flow_tags=task["flow_tags"],
                selected_rules=selected_rule_refs,
                run={
                    "mode": "batch",
                    "task_id": task_id,
                    "extra": {
                        "task_id": task_id,
                        "attempt_idx": attempt_idx,
                        "phase": phase,
                        "max_attempts": attempts_limit,
                    },
                },
                outputs={"task_id": task_id},
                verifier={
                    "verifier_id": "vf_l1_v1",
                    "verdict": verifier_result.verdict,
                    "outcome": verifier_result.outcome,
                    "reason_codes": verifier_result.reason_codes,
                    "violated_constraints": verifier_result.violated_constraints,
                    "pass": pass_from(verifier_result),
                },
                cost={
                    "latency_ms": _coerce_optional_int(meta.get("latency_ms")),
                    "tokens_in": _coerce_optional_int(meta.get("tokens_in")),
                    "tokens_out": _coerce_optional_int(meta.get("tokens_out")),
                    "tool_calls": _coerce_optional_int(meta.get("tool_calls")),
                    "meta": cost_meta,
                },
            )
            append_event(str(out_path), event)
            event_payload = event.to_dict()
            cost_usd_value, token_value = _event_cost_usage(event_payload)
            budget_state.attempts_used += 1
            budget_state.spent_usd += cost_usd_value
            budget_state.spent_tokens += token_value

            if verifier_result.verdict == "PASS" and verifier_result.outcome != "FAIL":
                break
            if not repair:
                break
            if not should_attempt_repair(budget_state, event_payload):
                break

            verifier_payload = {
                "verdict": verifier_result.verdict,
                "outcome": verifier_result.outcome,
                "reason_codes": verifier_result.reason_codes,
                "violated_constraints": verifier_result.violated_constraints,
            }
            repair_prompt, repair_instructions = build_repair_prompt(
                task_prompt=primary_prompt,
                mode=mode,
                last_output=text,
                verifier=verifier_payload,
            )
            attempt_prompt = repair_prompt
            if instructions and repair_instructions:
                attempt_instructions = f"{instructions}\n{repair_instructions}"
            else:
                attempt_instructions = repair_instructions or instructions

        summary["total"] += 1
        if final_verifier_result is None:
            continue
        if final_verifier_result.verdict == "PASS" and final_verifier_result.outcome != "FAIL":
            summary["passed"] += 1
        elif final_verifier_result.outcome == "UNKNOWN":
            summary["unknown"] += 1
        else:
            summary["failed"] += 1

    return summary
