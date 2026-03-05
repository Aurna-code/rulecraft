"""Minimal contract-aware batch runner example for offline experiments."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.scripted import ScriptedAdapter  # noqa: E402
from rulecraft.metrics.eventlog_metrics import summarize_jsonl  # noqa: E402
from rulecraft.runner.batch import run_batch  # noqa: E402


def main() -> None:
    tasks_path = ROOT / "examples" / "tasks" / "contract_tasks.jsonl"
    out_path = ROOT / ".rulecraft" / "contract_batch_eventlog.jsonl"

    if out_path.exists():
        out_path.unlink()

    adapter = ScriptedAdapter(
        scripts={
            "contract-json-1": ['{"status":"ok","count":"1"}', '{"status":"ok","count":1}'],
            "contract-json-2": ['{"status":"ok","tags":["a","b"]}'],
            "json-no-contract": ['{"status":"ok"}'],
            "text-summary": ["This is a one-sentence summary."],
        }
    )

    summary = run_batch(
        tasks_path=tasks_path,
        adapter=adapter,
        out_path=out_path,
        repair=True,
        max_attempts=2,
    )
    print("Contract batch summary")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))

    metrics = summarize_jsonl(out_path, task_metrics=True)
    print("Contract metrics summary")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
