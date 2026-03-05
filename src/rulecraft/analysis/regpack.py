"""Micro-regression pack generation from tasks and EventLog history."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from ..contracts import normalize_eventlog_dict, pass_from


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


def _read_tasks(tasks_path: str | Path) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, str | None]]:
    order: list[str] = []
    task_rows: dict[str, dict[str, Any]] = {}
    task_buckets: dict[str, str | None] = {}

    source = Path(tasks_path)
    with source.open("r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no} in {source}.") from exc
            if not isinstance(payload, Mapping):
                raise ValueError(f"Task on line {line_no} in {source} must be an object.")

            task_id = payload.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise ValueError(f"Task on line {line_no} in {source} is missing required string key 'task_id'.")

            task_rows[task_id] = dict(payload)
            order.append(task_id)
            bucket_key = payload.get("bucket_key")
            task_buckets[task_id] = bucket_key if isinstance(bucket_key, str) and bucket_key else None
    return order, task_rows, task_buckets


def _iter_normalized_eventlog(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    rows: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as fp:
        for line in fp:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                rows.append(normalize_eventlog_dict(payload))
    return rows


def build_regpack(
    tasks_path: str | Path,
    eventlog_path: str | Path,
    out_path: str | Path,
    per_cluster: int = 2,
    max_total: int = 100,
) -> dict[str, Any]:
    """Build a micro-regression task pack from failure clusters and pass canaries."""
    if int(per_cluster) < 1:
        raise ValueError("per_cluster must be >= 1")
    if int(max_total) < 1:
        raise ValueError("max_total must be >= 1")

    task_order, task_rows, task_buckets = _read_tasks(tasks_path)
    events = _iter_normalized_eventlog(eventlog_path)

    cluster_events: Counter[str] = Counter()
    cluster_task_ids: dict[str, list[str]] = {}
    pass_task_ids: set[str] = set()

    for event in events:
        task_id = _extract_task_id(event)
        if task_id is None or task_id not in task_rows:
            continue

        verifier = event.get("verifier")
        if isinstance(verifier, Mapping):
            cluster_id = verifier.get("failure_cluster_id")
            if isinstance(cluster_id, str) and cluster_id:
                cluster_events[cluster_id] += 1
                cluster_task_ids.setdefault(cluster_id, [])
                if task_id not in cluster_task_ids[cluster_id]:
                    cluster_task_ids[cluster_id].append(task_id)

            if pass_from(verifier) == 1:
                pass_task_ids.add(task_id)

    selected_ids: list[str] = []
    selected_set: set[str] = set()
    cluster_selected: dict[str, list[str]] = {}

    for cluster_id, _ in sorted(cluster_events.items(), key=lambda item: (-item[1], item[0])):
        picked: list[str] = []
        for task_id in cluster_task_ids.get(cluster_id, []):
            if len(selected_ids) >= max_total:
                break
            if task_id in selected_set:
                continue
            selected_ids.append(task_id)
            selected_set.add(task_id)
            picked.append(task_id)
            if len(picked) >= per_cluster:
                break
        cluster_selected[cluster_id] = picked
        if len(selected_ids) >= max_total:
            break

    pass_bucket_added = 0
    pass_candidates_by_bucket: dict[str, list[str]] = {}
    for task_id in task_order:
        if task_id not in pass_task_ids:
            continue
        bucket = task_buckets.get(task_id) or "(null)"
        pass_candidates_by_bucket.setdefault(bucket, []).append(task_id)

    for bucket in sorted(pass_candidates_by_bucket):
        if len(selected_ids) >= max_total:
            break
        for task_id in pass_candidates_by_bucket[bucket]:
            if task_id in selected_set:
                continue
            selected_ids.append(task_id)
            selected_set.add(task_id)
            pass_bucket_added += 1
            break

    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fp:
        for task_id in selected_ids:
            fp.write(json.dumps(task_rows[task_id], ensure_ascii=False))
            fp.write("\n")

    return {
        "clusters_total": len(cluster_events),
        "clusters_sampled": sum(1 for task_ids in cluster_selected.values() if task_ids),
        "pass_bucket_samples": pass_bucket_added,
        "selected_total": len(selected_ids),
    }


__all__ = ["build_regpack"]
