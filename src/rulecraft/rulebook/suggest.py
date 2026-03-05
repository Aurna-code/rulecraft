"""Conservative rulebook suggestion from observed failure clusters."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..contracts import SCHEMA_VERSION, normalize_eventlog_dict, pass_from

_MAX_REPRESENTATIVES = 5


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return cleaned or "unknown"


def _iter_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return
    with source.open("r", encoding="utf-8") as fp:
        for line in fp:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                yield payload


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


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _template_keys(
    reason_counts: Mapping[str, int],
    constraint_counts: Mapping[str, int],
    *,
    has_contract: bool,
    schema_id: str | None,
    event_count: int,
) -> list[str]:
    reason_set = set(reason_counts.keys())
    constraint_set = set(constraint_counts.keys())
    templates: list[str] = []

    has_format_failure = (
        "FORMAT_LEAK" in reason_set
        or "JSON_PARSE" in reason_set
        or any(item.startswith("FORMAT:JSON_ONLY") for item in constraint_set)
        or any(item.startswith("FORMAT:JSON_PARSE") for item in constraint_set)
    )
    if has_format_failure:
        templates.append("fmt")

    has_schema_failure = (
        "SCHEMA_VIOLATION" in reason_set or any(item.startswith("SCHEMA:JSONSCHEMA") for item in constraint_set)
    )
    if has_schema_failure:
        templates.append("schema")

    if has_schema_failure and has_contract and schema_id:
        templates.append("contract")

    if "ENV_NONDETERMINISM" in reason_set or event_count >= 3:
        templates.append("stable")

    if not templates:
        templates.append("fmt")

    return templates


def _template_payload(template: str) -> tuple[str, str, str, bool, int]:
    if template == "fmt":
        return (
            "Format compliance for machine-readable outputs",
            "Output JSON only. No prose. No code fences.",
            "GuardrailRule",
            True,
            1,
        )
    if template == "schema":
        return (
            "Schema compliance reminder",
            "Your JSON must satisfy the provided schema or contract.",
            "GuardrailRule",
            True,
            2,
        )
    if template == "contract":
        return (
            "Contract key and type restatement",
            "Ensure required keys exist and types match. Do not add extra keys unless allowed.",
            "StrategyRule",
            False,
            3,
        )
    return (
        "Deterministic output behavior",
        "Be deterministic. Do not include random or time-dependent values.",
        "StrategyRule",
        False,
        4,
    )


def _dominant_key(counter: Mapping[str, int]) -> str | None:
    best_key = None
    best_value = -1
    for key in sorted(counter):
        value = int(counter[key])
        if value > best_value:
            best_key = key
            best_value = value
    return best_key


def _sort_representatives(counter: Mapping[str, int], top_n: int) -> list[str]:
    ranked = sorted(counter.items(), key=lambda item: (-int(item[1]), item[0]))
    return [task_id for task_id, _ in ranked[:top_n]]


def suggest_rules(tasks_path: str, eventlog_path: str, max_rules: int = 20) -> dict[str, Any]:
    """Suggest conservative rulebook entries from clustered failures."""
    if int(max_rules) < 1:
        raise ValueError("max_rules must be >= 1")

    tasks: dict[str, dict[str, Any]] = {}
    for row in _iter_jsonl(tasks_path):
        task_id = row.get("task_id")
        if isinstance(task_id, str) and task_id:
            tasks[task_id] = row

    clusters: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "event_count": 0,
            "task_counts": Counter(),
            "reason_counts": Counter(),
            "constraint_counts": Counter(),
            "mode_counts": Counter(),
            "bucket_counts": Counter(),
            "contract_true_count": 0,
            "schema_id_counts": Counter(),
        }
    )

    for raw_event in _iter_jsonl(eventlog_path):
        event = normalize_eventlog_dict(raw_event)
        verifier = event.get("verifier")
        if not isinstance(verifier, Mapping):
            continue
        if pass_from(verifier) == 1 and verifier.get("outcome") == "OK":
            continue

        cluster_id = verifier.get("failure_cluster_id")
        if not isinstance(cluster_id, str) or not cluster_id:
            continue

        task_id = _extract_task_id(event)
        if task_id is None:
            continue
        task = tasks.get(task_id)
        if not isinstance(task, Mapping):
            continue

        cluster = clusters[cluster_id]
        cluster["event_count"] += 1
        cluster["task_counts"][task_id] += 1

        for reason_code in _normalize_string_list(verifier.get("reason_codes")):
            cluster["reason_counts"][reason_code] += 1
        for constraint in _normalize_string_list(verifier.get("violated_constraints")):
            cluster["constraint_counts"][constraint] += 1

        mode = task.get("mode")
        if isinstance(mode, str) and mode:
            cluster["mode_counts"][mode] += 1

        bucket_key = task.get("bucket_key")
        if isinstance(bucket_key, str) and bucket_key:
            cluster["bucket_counts"][bucket_key] += 1

        contract = task.get("contract")
        if isinstance(contract, Mapping):
            cluster["contract_true_count"] += 1
            schema_id = contract.get("schema_id")
            if isinstance(schema_id, str) and schema_id:
                cluster["schema_id_counts"][schema_id] += 1

    rules: list[dict[str, Any]] = []
    template_counter: Counter[str] = Counter()

    sorted_clusters = sorted(
        clusters.items(),
        key=lambda item: (-int(item[1]["event_count"]), item[0]),
    )

    for cluster_id, cluster in sorted_clusters:
        if len(rules) >= max_rules:
            break

        representative_task_ids = _sort_representatives(cluster["task_counts"], _MAX_REPRESENTATIVES)
        mode = _dominant_key(cluster["mode_counts"]) or "json"
        bucket_key = _dominant_key(cluster["bucket_counts"])
        schema_id = _dominant_key(cluster["schema_id_counts"])
        has_contract = bool(cluster["contract_true_count"])
        template_keys = _template_keys(
            cluster["reason_counts"],
            cluster["constraint_counts"],
            has_contract=has_contract,
            schema_id=schema_id,
            event_count=int(cluster["event_count"]),
        )

        for template_key in template_keys:
            if len(rules) >= max_rules:
                break

            title, body, rule_type, guardrail_first, rank = _template_payload(template_key)
            rule_id = f"rs_{_slug(cluster_id)}_{template_key}"
            if any(existing.get("rule_id") == rule_id for existing in rules):
                continue

            keywords: list[str] = []
            if template_key in {"fmt", "schema", "contract"}:
                keywords.append("json")
            if template_key in {"schema", "contract"}:
                keywords.append("schema")
            if template_key == "stable":
                keywords.append("deterministic")

            applicability: dict[str, Any] = {
                "bucket_ids": [bucket_key] if isinstance(bucket_key, str) and bucket_key else [],
                "mode": mode,
                "failure_cluster_ids": [cluster_id],
            }
            if keywords:
                applicability["keyword_any"] = sorted(set(keywords))

            rule = {
                "schema_version": SCHEMA_VERSION,
                "rule_id": rule_id,
                "version": "0.1.0",
                "type": rule_type,
                "status": "active",
                "title": f"{title} ({cluster_id})",
                "body": body,
                "applicability": applicability,
                "priority": {"guardrail_first": guardrail_first, "rank": rank},
                "injection_mode": "prepend",
                "evidence": {
                    "run_ids": [],
                    "validator_ids": [],
                    "regression_ids": [f"cluster:{cluster_id}"],
                    "representative_task_ids": representative_task_ids,
                    "dominant_reason_codes": [code for code, _ in cluster["reason_counts"].most_common(3)],
                    "dominant_constraints": [code for code, _ in cluster["constraint_counts"].most_common(3)],
                    "schema_id": schema_id,
                },
                "tests": {"regression_tests": [], "counterexample_tests": []},
                "metrics": {"utility_q_ema": 0.0, "pass_p_hat": None, "pass_p_lb95": None, "pass_p_K": None},
                "category": {
                    "fmt": "FormatRule",
                    "schema": "SchemaRule",
                    "contract": "ContractRule",
                    "stable": "StabilityRule",
                }[template_key],
            }
            rules.append(rule)
            template_counter[template_key] += 1

    return {
        "rulebook_name": "Rulebook",
        "rules": rules,
        "suggestion_summary": {
            "clusters_total": len(clusters),
            "rules_total": len(rules),
            "templates": dict(template_counter),
        },
    }


__all__ = ["suggest_rules"]
