"""End-to-end minimal Orchestrator run for v0.1."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.adapters.dummy import DummyAdapter  # noqa: E402
from rulecraft.orchestrator import Orchestrator  # noqa: E402
from rulecraft.rulebook.store import RulebookStore  # noqa: E402


def _preview(text: str, limit: int = 120) -> str:
    return text.replace("\n", " ")[:limit]


def main() -> None:
    store = RulebookStore.load_from_json(ROOT / "rules" / "sample_rulebook.json")
    orchestrator = Orchestrator()

    runlog_path = ROOT / "logs" / "runlog.jsonl"
    if runlog_path.exists():
        runlog_path.unlink()

    context = {
        "bucket_id": "support",
        "domain_tag": "payments",
        "task_family": "answer",
        "impact_level": "low",
        "user_clarity": "high",
    }
    constraints = {"json_only": True, "length_lte": 4000}

    runs = [
        ("json_ok", "Return a short JSON object with replacement_status and next_steps."),
        ("echo", "I lost my card. Please help me replace it quickly."),
    ]

    for mode, input_text in runs:
        adapter = DummyAdapter(mode=mode)
        output, runlog = orchestrator.run(
            input_text=input_text,
            context=context,
            constraints=constraints,
            rulebook_store=store,
            adapter=adapter,
            runlog_path=str(runlog_path),
        )
        validator = runlog["validator"]
        control_signals = runlog["control_signals"]
        print(
            f"mode={mode} verdict={validator['verdict']} outcome={validator['outcome']} "
            f"should_escalate={control_signals['should_escalate']} output={_preview(output)}"
        )


if __name__ == "__main__":
    main()
