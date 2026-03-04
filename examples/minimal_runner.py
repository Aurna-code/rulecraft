"""Smoke example for the minimal MVP runner."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.logging.jsonl_logger import append_event  # noqa: E402
from rulecraft.runner.minimal import run_once  # noqa: E402


def main() -> None:
    y, event = run_once("hello rulecraft")
    out_path = ROOT / ".rulecraft" / "eventlog.jsonl"
    append_event(str(out_path), event)
    print(f"y={y} trace_id={event.trace_id} x_ref={event.x_ref} out={out_path}")


if __name__ == "__main__":
    main()

