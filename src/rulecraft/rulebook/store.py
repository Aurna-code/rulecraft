"""Rulebook store for v0.1 JSON sources."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

RuleStatus = Literal["active", "temporary", "retired"]
RuleRecord = dict[str, Any]
_VALID_STATUSES: set[str] = {"active", "temporary", "retired"}


@dataclass(slots=True)
class RulebookStore:
    _records: list[RuleRecord]

    @classmethod
    def load_from_json(cls, path: str | Path) -> "RulebookStore":
        input_path = Path(path)
        with input_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)

        if isinstance(payload, list):
            raw_records = payload
        elif isinstance(payload, dict) and isinstance(payload.get("rules"), list):
            raw_records = payload["rules"]
        else:
            raise ValueError("Rulebook JSON must be a list or an object with a 'rules' list.")

        records: list[RuleRecord] = []
        for idx, item in enumerate(raw_records):
            if not isinstance(item, dict):
                raise ValueError(f"Rule record at index {idx} must be an object.")
            records.append(dict(item))

        return cls(_records=records)

    def list(self, status: RuleStatus | None = None) -> list[RuleRecord]:
        if status is not None and status not in _VALID_STATUSES:
            raise ValueError(f"Unsupported status: {status!r}")

        if status is None:
            records = self._records
        else:
            records = [record for record in self._records if record.get("status") == status]

        return [dict(record) for record in records]
