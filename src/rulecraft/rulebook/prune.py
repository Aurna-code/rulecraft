"""Rulebook pruning utilities driven by EventLog rule usage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..contracts import normalize_eventlog_dict, pass_from

_KEEP_TOP_SELECTED = 5


def _extract_task_id(event: Mapping[str, Any]) -> str | None:
    run = event.get("run")
    if not isinstance(run, Mapping):
        return None
    extra = run.get("extra")
    if isinstance(extra, Mapping):
        task_id = extra.get("task_id")
        if isinstance(task_id, str) and task_id:
            return task_id
    task_id = run.get("task_id")
    if isinstance(task_id, str) and task_id:
        return task_id
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _iter_events(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    events: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as fp:
        for line in fp:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                events.append(normalize_eventlog_dict(payload))
    return events


def _strong_pass_event(event: Mapping[str, Any]) -> bool:
    verifier = event.get("verifier")
    if not isinstance(verifier, Mapping):
        return False
    return verifier.get("verdict") == "PASS" and verifier.get("outcome") == "OK"


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _is_safety_rule(rule: Mapping[str, Any]) -> bool:
    for field in ("type", "category"):
        value = rule.get(field)
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if "formatrule" in lowered or "schemarule" in lowered:
            return True
    return False


def compute_rule_stats(rulebook: dict, eventlog_path: str) -> dict:
    """Compute per-rule usage and outcome stats from eventlog data."""
    raw_rules = rulebook.get("rules") if isinstance(rulebook, Mapping) else None
    if not isinstance(raw_rules, list):
        raise ValueError("Rulebook must contain a 'rules' list.")

    rules_by_id: dict[str, Mapping[str, Any]] = {}
    for item in raw_rules:
        if not isinstance(item, Mapping):
            continue
        rule_id = item.get("rule_id")
        if isinstance(rule_id, str) and rule_id:
            rules_by_id[rule_id] = item

    events = _iter_events(eventlog_path)
    task_ids: set[str] = set()
    task_strong_pass: dict[str, bool] = {}
    rule_selected_counts: dict[str, int] = {rule_id: 0 for rule_id in rules_by_id}
    rule_selected_tasks: dict[str, set[str]] = {rule_id: set() for rule_id in rules_by_id}
    rule_costs: dict[str, list[float]] = {rule_id: [] for rule_id in rules_by_id}

    for event in events:
        task_id = _extract_task_id(event)
        if task_id is not None:
            task_ids.add(task_id)
            task_strong_pass[task_id] = task_strong_pass.get(task_id, False) or _strong_pass_event(event)

        selected_rules = event.get("selected_rules")
        if not isinstance(selected_rules, list):
            continue

        cost = event.get("cost")
        cost_usd: float | None = None
        if isinstance(cost, Mapping):
            meta = cost.get("meta")
            if isinstance(meta, Mapping):
                cost_usd = _as_float(meta.get("cost_usd"))

        for selected in selected_rules:
            if not isinstance(selected, Mapping):
                continue
            rule_id = selected.get("rule_id")
            if not isinstance(rule_id, str) or not rule_id or rule_id not in rules_by_id:
                continue
            rule_selected_counts[rule_id] = rule_selected_counts.get(rule_id, 0) + 1
            if task_id is not None:
                rule_selected_tasks.setdefault(rule_id, set()).add(task_id)
            if cost_usd is not None:
                rule_costs.setdefault(rule_id, []).append(cost_usd)

    strong_pass_total = sum(1 for task_id in task_ids if task_strong_pass.get(task_id, False))
    overall_strong_pass_rate = _safe_rate(strong_pass_total, len(task_ids))

    per_rule: dict[str, dict[str, Any]] = {}
    for rule_id, rule in sorted(rules_by_id.items()):
        covered = rule_selected_tasks.get(rule_id, set())
        covered_total = len(covered)
        strong_when_selected_count = sum(1 for task_id in covered if task_strong_pass.get(task_id, False))
        strong_when_selected = _safe_rate(strong_when_selected_count, covered_total)
        fail_or_unknown_rate = _safe_rate(covered_total - strong_when_selected_count, covered_total)

        costs = rule_costs.get(rule_id, [])
        avg_cost = (sum(costs) / len(costs)) if costs else None
        impact = strong_when_selected - overall_strong_pass_rate
        per_rule[rule_id] = {
            "selected_count": int(rule_selected_counts.get(rule_id, 0)),
            "tasks_covered": covered_total,
            "strong_pass_when_selected": strong_when_selected,
            "fail_or_unknown_when_selected": fail_or_unknown_rate,
            "avg_cost_usd_when_selected": avg_cost,
            "impact": impact,
            "is_safety_rule": _is_safety_rule(rule),
        }

    return {
        "overall": {
            "tasks_total": len(task_ids),
            "strong_pass_rate": overall_strong_pass_rate,
        },
        "rules": per_rule,
    }


def prune_rulebook(
    rulebook: dict,
    stats: dict,
    min_selected: int,
    min_impact: float | None,
    max_remove: int | None,
) -> tuple[dict, dict]:
    """Return a pruned rulebook and plan report based on usage stats."""
    if int(min_selected) < 0:
        raise ValueError("min_selected must be >= 0")

    raw_rules = rulebook.get("rules") if isinstance(rulebook, Mapping) else None
    if not isinstance(raw_rules, list):
        raise ValueError("Rulebook must contain a 'rules' list.")

    stats_rules = stats.get("rules") if isinstance(stats, Mapping) else None
    if not isinstance(stats_rules, Mapping):
        stats_rules = {}

    top_selected_ids = {
        rule_id
        for rule_id, _ in sorted(
            (
                (
                    str(rule_id),
                    int((rule_stats.get("selected_count") if isinstance(rule_stats, Mapping) else 0) or 0),
                )
                for rule_id, rule_stats in stats_rules.items()
            ),
            key=lambda item: (-item[1], item[0]),
        )[:_KEEP_TOP_SELECTED]
        if _ > 0
    }

    candidates: list[dict[str, Any]] = []
    keep_ids: list[str] = []

    for item in raw_rules:
        if not isinstance(item, Mapping):
            continue
        rule = dict(item)
        rule_id = rule.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id:
            keep_ids.append(str(rule_id))
            continue

        rule_stats = stats_rules.get(rule_id)
        if isinstance(rule_stats, Mapping):
            selected_count = int(rule_stats.get("selected_count", 0) or 0)
            impact = float(rule_stats.get("impact", 0.0) or 0.0)
            safety_rule = bool(rule_stats.get("is_safety_rule", False))
        else:
            selected_count = 0
            impact = 0.0
            safety_rule = _is_safety_rule(rule)

        if rule_id in top_selected_ids:
            keep_ids.append(rule_id)
            continue

        if safety_rule and selected_count > 0:
            keep_ids.append(rule_id)
            continue

        low_selected = selected_count < int(min_selected)
        if not low_selected:
            keep_ids.append(rule_id)
            continue

        if min_impact is not None and impact >= float(min_impact):
            keep_ids.append(rule_id)
            continue

        candidates.append(
            {
                "rule_id": rule_id,
                "selected_count": selected_count,
                "impact": impact,
                "safety_rule": safety_rule,
                "reason": "selected_count_below_min" if min_impact is None else "low_selection_and_impact",
            }
        )

    remove_candidates = sorted(candidates, key=lambda item: (item["selected_count"], item["impact"], item["rule_id"]))
    if max_remove is not None and int(max_remove) >= 0:
        remove_candidates = remove_candidates[: int(max_remove)]
    remove_ids = {item["rule_id"] for item in remove_candidates}

    kept_rules: list[dict[str, Any]] = []
    for item in raw_rules:
        if not isinstance(item, Mapping):
            continue
        rule_id = item.get("rule_id")
        if isinstance(rule_id, str) and rule_id in remove_ids:
            continue
        kept_rules.append(dict(item))

    kept_ids = [str(item.get("rule_id", "")) for item in kept_rules if isinstance(item, Mapping)]
    pruned_rulebook = dict(rulebook)
    pruned_rulebook["rules"] = kept_rules

    plan = {
        "removed_rule_ids": sorted(remove_ids),
        "kept_rule_ids": kept_ids,
        "removed": remove_candidates,
        "summary": {
            "rules_total": len(raw_rules),
            "rules_removed": len(remove_ids),
            "rules_kept": len(kept_rules),
            "min_selected": int(min_selected),
            "min_impact": min_impact,
            "max_remove": max_remove,
        },
    }
    return pruned_rulebook, plan


__all__ = ["compute_rule_stats", "prune_rulebook"]
