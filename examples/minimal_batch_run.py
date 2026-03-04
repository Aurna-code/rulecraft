"""Minimal batch runner example for offline experiments."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.stub import StubAdapter  # noqa: E402
from rulecraft.metrics.eventlog_metrics import summarize_jsonl  # noqa: E402
from rulecraft.runner.batch import run_batch  # noqa: E402


def main() -> None:
    tasks_path = ROOT / "examples" / "tasks" / "sample_tasks.jsonl"
    out_path = ROOT / ".rulecraft" / "batch_eventlog.jsonl"

    if out_path.exists():
        out_path.unlink()

    summary = run_batch(
        tasks_path=tasks_path,
        adapter=StubAdapter(mode="text"),
        out_path=out_path,
        instructions=None,
    )
    print("Batch summary")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))

    metrics = summarize_jsonl(out_path, group_by="bucket_key")
    print("Metrics summary")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
