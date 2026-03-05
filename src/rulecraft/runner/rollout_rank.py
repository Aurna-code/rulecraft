"""Candidate ranking helpers for rollout selection."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping


def _verifier(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    verifier = candidate.get("verifier")
    if isinstance(verifier, Mapping):
        return verifier
    return {}


def _priority(verifier: Mapping[str, Any]) -> int:
    verdict = verifier.get("verdict")
    outcome = verifier.get("outcome")

    if verdict == "PASS" and outcome == "OK":
        return 0
    if verdict == "PASS" and outcome == "UNKNOWN":
        return 1
    if verdict == "PARTIAL":
        return 2
    return 3


def _list_size(value: Any) -> int:
    if isinstance(value, list):
        return len([item for item in value if item is not None])
    return 0


def _tie_breaker(seed: int | None, idx: int, candidate: Mapping[str, Any]) -> int:
    if seed is None:
        return 0

    payload = f"{seed}:{idx}:{candidate.get('y', '')}:{candidate.get('verifier', {})}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def rank_candidates(candidates: list[dict[str, Any]], seed: int | None = None) -> list[dict[str, Any]]:
    """Sort rollout candidates from best to worst using verifier-first heuristics."""
    decorated: list[tuple[tuple[int, int, int, int, int], dict[str, Any]]] = []

    for idx, candidate in enumerate(candidates):
        verifier = _verifier(candidate)
        key = (
            _priority(verifier),
            _list_size(verifier.get("violated_constraints")),
            _list_size(verifier.get("reason_codes")),
            _tie_breaker(seed, idx, candidate),
            idx,
        )
        decorated.append((key, candidate))

    decorated.sort(key=lambda item: item[0])
    return [candidate for _, candidate in decorated]


__all__ = ["rank_candidates"]
