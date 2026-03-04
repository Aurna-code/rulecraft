"""Minimal CLI for Rulecraft v0.1 single-run execution."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .adapters.dummy import DummyAdapter
from .metrics.eventlog_metrics import summarize_jsonl
from .orchestrator import Orchestrator
from .rulebook.store import RulebookStore


def _preview(text: str, limit: int = 120) -> str:
    return text.replace("\n", " ")[:limit]


def _build_adapter(adapter_spec: str) -> DummyAdapter:
    if adapter_spec == "dummy:json_ok":
        return DummyAdapter(mode="json_ok")
    if adapter_spec == "dummy:echo":
        return DummyAdapter(mode="echo")
    raise ValueError(f"Unsupported adapter: {adapter_spec!r}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Rulecraft v0.1 request from terminal.")
    parser.add_argument("--rulebook", default="rules/sample_rulebook.json", help="Path to Rulebook JSON file.")
    parser.add_argument("--bucket-id", default="support", help="Bucket id for routing and selection.")
    parser.add_argument("--json-only", action="store_true", help="Require JSON-only output.")
    parser.add_argument("--length-lte", type=int, default=4000, help="Maximum output length.")
    parser.add_argument(
        "--adapter",
        default="dummy:json_ok",
        choices=("dummy:json_ok", "dummy:echo"),
        help="BackendAdapter profile.",
    )
    parser.add_argument("--out", default="logs/runlog.jsonl", help="RunLog JSONL output path.")
    parser.add_argument("--text", required=True, help="Input text to run.")
    return parser


def _build_metrics_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate metrics from EventLog JSONL records.")
    parser.add_argument("--path", default=".rulecraft/eventlog.jsonl", help="EventLog JSONL file path.")
    parser.add_argument("--group-by", choices=("bucket_key",), default=None, help="Optional grouping dimension.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else list(sys.argv[1:])
    if raw_argv and raw_argv[0] == "metrics":
        parser = _build_metrics_parser()
        args = parser.parse_args(raw_argv[1:])
        summary = summarize_jsonl(args.path, group_by=args.group_by)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    parser = _build_parser()
    args = parser.parse_args(raw_argv)

    try:
        rulebook_store = RulebookStore.load_from_json(args.rulebook)
    except Exception as exc:  # pragma: no cover - parser error path
        parser.error(f"failed to load Rulebook from {args.rulebook!r}: {exc}")

    try:
        adapter = _build_adapter(args.adapter)
    except ValueError as exc:  # pragma: no cover - parser choices should cover this
        parser.error(str(exc))

    orchestrator = Orchestrator()
    context = {"bucket_id": args.bucket_id}
    constraints = {"json_only": bool(args.json_only), "length_lte": int(args.length_lte)}

    output, runlog = orchestrator.run(
        input_text=args.text,
        context=context,
        constraints=constraints,
        rulebook_store=rulebook_store,
        adapter=adapter,
        runlog_path=args.out,
    )

    validator = runlog.get("validator", {})
    print(
        f"run_id={runlog.get('run_id', '')} "
        f"verdict={validator.get('verdict', '')} "
        f"outcome={validator.get('outcome', '')} "
        f"output={_preview(output)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
