from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.cli import main


def test_cli_runs_and_appends_runlog(tmp_path: Path, capsys: object) -> None:
    runlog_path = tmp_path / "runlog.jsonl"
    exit_code = main(
        [
            "--rulebook",
            str(ROOT / "rules" / "sample_rulebook.json"),
            "--bucket-id",
            "support",
            "--json-only",
            "--length-lte",
            "4000",
            "--adapter",
            "dummy:json_ok",
            "--out",
            str(runlog_path),
            "--text",
            "Return a short JSON object.",
        ]
    )

    assert exit_code == 0

    printed = capsys.readouterr().out
    assert "run_id=" in printed
    assert "verdict=PASS" in printed
    assert "outcome=OK" in printed

    lines = runlog_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["run_id"]
    assert payload["control_signals"]["exit_stage"] == "l1"
    assert payload["control_signals"]["repair_attempted"] is False
