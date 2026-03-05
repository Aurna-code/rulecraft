"""Deterministic micro-counterexample generation for regression packs."""

from __future__ import annotations

import random
import re
from typing import Any, Mapping


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return cleaned or "cluster"


def _normalize_sentences(prompt: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", prompt.strip())
    cleaned = [chunk.strip() for chunk in chunks if chunk.strip()]
    if cleaned:
        return cleaned
    return [prompt.strip() or "Return the correct result."]


def _perturb_whitespace(text: str, rnd: random.Random) -> str:
    collapsed = " ".join(text.split())
    if rnd.random() < 0.5:
        return collapsed + " "
    return collapsed.replace(", ", ",  ")


def _reorder_sentences(prompt: str, rnd: random.Random) -> str:
    sentences = _normalize_sentences(prompt)
    if len(sentences) <= 1:
        return prompt.strip()
    idx = rnd.randrange(len(sentences))
    rotated = sentences[idx:] + sentences[:idx]
    return " ".join(rotated)


def _add_distractor(prompt: str) -> str:
    base = prompt.strip()
    suffix = "Note: keep output concise."
    if not base:
        return suffix
    return f"{base} {suffix}"


def _toggle_json_reminder(prompt: str) -> str:
    base = prompt.strip()
    reminder = "Return JSON only."
    lowered = base.lower()
    if "json only" in lowered:
        # Remove one short JSON-only phrase and normalize spaces.
        trimmed = re.sub(r"\breturn json only\.?\s*", "", base, flags=re.IGNORECASE).strip()
        return trimmed or "Return the answer in JSON."
    if not base:
        return reminder
    return f"{base} {reminder}"


def _restate_schema_contract(prompt: str) -> str:
    base = prompt.strip()
    addendum = "Follow the provided schema exactly and keep field types correct."
    if not base:
        return addendum
    return f"{base} {addendum}"


def generate_counterexamples(task: dict, cluster_id: str, seed: int, n: int = 3) -> list[dict]:
    """Generate deterministic, safe prompt perturbations for a task."""
    if int(n) < 1:
        return []

    task_id = str(task.get("task_id", "task"))
    mode = str(task.get("mode", "text"))
    prompt = str(task.get("prompt", "") or "")
    contract = task.get("contract")
    has_contract = isinstance(contract, Mapping)
    cluster_slug = _slug(cluster_id)

    generated: list[dict] = []
    for idx in range(int(n)):
        rnd = random.Random(f"{seed}:{task_id}:{cluster_id}:{idx}")

        variant_kind = idx % 3
        if variant_kind == 0:
            mutated_prompt = _perturb_whitespace(prompt, rnd)
            mutated_prompt = _add_distractor(mutated_prompt)
        elif variant_kind == 1:
            mutated_prompt = _reorder_sentences(prompt, rnd)
            mutated_prompt = _add_distractor(mutated_prompt)
        else:
            mutated_prompt = _toggle_json_reminder(prompt) if mode == "json" else _add_distractor(prompt)

        if has_contract:
            mutated_prompt = _restate_schema_contract(mutated_prompt)

        mutated = dict(task)
        mutated["task_id"] = f"{task_id}__ce_{cluster_slug}_{idx}"
        mutated["prompt"] = mutated_prompt
        generated.append(mutated)

    return generated


__all__ = ["generate_counterexamples"]
