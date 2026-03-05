"""Verifier cache backends and cache key helpers."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol


class VerifierCache(Protocol):
    def get(self, key: str) -> dict[str, Any] | None:
        ...

    def set(self, key: str, value: dict[str, Any]) -> None:
        ...


class InMemoryVerifierCache:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        value = self._store.get(key)
        if value is None:
            return None
        return dict(value)

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._store[str(key)] = dict(value)


class SqliteVerifierCache:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS verifier_cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()

    def get(self, key: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT value FROM verifier_cache WHERE key = ?", (str(key),)).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row[0]))
        if isinstance(payload, dict):
            return payload
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
        self._conn.execute(
            "INSERT INTO verifier_cache(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(key), payload),
        )
        self._conn.commit()


def make_cache_key(
    schema_version: str,
    verifier_id: str,
    mode: str,
    contract_id: str | None,
    y_ref: str,
) -> str:
    raw = json.dumps(
        {
            "schema_version": schema_version,
            "verifier_id": verifier_id,
            "mode": mode,
            "contract_id": contract_id,
            "y_ref": y_ref,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "VerifierCache",
    "InMemoryVerifierCache",
    "SqliteVerifierCache",
    "make_cache_key",
]
