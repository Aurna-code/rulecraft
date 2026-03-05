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
from ..policy.profile import apply_overrides, match_bucket
from ..policy.repair_loop import build_repair_prompt
from ..policy.should_scale import ScaleTier, escalate_to_full, should_scale
from ..rulebook.select import RuleSelectRequest, select_rules
from ..rulebook.store import RulebookStore
from ..verifier.cache import VerifierCache
from ..verifier.verify_output import verify_output
from .pacore_lite import run_pacore_lite

ScaleMode = Literal["off", "auto", "probe", "full"]


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


def _verifier_is_pass(verifier: Mapping[str, Any]) -> bool:
    return pass_from(verifier) == 1


def _verifier_outcome(verifier: Mapping[str, Any]) -> str:
    outcome = verifier.get("outcome")
    if isinstance(outcome, str) and outcome:
        return outcome
    return "UNKNOWN"


def _normalize_task_contract(contract: object, *, line_no: int, path: Path) -> dict[str, Any] | None:
    if contract is None:
        return None
    if not isinstance(contract, Mapping):
        raise ValueError(f"Task on line {line_no} in {path} has invalid 'contract' type.")

    contract_type = contract.get("type")
    if contract_type != "jsonschema":
        raise ValueError(f"Task on line {line_no} in {path} has unsupported contract type.")

    schema = contract.get("schema")
    if not isinstance(schema, Mapping):
        raise ValueError(f"Task on line {line_no} in {path} must include object 'contract.schema'.")

    schema_id_raw = contract.get("schema_id")
    if schema_id_raw is None:
        schema_id = None
    elif isinstance(schema_id_raw, str):
        schema_id = schema_id_raw or None
    else:
        schema_id = str(schema_id_raw)

    return {
        "type": "jsonschema",
        "schema": dict(schema),
        "schema_id": schema_id,
    }


