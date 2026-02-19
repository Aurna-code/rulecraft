from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [ROOT / "src", ROOT / "examples"]
EXCLUDED_DIRS = {ROOT / "docs"}
BANNED_TERMS = [
    "trace_id",
    "x_ref",
    "y_ref",
    "bucket_key",
    "policy_signals",
    "cu_select",
    "ContextUnit",
    "Verifier",
    "EventLog",
    "TraceCapsule",
    "CandidateSelect",
    "should_scale",
    "/docs",
]


def _iter_files(base: Path) -> list[Path]:
    if not base.exists():
        return []

    files: list[Path] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if any(path.is_relative_to(excluded) for excluded in EXCLUDED_DIRS):
            continue
        files.append(path)
    return files


def main() -> int:
    findings: list[tuple[str, str, int, str]] = []

    for scan_dir in SCAN_DIRS:
        for path in _iter_files(scan_dir):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for term in BANNED_TERMS:
                    if term in line:
                        findings.append((str(path.relative_to(ROOT)), term, lineno, line.strip()))

    if findings:
        print("Legacy term check failed. Found banned terms:")
        for relpath, term, lineno, line in findings:
            print(f"- {relpath}:{lineno}: {term}: {line}")
        return 1

    print("Legacy term check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
