"""Rulebook linting and hygiene checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from ..contracts import normalize_eventlog_dict

_ALLOWED_INJECTION_MODES = {"system_guard", "prepend", "inline"}


def _normalize_payload_text(rule: Mapping[str, Any]) -> str:
    body = rule.get("body")
    if isinstance(body, str):
        return " ".join(body.split())

    injection = rule.get("injection")
    if isinstance(injection, Mapping):
        for key in ("body", "text", "payload", "prompt"):
            value = injection.get(key)
            if isinstance(value, str):
                normalized = " ".join(value.split())
                if normalized:
                    return normalized
    return ""


def _extract_selector_scope(rule: Mapping[str, Any]) -> dict[str, Any]:
    scope: dict[str, Any] = {}

    applicability = rule.get("applicability")
    if isinstance(applicability, Mapping):
        for key in (
            "bucket_ids",
            "bucket_id",
            "mode",
            "keyword_any",
            "domain_tag",
            "task_family",
            "failure_cluster_ids",
        ):
            value = applicability.get(key)
            if isinstance(value, str) and value:
                scope[key] = value
            elif isinstance(value, list):
                normalized = sorted(item for item in value if isinstance(item, str) and item)
                if normalized:
                    scope[key] = normalized

    for key in ("bucket_id", "mode", "domain_tag", "task_family"):
        value = rule.get(key)
        if isinstance(value, str) and value:
            scope[key] = value
    for key in ("bucket_ids", "keywords", "keyword_any"):
        value = rule.get(key)
        if isinstance(value, list):
            normalized = sorted(item for item in value if isinstance(item, str) and item)
            if normalized:
                scope[key] = normalized

    return scope


def _selector_present(rule: Mapping[str, Any]) -> bool:
    return bool(_extract_selector_scope(rule))


def _priority_value(rule: Mapping[str, Any]) -> int | None:
    priority = rule.get("priority")
    if priority is None:
        return None
    if isinstance(priority, bool):
        return int(priority)
    if isinstance(priority, int):
        return priority
    if isinstance(priority, Mapping):
        rank = priority.get("rank")
        if isinstance(rank, bool):
            return int(rank)
        if isinstance(rank, int):
            return rank
    return None


def _payload_conflict(lhs: str, rhs: str) -> str | None:
    left = lhs.lower()
    right = rhs.lower()
    left_json_only = bool(re.search(r"\b(output|return)\s+json\s+only\b", left)) or "no prose" in left
    right_json_only = bool(re.search(r"\b(output|return)\s+json\s+only\b", right)) or "no prose" in right
    left_text_only = bool(re.search(r"\b(output|return)\s+(plain\s+)?text\s+only\b", left))
    right_text_only = bool(re.search(r"\b(output|return)\s+(plain\s+)?text\s+only\b", right))

    if (left_json_only and right_text_only) or (left_text_only and right_json_only):
        return "json_only_vs_text_only"
    return None


def _iter_rule_records(rulebook: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rules = rulebook.get("rules")
    if not isinstance(raw_rules, list):
        return []
    records: list[dict[str, Any]] = []
    for item in raw_rules:
        if isinstance(item, Mapping):
            records.append(dict(item))
    return records


def _eventlog_selected_counts(eventlog_path: str | Path) -> dict[str, int]:
    source = Path(eventlog_path)
    if not source.exists():
        return {}
    counts: dict[str, int] = {}
    with source.open("r", encoding="utf-8") as fp:
        for line in fp:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                continue
            event = normalize_eventlog_dict(payload)
            selected = event.get("selected_rules")
            if not isinstance(selected, list):
                continue
            for item in selected:
                if not isinstance(item, Mapping):
                    continue
                rule_id = item.get("rule_id")
                if isinstance(rule_id, str) and rule_id:
                    counts[rule_id] = counts.get(rule_id, 0) + 1
    return counts


def lint_rulebook(rulebook: dict, eventlog_path: str | None = None) -> dict:
    """Lint a rulebook dict and return JSON-serializable findings."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    records = _iter_rule_records(rulebook) if isinstance(rulebook, Mapping) else []
    if not records:
        errors.append(
            {
                "code": "RULEBOOK_RULES_MISSING",
                "message": "Rulebook must contain a non-empty 'rules' list.",
                "path": "rules",
            }
        )

    seen_ids: dict[str, int] = {}
    payload_index: dict[str, list[str]] = {}
    scoped_payload_index: dict[tuple[str, str], list[str]] = {}
    scoped_rules: list[tuple[str, str, str, int | None]] = []

    for idx, rule in enumerate(records):
        rule_path = f"rules[{idx}]"
        rule_id = rule.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id:
            errors.append(
                {
                    "code": "RULE_ID_MISSING",
                    "message": "Rule must include non-empty string 'rule_id'.",
                    "path": f"{rule_path}.rule_id",
                }
            )
            continue

        if rule_id in seen_ids:
            errors.append(
                {
                    "code": "RULE_ID_DUPLICATE",
                    "message": f"Duplicate rule_id detected: {rule_id}",
                    "rule_id": rule_id,
                    "path": f"{rule_path}.rule_id",
                }
            )
        seen_ids[rule_id] = seen_ids.get(rule_id, 0) + 1

        version = rule.get("version")
        if not isinstance(version, str) or not version:
            errors.append(
                {
                    "code": "RULE_VERSION_MISSING",
                    "message": "Rule must include non-empty string 'version'.",
                    "rule_id": rule_id,
                    "path": f"{rule_path}.version",
                }
            )

        rule_type = rule.get("type")
        if not isinstance(rule_type, str) or not rule_type:
            errors.append(
                {
                    "code": "RULE_TYPE_MISSING",
                    "message": "Rule must include non-empty string 'type'.",
                    "rule_id": rule_id,
                    "path": f"{rule_path}.type",
                }
            )

        payload = _normalize_payload_text(rule)
        if not payload:
            errors.append(
                {
                    "code": "INJECTION_PAYLOAD_EMPTY",
                    "message": "Rule injection payload must be non-empty.",
                    "rule_id": rule_id,
                    "path": f"{rule_path}.body",
                }
            )

        if not _selector_present(rule):
            errors.append(
                {
                    "code": "SELECTOR_MISSING",
                    "message": "Rule selector criteria are missing.",
                    "rule_id": rule_id,
                    "path": f"{rule_path}.applicability",
                }
            )

        priority = rule.get("priority")
        if priority is not None and _priority_value(rule) is None:
            errors.append(
                {
                    "code": "PRIORITY_INVALID",
                    "message": "Rule priority must be an integer or include integer priority.rank.",
                    "rule_id": rule_id,
                    "path": f"{rule_path}.priority",
                }
            )

        injection_mode = rule.get("injection_mode")
        if injection_mode is not None and injection_mode not in _ALLOWED_INJECTION_MODES:
            errors.append(
                {
                    "code": "INJECTION_MODE_INVALID",
                    "message": f"Unsupported injection_mode: {injection_mode!r}",
                    "rule_id": rule_id,
                    "path": f"{rule_path}.injection_mode",
                }
            )

        if payload:
            payload_index.setdefault(payload, []).append(rule_id)
            selector_scope = _extract_selector_scope(rule)
            scope_key = json.dumps(selector_scope, sort_keys=True)
            scoped_payload_index.setdefault((scope_key, payload), []).append(rule_id)
            scoped_rules.append(
                (
                    rule_id,
                    scope_key,
                    str(injection_mode or ("system_guard" if rule.get("type") == "GuardrailRule" else "prepend")),
                    _priority_value(rule),
                )
            )

    for payload, rule_ids in payload_index.items():
        if len(rule_ids) > 1:
            for i in range(len(rule_ids)):
                for j in range(i + 1, len(rule_ids)):
                    duplicates.append(
                        {
                            "rule_id_a": rule_ids[i],
                            "rule_id_b": rule_ids[j],
                            "reason": "identical_payload",
                        }
                    )
                    warnings.append(
                        {
                            "code": "DUPLICATE_PAYLOAD",
                            "message": f"Rules {rule_ids[i]} and {rule_ids[j]} have identical payloads.",
                            "rule_id": rule_ids[i],
                        }
                    )

    for (scope_key, _payload), rule_ids in scoped_payload_index.items():
        if len(rule_ids) > 1:
            for i in range(len(rule_ids)):
                for j in range(i + 1, len(rule_ids)):
                    duplicates.append(
                        {
                            "rule_id_a": rule_ids[i],
                            "rule_id_b": rule_ids[j],
                            "reason": "identical_scope_and_payload",
                        }
                    )
                    warnings.append(
                        {
                            "code": "DUPLICATE_SCOPE_PAYLOAD",
                            "message": f"Rules {rule_ids[i]} and {rule_ids[j]} overlap on scope and payload.",
                            "rule_id": rule_ids[i],
                            "path": scope_key,
                        }
                    )

    records_by_id = {str(rule.get("rule_id")): rule for rule in records if isinstance(rule.get("rule_id"), str)}
    for i in range(len(scoped_rules)):
        for j in range(i + 1, len(scoped_rules)):
            rule_id_a, scope_a, mode_a, priority_a = scoped_rules[i]
            rule_id_b, scope_b, mode_b, priority_b = scoped_rules[j]
            if scope_a != scope_b or mode_a != mode_b or priority_a != priority_b:
                continue
            rule_a = records_by_id.get(rule_id_a)
            rule_b = records_by_id.get(rule_id_b)
            if not isinstance(rule_a, Mapping) or not isinstance(rule_b, Mapping):
                continue
            payload_a = _normalize_payload_text(rule_a)
            payload_b = _normalize_payload_text(rule_b)
            conflict_reason = _payload_conflict(payload_a, payload_b)
            if conflict_reason is None:
                continue
            conflicts.append(
                {
                    "rule_id_a": rule_id_a,
                    "rule_id_b": rule_id_b,
                    "scope": scope_a,
                    "reason": conflict_reason,
                }
            )
            warnings.append(
                {
                    "code": "POTENTIAL_CONFLICT",
                    "message": f"Rules {rule_id_a} and {rule_id_b} may conflict in the same selector scope.",
                    "rule_id": rule_id_a,
                }
            )

    selected_counts: dict[str, int] = {}
    if eventlog_path:
        selected_counts = _eventlog_selected_counts(eventlog_path)
        for rule in records:
            rule_id = rule.get("rule_id")
            if not isinstance(rule_id, str) or not rule_id:
                continue
            if selected_counts.get(rule_id, 0) > 0:
                continue
            warnings.append(
                {
                    "code": "RULE_UNUSED_IN_EVENTLOG",
                    "message": f"Rule {rule_id} was not selected in the provided eventlog.",
                    "rule_id": rule_id,
                }
            )

    enabled_count = sum(
        1
        for rule in records
        if not (isinstance(rule.get("status"), str) and str(rule.get("status")).lower() == "retired")
    )
    result = {
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "rules_total": len(records),
            "rules_enabled": enabled_count if records else None,
            "unique_ids": all(count == 1 for count in seen_ids.values()) if seen_ids else False,
            "eventlog_selected_rules_total": int(sum(selected_counts.values())),
        },
        "duplicates": duplicates,
        "conflicts": conflicts,
    }
    return result


__all__ = ["lint_rulebook"]
