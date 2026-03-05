"""PaCoRe-lite rollout helper: parallel candidates, compact, top-m, optional synth."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Literal, Mapping

from ..verifier.verify_output import verify_output
from .rollout_rank import rank_candidates

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
    return None


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _verifier_is_pass(verifier: Mapping[str, Any]) -> bool:
    pass_value = verifier.get("pass")
    if isinstance(pass_value, int):
        return pass_value == 1
    verdict = verifier.get("verdict")
    outcome = verifier.get("outcome")
    return verdict == "PASS" and outcome != "FAIL"


def _compact_text(text: str, max_chars: int = 800) -> str:
    compact = text.strip()
    if len(compact) <= max_chars:
        return compact
    if max_chars <= 3:
        return compact[:max_chars]
    return compact[: max_chars - 3].rstrip() + "..."


def _compact_candidate(mode: TaskMode, text: str, max_chars: int = 800) -> str:
    if mode == "json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return _compact_text(text, max_chars=max_chars)
        compact_json = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return _compact_text(compact_json, max_chars=max_chars)
    return _compact_text(text, max_chars=max_chars)


def _build_synth_prompt(mode: TaskMode, summaries: list[str], selected_rules: list[object]) -> str:
    rule_context = _build_rule_context_block(selected_rules)
    lines = [
        "Synthesize the best final answer that satisfies constraints. Output JSON only if mode=json.",
        f"mode={mode}",
        "",
    ]
    if rule_context is not None:
        lines.extend(
            [
                "Rulecraft Context",
                rule_context,
                "",
            ]
        )
    lines.append("Candidate summaries:")
    for idx, summary in enumerate(summaries, start=1):
        lines.append(f"[Candidate {idx}]")
        lines.append(summary)
    return "\n".join(lines).strip()


def _build_rule_context_block(selected_rules: list[object]) -> str | None:
    compact_rules: list[dict[str, str]] = []
    for rule in selected_rules:
        if not isinstance(rule, Mapping):
            continue

        rule_id = str(rule.get("rule_id", "")).strip()
        if not rule_id:
            continue

        compact_rules.append(
            {
                "rule_id": rule_id,
                "type": str(rule.get("type", "UnknownRule")),
                "injection_mode": str(rule.get("injection_mode", "prepend")),
            }
        )

    if not compact_rules:
        return None
    return json.dumps(compact_rules, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _generate_with_fallback(
    adapter: Any,
    prompt: str,
    *,
    instructions: str | None,
    generate_kwargs: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    kwargs = dict(generate_kwargs or {})

    try:
        response = adapter.generate(prompt, instructions=instructions, **kwargs)
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


def _meta_to_cost_fields(meta: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "latency_ms": _coerce_optional_int(meta.get("latency_ms")),
        "tokens_in": _coerce_optional_int(meta.get("tokens_in")),
        "tokens_out": _coerce_optional_int(meta.get("tokens_out")),
        "tool_calls": _coerce_optional_int(meta.get("tool_calls")),
        "meta": {
            "backend": meta.get("backend", "unknown"),
            "model": meta.get("model", meta.get("model_name", "unknown")),
            "cost_usd": _coerce_optional_float(meta.get("cost_usd")),
            "error": meta.get("error"),
        },
    }


def _rollup_call_meta(call_metas: list[dict[str, Any]]) -> dict[str, Any]:
    backend = "rollout"
    model = "unknown"
    latency_ms = 0
    tokens_in = 0
    tokens_out = 0
    cost_usd = 0.0
    first_error: Any = None

    for meta in call_metas:
        backend_value = meta.get("backend")
        if isinstance(backend_value, str) and backend_value:
            backend = backend_value
        model_value = meta.get("model", meta.get("model_name"))
        if isinstance(model_value, str) and model_value:
            model = model_value

        latency_ms += _coerce_optional_int(meta.get("latency_ms")) or 0
        tokens_in += _coerce_optional_int(meta.get("tokens_in")) or 0
        tokens_out += _coerce_optional_int(meta.get("tokens_out")) or 0
        cost_usd += _coerce_optional_float(meta.get("cost_usd")) or 0.0

        if first_error is None and meta.get("error") is not None:
            first_error = meta.get("error")

    return {
        "backend": backend,
        "model": model,
        "latency_ms": latency_ms,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "error": first_error,
    }


def run_pacore_lite(
    prompt: str,
    mode: str,
    adapter: Any,
    k: int,
    top_m: int,
    use_synth: bool,
    instructions: str | None,
    selected_rules: list[object],
    contract: Mapping[str, Any] | None = None,
    *,
    tier: str | None = None,
    task_id: str | None = None,
    attempt_idx: int = 0,
) -> tuple[str, dict[str, Any]]:
    """Run PaCoRe-lite and return the chosen final output plus compact rollout metadata."""
    task_mode: TaskMode = "json" if mode == "json" else "text"
    effective_k = max(int(k), 1)
    effective_top_m = max(int(top_m), 1)
    resolved_tier = tier if tier in {"probe", "full"} else "probe"
    base_phase = f"scale_{resolved_tier}"

    candidates: list[dict[str, Any]] = []
    call_metas: list[dict[str, Any]] = []

    for candidate_idx in range(effective_k):
        candidate_prompt = f"{prompt}\n\n# Candidate {candidate_idx + 1}\n"
        text, meta = _generate_with_fallback(
            adapter,
            candidate_prompt,
            instructions=instructions,
            generate_kwargs={
                "task_id": task_id,
                "attempt_idx": attempt_idx,
                "phase": f"{base_phase}_candidate",
                "candidate_idx": candidate_idx,
            },
        )
        call_metas.append(meta)

        verifier = verify_output(mode=task_mode, y_text=text, contract=contract)
        candidates.append(
            {
                "y": text,
                "verifier": verifier,
                "cost": _meta_to_cost_fields(meta),
            }
        )

    ranked = rank_candidates(candidates)
    if ranked:
        best_candidate = ranked[0]
    else:
        best_candidate = {
            "y": "",
            "verifier": {
                "verdict": "FAIL",
                "outcome": "UNKNOWN",
                "reason_codes": None,
                "violated_constraints": None,
                "pass": 0,
            },
            "cost": None,
        }

    selected = ranked[: min(effective_top_m, len(ranked))]
    final_y = str(best_candidate.get("y", ""))
    used_synth = False
    synth_verdict: str | None = None
    synth_outcome: str | None = None

    if use_synth and selected:
        used_synth = True
        summaries = [_compact_candidate(task_mode, str(candidate.get("y", ""))) for candidate in selected]
        synth_prompt = _build_synth_prompt(task_mode, summaries, selected_rules)
        synth_text, synth_meta = _generate_with_fallback(
            adapter,
            synth_prompt,
            instructions=instructions,
            generate_kwargs={
                "task_id": task_id,
                "attempt_idx": attempt_idx,
                "phase": f"{base_phase}_synth",
            },
        )
        call_metas.append(synth_meta)

        synth_verifier = verify_output(mode=task_mode, y_text=synth_text, contract=contract)
        synth_verdict = str(synth_verifier.get("verdict"))
        synth_outcome = str(synth_verifier.get("outcome"))

        if _verifier_is_pass(synth_verifier):
            final_y = synth_text

    best_verifier = best_candidate.get("verifier")
    if isinstance(best_verifier, Mapping):
        best_verdict = best_verifier.get("verdict")
        best_outcome = best_verifier.get("outcome")
    else:
        best_verdict = None
        best_outcome = None

    verdict_counts: Counter[str] = Counter()
    for candidate in ranked:
        verifier = candidate.get("verifier")
        if isinstance(verifier, Mapping):
            verdict = verifier.get("verdict")
            outcome = verifier.get("outcome")
            verdict_counts[f"{verdict}/{outcome}"] += 1

    meta = {
        "tier": resolved_tier,
        "k": effective_k,
        "top_m": min(effective_top_m, len(ranked)),
        "used_synth": used_synth,
        "best_candidate_verdict": best_verdict,
        "best_candidate_outcome": best_outcome,
        "synth_verdict": synth_verdict,
        "synth_outcome": synth_outcome,
        "candidate_verdict_counts": dict(sorted(verdict_counts.items())),
        "event_meta": _rollup_call_meta(call_metas),
    }
    return final_y, meta


__all__ = ["run_pacore_lite"]