def _contract_log_summary(contract: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(contract, Mapping):
        return None
    return {
        "type": contract.get("type"),
        "schema_id": contract.get("schema_id"),
        "has_schema": isinstance(contract.get("schema"), Mapping),
    }


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


def _cost_meta_from_adapter(meta: Mapping[str, Any]) -> dict[str, Any]:
    cost_meta = {
        "backend": meta.get("backend", "unknown"),
        "model": meta.get("model", meta.get("model_name", "unknown")),
        "cost_usd": _coerce_optional_float(meta.get("cost_usd")),
        "error": meta.get("error"),
        "error_class": meta.get("error_class"),
        "status_code": _coerce_optional_int(meta.get("status_code")),
        "attempts": _coerce_optional_int(meta.get("attempts")),
        "retries": _coerce_optional_int(meta.get("retries")),
        "retry_sleep_s_total": _coerce_optional_float(meta.get("retry_sleep_s_total")),
    }
    if meta.get("response_id") is not None:
        cost_meta["response_id"] = meta.get("response_id")
    return cost_meta


def _scale_budget_ok(state: BudgetState, last_event: Mapping[str, Any]) -> bool:
    if state.budget_usd is not None and state.spent_usd >= state.budget_usd:
        return False
    if state.budget_tokens is not None and state.spent_tokens >= state.budget_tokens:
        return False

    projected_usd, projected_tokens = _event_cost_usage(last_event)
    if state.budget_usd is not None and (state.spent_usd + projected_usd) > state.budget_usd:
        return False
    if state.budget_tokens is not None and (state.spent_tokens + projected_tokens) > state.budget_tokens:
        return False
    return True


def estimate_full_cost_usd(
    last_scale_event_cost_usd: float,
    k_probe: int,
    k_full: int,
    used_synth: bool,
) -> float:
    """Estimate full rollout USD from the probe rollout event cost."""
    base = max(float(last_scale_event_cost_usd), 0.0)
    probe_count = max(int(k_probe), 1)
    ratio = max(float(k_full) / probe_count, 1.0)
    projected = base * ratio
    if used_synth:
        projected += base / probe_count
    return projected


def _rollout_summary(scale_meta: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "tier": scale_meta.get("tier"),
        "k": scale_meta.get("k"),
        "top_m": scale_meta.get("top_m"),
        "used_synth": bool(scale_meta.get("used_synth", False)),
        "best_candidate_verdict": scale_meta.get("best_candidate_verdict"),
        "best_candidate_outcome": scale_meta.get("best_candidate_outcome"),
        "synth_verdict": scale_meta.get("synth_verdict"),
        "synth_outcome": scale_meta.get("synth_outcome"),
        "candidate_verdict_counts": scale_meta.get("candidate_verdict_counts", {}),
    }


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
            contract = _normalize_task_contract(payload.get("contract"), line_no=line_no, path=path)

            yield {
                "task_id": task_id,
                "prompt": prompt,
                "mode": mode,
                "bucket_key": bucket_key,
                "flow_tags": flow_tags,
                "contract": contract,
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
    scale: ScaleMode = "off",
    k_probe: int = 3,
    k_full: int = 8,
    top_m: int = 2,
    synth: bool = True,
    verifier_cache: VerifierCache | None = None,
    policy_profile: Mapping[str, Any] | None = None,
    seed: int | None = None,
) -> dict[str, int]:
    scale_mode = str(scale).lower()
    if scale_mode not in {"off", "auto", "probe", "full"}:
        raise ValueError(f"Unsupported scale mode: {scale!r}")

    if int(k_probe) < 1:
        raise ValueError("k_probe must be >= 1")
    if int(k_full) < 1:
        raise ValueError("k_full must be >= 1")
    if int(top_m) < 1:
        raise ValueError("top_m must be >= 1")

    default_task_policy = {
        "max_attempts": int(max_attempts),
        "scale": scale_mode,
        "k_probe": int(k_probe),
        "k_full": int(k_full),
        "top_m": int(top_m),
        "synth": bool(synth),
        "budget_usd": budget_usd,
        "budget_tokens": budget_tokens,
    }

    summary = {"total": 0, "passed": 0, "failed": 0, "unknown": 0}

    for task in _iter_tasks(tasks_path, limit):
        prompt = str(task["prompt"])
        mode = str(task["mode"])
        task_bucket_key = task.get("bucket_key")
        applied_policy_overrides = match_bucket(policy_profile, task_bucket_key if isinstance(task_bucket_key, str) else None)
        effective_policy = apply_overrides(default_task_policy, applied_policy_overrides)
        effective_max_attempts = _coerce_optional_int(effective_policy.get("max_attempts")) or int(max_attempts)
        task_attempts_limit = max(effective_max_attempts, 1) if repair else 1
        effective_scale_mode = str(effective_policy.get("scale", scale_mode))
        if effective_scale_mode not in {"off", "auto", "probe", "full"}:
            effective_scale_mode = scale_mode
        effective_k_probe = _coerce_optional_int(effective_policy.get("k_probe")) or int(k_probe)
        effective_k_full = _coerce_optional_int(effective_policy.get("k_full")) or int(k_full)
        effective_top_m = _coerce_optional_int(effective_policy.get("top_m")) or int(top_m)
        effective_synth = bool(effective_policy.get("synth", synth))
        effective_budget_usd = _coerce_optional_float(effective_policy.get("budget_usd"))
        effective_budget_tokens = _coerce_optional_int(effective_policy.get("budget_tokens"))
        policy_summary = None
        if policy_profile is not None:
            policy_summary = {
                "matched": bool(applied_policy_overrides),
                "overrides": dict(applied_policy_overrides) if applied_policy_overrides else None,
            }

        task_contract = task.get("contract")
        if isinstance(task_contract, Mapping):
            normalized_contract: dict[str, Any] | None = dict(task_contract)
        else:
            normalized_contract = None
        contract_summary = _contract_log_summary(normalized_contract)
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
        events_so_far: list[dict[str, Any]] = []
        budget_state = BudgetState(
            max_attempts=task_attempts_limit,
            attempts_used=0,
            budget_usd=effective_budget_usd,
            spent_usd=0.0,
            budget_tokens=effective_budget_tokens,
            spent_tokens=0,
        )

        def log_attempt_event(
            *,
            attempt_idx: int,
            phase: str,
            verifier_result: Mapping[str, Any],
            meta: Mapping[str, Any],
            scale_meta: Mapping[str, Any] | None = None,
            rollout: Mapping[str, Any] | None = None,
            verifier_cache_hit: bool = False,
        ) -> dict[str, Any]:
            run_extra: dict[str, Any] = {
                "task_id": task_id,
                "attempt_idx": attempt_idx,
                "phase": phase,
                "max_attempts": task_attempts_limit,
            }
            if verifier_cache_hit:
                run_extra["verifier_cache_hit"] = True
            if contract_summary is not None:
                run_extra["contract"] = dict(contract_summary)
            if policy_summary is not None:
                run_extra["policy"] = dict(policy_summary)
            if scale_meta is not None:
                run_extra["scale"] = dict(scale_meta)

            outputs: dict[str, Any] = {"task_id": task_id}
            if rollout is not None:
                outputs["rollout"] = dict(rollout)

            event = EventLog(
                trace_id=trace_id,
                x_ref=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                bucket_key=task["bucket_key"],
                flow_tags=task["flow_tags"],
                selected_rules=selected_rule_refs,
                run={
                    "mode": "batch",
                    "task_id": task_id,
                    "extra": run_extra,
                },
                outputs=outputs,
                verifier=dict(verifier_result),
                cost={
                    "latency_ms": _coerce_optional_int(meta.get("latency_ms")),
                    "tokens_in": _coerce_optional_int(meta.get("tokens_in")),
                    "tokens_out": _coerce_optional_int(meta.get("tokens_out")),
                    "tool_calls": _coerce_optional_int(meta.get("tool_calls")),
                    "meta": _cost_meta_from_adapter(meta),
                },
            )
            append_event(str(out_path), event)
            payload = event.to_dict()
            events_so_far.append(payload)

            cost_usd_value, token_value = _event_cost_usage(payload)
            budget_state.attempts_used += 1
            budget_state.spent_usd += cost_usd_value
            budget_state.spent_tokens += token_value
            return payload

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
            verifier_meta: dict[str, Any] = {}
            verifier_result = verify_output(
                mode=mode,
                y_text=text,
                contract=normalized_contract,
                cache=verifier_cache,
                meta_out=verifier_meta,
            )
            final_verifier_result = verifier_result
            event_payload = log_attempt_event(
                attempt_idx=attempt_idx,
                phase=phase,
                verifier_result=verifier_result,
                meta=meta,
                verifier_cache_hit=bool(verifier_meta.get("cache_hit", False)),
            )

            if _verifier_is_pass(verifier_result):
                break
            if not repair:
                break
            if not should_attempt_repair(budget_state, event_payload):
                break

            verifier_payload = {
                "verdict": verifier_result.get("verdict"),
                "outcome": verifier_result.get("outcome"),
                "reason_codes": verifier_result.get("reason_codes"),
                "violated_constraints": verifier_result.get("violated_constraints"),
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

        task_passed = final_verifier_result is not None and _verifier_is_pass(final_verifier_result)
        if not task_passed and effective_scale_mode != "off":
            tier: ScaleTier
            if effective_scale_mode in {"probe", "full"}:
                tier = effective_scale_mode
            else:
                tier = should_scale(events_so_far, mode)

            if tier == "probe":
                probe_attempt_idx = budget_state.attempts_used
                probe_text, probe_meta = run_pacore_lite(
                    primary_prompt,
                    mode,
                    adapter,
                    k=effective_k_probe,
                    top_m=effective_top_m,
                    use_synth=effective_synth,
                    instructions=instructions,
                    selected_rules=selected_rules,
                    contract=normalized_contract,
                    verifier_cache=verifier_cache,
                    tier="probe",
                    task_id=task_id,
                    attempt_idx=probe_attempt_idx,
                    seed=seed,
                )
                probe_verifier_meta: dict[str, Any] = {}
                probe_verifier = verify_output(
                    mode=mode,
                    y_text=probe_text,
                    contract=normalized_contract,
                    cache=verifier_cache,
                    meta_out=probe_verifier_meta,
                )
                final_verifier_result = probe_verifier

                probe_scale_meta = _rollout_summary(probe_meta)
                probe_meta_for_event = probe_meta.get("event_meta")
                if not isinstance(probe_meta_for_event, Mapping):
                    probe_meta_for_event = {}
                probe_event = log_attempt_event(
                    attempt_idx=probe_attempt_idx,
                    phase="scale_probe",
                    verifier_result=probe_verifier,
                    meta=probe_meta_for_event,
                    scale_meta=probe_scale_meta,
                    rollout=probe_scale_meta,
                    verifier_cache_hit=bool(probe_verifier_meta.get("cache_hit", False)),
                )

                budget_ok_for_full = _scale_budget_ok(budget_state, probe_event)
                if budget_ok_for_full and budget_state.budget_usd is not None:
                    probe_cost_usd, _ = _event_cost_usage(probe_event)
                    projected_full_usd = estimate_full_cost_usd(
                        probe_cost_usd,
                        k_probe=effective_k_probe,
                        k_full=effective_k_full,
                        used_synth=effective_synth,
                    )
                    budget_ok_for_full = (budget_state.spent_usd + projected_full_usd) <= budget_state.budget_usd

                if escalate_to_full(dict(probe_event), budget_ok=budget_ok_for_full):
                    full_attempt_idx = budget_state.attempts_used
                    full_text, full_meta = run_pacore_lite(
                        primary_prompt,
                        mode,
                        adapter,
                        k=effective_k_full,
                        top_m=effective_top_m,
                        use_synth=effective_synth,
                        instructions=instructions,
                        selected_rules=selected_rules,
                        contract=normalized_contract,
                        verifier_cache=verifier_cache,
                        tier="full",
                        task_id=task_id,
                        attempt_idx=full_attempt_idx,
                        seed=seed,
                    )
                    full_verifier_meta: dict[str, Any] = {}
                    full_verifier = verify_output(
                        mode=mode,
                        y_text=full_text,
                        contract=normalized_contract,
                        cache=verifier_cache,
                        meta_out=full_verifier_meta,
                    )
                    final_verifier_result = full_verifier

                    full_scale_meta = _rollout_summary(full_meta)
                    full_meta_for_event = full_meta.get("event_meta")
                    if not isinstance(full_meta_for_event, Mapping):
                        full_meta_for_event = {}
                    log_attempt_event(
                        attempt_idx=full_attempt_idx,
                        phase="scale_full",
                        verifier_result=full_verifier,
                        meta=full_meta_for_event,
                        scale_meta=full_scale_meta,
                        rollout=full_scale_meta,
                        verifier_cache_hit=bool(full_verifier_meta.get("cache_hit", False)),
                    )
            elif tier == "full":
                can_run_full = not events_so_far or _scale_budget_ok(budget_state, events_so_far[-1])
                if can_run_full:
                    full_attempt_idx = budget_state.attempts_used
                    full_text, full_meta = run_pacore_lite(
                        primary_prompt,
                        mode,
                        adapter,
                        k=effective_k_full,
                        top_m=effective_top_m,
                        use_synth=effective_synth,
                        instructions=instructions,
                        selected_rules=selected_rules,
                        contract=normalized_contract,
                        verifier_cache=verifier_cache,
                        tier="full",
                        task_id=task_id,
                        attempt_idx=full_attempt_idx,
                        seed=seed,
                    )
                    full_verifier_meta: dict[str, Any] = {}
                    full_verifier = verify_output(
                        mode=mode,
                        y_text=full_text,
                        contract=normalized_contract,
                        cache=verifier_cache,
                        meta_out=full_verifier_meta,
                    )
                    final_verifier_result = full_verifier

                    full_scale_meta = _rollout_summary(full_meta)
                    full_meta_for_event = full_meta.get("event_meta")
                    if not isinstance(full_meta_for_event, Mapping):
                        full_meta_for_event = {}
                    log_attempt_event(
                        attempt_idx=full_attempt_idx,
                        phase="scale_full",
                        verifier_result=full_verifier,
                        meta=full_meta_for_event,
                        scale_meta=full_scale_meta,
                        rollout=full_scale_meta,
                        verifier_cache_hit=bool(full_verifier_meta.get("cache_hit", False)),
                    )

        summary["total"] += 1
        if final_verifier_result is None:
            continue
        if _verifier_is_pass(final_verifier_result):
            summary["passed"] += 1
        elif _verifier_outcome(final_verifier_result) == "UNKNOWN":
            summary["unknown"] += 1
        else:
            summary["failed"] += 1

    return summary
