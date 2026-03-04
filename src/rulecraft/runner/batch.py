"""Batch task runner for offline experiments."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Iterator, Literal

from ..contracts import EventLog, pass_from
from ..logging import append_event
from ..policy.repair_loop import build_repair_prompt
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
) -> dict[str, int]:
    summary = {"total": 0, "passed": 0, "failed": 0, "unknown": 0}
    attempts_limit = max(int(max_attempts), 1)

    for task in _iter_tasks(tasks_path, limit):
        prompt = str(task["prompt"])
        mode = str(task["mode"])
        trace_id = str(uuid.uuid4())
        task_id = str(task["task_id"])
        attempt_prompt = prompt
        attempt_instructions = instructions
        final_verifier_result = None

        for attempt_idx in range(attempts_limit):
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
                selected_rules=[],
                run={
                    "mode": "batch",
                    "task_id": task_id,
                    "extra": {
                        "task_id": task_id,
                        "attempt_idx": attempt_idx,
                        "phase": phase,
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

            if verifier_result.verdict == "PASS" and verifier_result.outcome != "FAIL":
                break
            if not repair or attempt_idx + 1 >= attempts_limit:
                break

            verifier_payload = {
                "verdict": verifier_result.verdict,
                "outcome": verifier_result.outcome,
                "reason_codes": verifier_result.reason_codes,
                "violated_constraints": verifier_result.violated_constraints,
            }
            attempt_prompt, attempt_instructions = build_repair_prompt(
                task_prompt=prompt,
                mode=mode,
                last_output=text,
                verifier=verifier_payload,
            )

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
