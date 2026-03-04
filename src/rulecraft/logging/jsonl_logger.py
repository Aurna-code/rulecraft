"""Minimal EventLog JSONL writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..contracts import EventLog, normalize_eventlog_dict, to_dict


def append_event(path: str, eventlog: EventLog | Mapping[str, Any]) -> None:
    record = normalize_eventlog_dict(to_dict(eventlog))
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        fp.write("\n")
