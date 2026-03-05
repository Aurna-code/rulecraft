from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.cli import main
from rulecraft.runner.cleanup import cleanup_runs


def _make_run(root: Path, name: str, created_utc: str, blob_bytes: int = 128) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "created_utc": created_utc,
        "schema_version": "0.5.15",
        "git": {"commit": name, "dirty": False},
        "inputs": {"tasks_path": str(run_dir / "tasks.jsonl"), "baseline_policy_profile_path": None, "baseline_rulebook_path": None},
        "params": {"adapter": "stub", "run_batch": {}, "regpack": {}, "promote": {}, "promote_rules": {}},
        "outputs": {"summary": "summary.json"},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True}, ensure_ascii=False) + "\n", encoding="utf-8")
    (run_dir / "blob.bin").write_bytes(b"x" * blob_bytes)
    return run_dir


def test_cleanup_runs_dry_run_lists_candidates(tmp_path: Path) -> None:
    root = tmp_path / "evolve"
    _make_run(root, "run1", "2026-03-01T00:00:00Z")
    _make_run(root, "run2", "2026-03-02T00:00:00Z")
    _make_run(root, "run3", "2026-03-03T00:00:00Z")

    summary = cleanup_runs(str(root), keep_last=2, dry_run=True)
    assert summary["dry_run"] is True
    assert summary["total_runs"] == 3
    assert len(summary["candidates"]) == 1
    assert summary["candidates"][0]["path"].endswith("run1")
    assert (root / "run1").exists()


def test_cleanup_runs_apply_deletes_expected_dirs(tmp_path: Path) -> None:
    root = tmp_path / "evolve_apply"
    _make_run(root, "run1", "2026-03-01T00:00:00Z", blob_bytes=256)
    _make_run(root, "run2", "2026-03-02T00:00:00Z", blob_bytes=256)
    _make_run(root, "run3", "2026-03-03T00:00:00Z", blob_bytes=256)

    summary = cleanup_runs(str(root), keep_last=1, dry_run=False)
    assert summary["dry_run"] is False
    assert len(summary["deleted"]) == 2
    assert summary["bytes_freed"] > 0
    assert not (root / "run1").exists()
    assert not (root / "run2").exists()
    assert (root / "run3").exists()


def test_cleanup_cli_supports_dry_run_and_apply(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "evolve_cli"
    _make_run(root, "run1", "2026-03-01T00:00:00Z")
    _make_run(root, "run2", "2026-03-02T00:00:00Z")

    exit_code = main(["cleanup", "--root", str(root), "--keep-last", "1", "--dry-run"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert len(payload["candidates"]) == 1

    exit_code = main(["cleanup", "--root", str(root), "--keep-last", "1", "--apply"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is False
    assert len(payload["deleted"]) == 1
