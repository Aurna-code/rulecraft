"""Minimal OpenAI runner for canonical EventLog writes."""

from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.openai_adapter import OpenAIAdapter  # noqa: E402
from rulecraft.logging.jsonl_logger import append_event  # noqa: E402
from rulecraft.runner.minimal import run_once  # noqa: E402


def main() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Skipping OpenAI run.")
        return 2

    adapter = OpenAIAdapter()
    y, event = run_once("Say hello in one short sentence.", adapter=adapter)

    out_path = ROOT / ".rulecraft" / "eventlog.jsonl"
    append_event(str(out_path), event)
    print(f"y={y} trace_id={event.trace_id} x_ref={event.x_ref} out={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
