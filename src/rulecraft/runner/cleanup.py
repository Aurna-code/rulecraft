"""Retention cleanup for evolve/replay run directories."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _parse_created_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dir_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def _manifest_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def _run_entries(root_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for manifest in sorted(root_dir.rglob("manifest.json")):
        run_dir = manifest.parent
        payload = _manifest_payload(manifest)
        created_utc = payload.get("created_utc")
        created_dt = _parse_created_utc(created_utc)
        mtime = run_dir.stat().st_mtime
        entries.append(
            {
                "path": str(run_dir),
                "manifest_path": str(manifest),
                "created_utc": created_utc if isinstance(created_utc, str) else None,
                "created_ts": created_dt.timestamp() if created_dt is not None else mtime,
                "mtime": mtime,
                "size_bytes": _dir_size(run_dir),
            }
        )
    entries.sort(key=lambda row: float(row["created_ts"]), reverse=True)
    return entries


def cleanup_runs(
    root_dir: str,
    keep_last: int = 10,
    keep_days: int | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Plan or apply run retention cleanup under root_dir."""
    keep_last_count = max(int(keep_last), 0)
    root = Path(root_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    entries = _run_entries(root)

    keep_paths: set[str] = set()
    for row in entries[:keep_last_count]:
        keep_paths.add(str(row["path"]))

    cutoff: datetime | None = None
    if keep_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(int(keep_days), 0))
        for row in entries:
            created_ts = float(row["created_ts"])
            created_dt = datetime.fromtimestamp(created_ts, tz=timezone.utc)
            if created_dt >= cutoff:
                keep_paths.add(str(row["path"]))

    candidates = [row for row in entries if str(row["path"]) not in keep_paths]
    deleted: list[dict[str, Any]] = []
    bytes_freed = 0

    if not dry_run:
        for row in candidates:
            run_path = Path(str(row["path"]))
            if not run_path.exists():
                continue
            freed = int(row.get("size_bytes", 0))
            shutil.rmtree(run_path)
            bytes_freed += freed
            deleted.append(
                {
                    "path": str(run_path),
                    "created_utc": row.get("created_utc"),
                    "size_bytes": freed,
                }
            )

    return {
        "root": str(root),
        "keep_last": keep_last_count,
        "keep_days": int(keep_days) if keep_days is not None else None,
        "dry_run": bool(dry_run),
        "total_runs": len(entries),
        "candidates": [
            {
                "path": row.get("path"),
                "created_utc": row.get("created_utc"),
                "size_bytes": int(row.get("size_bytes", 0)),
            }
            for row in candidates
        ],
        "deleted": deleted,
        "bytes_freed": bytes_freed,
    }


__all__ = ["cleanup_runs"]
