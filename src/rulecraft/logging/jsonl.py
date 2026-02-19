"""JSONL logging for RunLog records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..contracts import RunLog, to_dict


def append_runlog(path: str, runlog: RunLog | Mapping[str, Any]) -> None:
    record = to_dict(runlog)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        fp.write("\n")
