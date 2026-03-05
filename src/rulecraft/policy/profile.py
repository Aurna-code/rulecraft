"""Bucket-aware policy profile loading and matching."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

_ALLOWED_SCALE = {"off", "auto", "probe", "full"}
_ALLOWED_OVERRIDE_KEYS = {
    "max_attempts",
    "scale",
    "k_probe",
    "k_full",
    "top_m",
    "synth",
    "budget_usd",
    "budget_tokens",
}


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _normalize_overrides(overrides: Any) -> dict[str, Any]:
    if not isinstance(overrides, Mapping):
        raise ValueError("Profile rule overrides must be an object.")

    normalized: dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in _ALLOWED_OVERRIDE_KEYS:
            continue
        if key == "scale":
            if not isinstance(value, str) or value not in _ALLOWED_SCALE:
                raise ValueError("Profile override 'scale' must be one of off|auto|probe|full.")
            normalized[key] = value
        elif key in {"max_attempts", "k_probe", "k_full", "top_m"}:
            numeric = _as_int(value)
            if numeric is None or numeric < 1:
                raise ValueError(f"Profile override '{key}' must be an integer >= 1.")
            normalized[key] = numeric
        elif key == "synth":
            if not isinstance(value, bool):
                raise ValueError("Profile override 'synth' must be a boolean.")
            normalized[key] = value
        elif key == "budget_usd":
            if value is None:
                normalized[key] = None
            else:
                numeric = _as_float(value)
                if numeric is None or numeric < 0:
                    raise ValueError("Profile override 'budget_usd' must be a number >= 0 or null.")
                normalized[key] = numeric
        elif key == "budget_tokens":
            if value is None:
                normalized[key] = None
            else:
                numeric = _as_int(value)
                if numeric is None or numeric < 0:
                    raise ValueError("Profile override 'budget_tokens' must be an integer >= 0 or null.")
                normalized[key] = numeric
    return normalized


def load_profile(path: str | Path) -> dict[str, Any]:
    """Load and validate a policy profile JSON file."""
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Policy profile must be a JSON object.")

    version = payload.get("version")
    if version != 1:
        raise ValueError("Policy profile version must be 1.")

    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Policy profile 'rules' must be a list.")

    normalized_rules: list[dict[str, Any]] = []
    for idx, raw_rule in enumerate(rules):
        if not isinstance(raw_rule, Mapping):
            raise ValueError(f"Policy profile rule {idx} must be an object.")
        bucket_match = raw_rule.get("bucket_match")
        if not isinstance(bucket_match, str) or not bucket_match:
            raise ValueError(f"Policy profile rule {idx} must include non-empty 'bucket_match'.")
        if bucket_match.startswith("regex:"):
            pattern = bucket_match[len("regex:") :]
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Policy profile rule {idx} has invalid regex.") from exc

        normalized_rules.append(
            {
                "bucket_match": bucket_match,
                "overrides": _normalize_overrides(raw_rule.get("overrides", {})),
            }
        )

    return {
        "version": 1,
        "rules": normalized_rules,
    }


def match_bucket(profile: Mapping[str, Any] | None, bucket_key: str | None) -> dict[str, Any]:
    """Return first matching override map for the bucket key."""
    if not isinstance(profile, Mapping):
        return {}
    rules = profile.get("rules")
    if not isinstance(rules, list):
        return {}
    key = bucket_key or ""
    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        bucket_match = rule.get("bucket_match")
        overrides = rule.get("overrides")
        if not isinstance(bucket_match, str):
            continue
        if bucket_match.startswith("regex:"):
            pattern = bucket_match[len("regex:") :]
            if re.search(pattern, key):
                return dict(overrides) if isinstance(overrides, Mapping) else {}
        else:
            if key.startswith(bucket_match):
                return dict(overrides) if isinstance(overrides, Mapping) else {}
    return {}


def apply_overrides(defaults: Mapping[str, Any], overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    """Apply override values onto defaults and return merged config."""
    merged = dict(defaults)
    if isinstance(overrides, Mapping):
        for key, value in overrides.items():
            if key in _ALLOWED_OVERRIDE_KEYS:
                merged[key] = value
    return merged


__all__ = ["load_profile", "match_bucket", "apply_overrides"]
