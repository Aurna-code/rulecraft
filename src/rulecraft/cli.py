"""CLI entry points for Rulecraft local runs and experiments."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from .adapters.dummy import DummyAdapter
from .adapters.openai_adapter import OpenAIAdapter
from .adapters.stub import StubAdapter
from .analysis.flowmap import analyze_flowmap
from .analysis.regpack import build_regpack
from .metrics.eventlog_metrics import summarize_jsonl
from .orchestrator import Orchestrator
from .policy.profile import load_profile
from .policy.suggest import suggest_policy
from .runner.batch import run_batch
from .runner.promote import run_promotion
from .runner.promote_rules import run_rule_promotion
from .rulebook.suggest import suggest_rules
from .rulebook.store import RulebookStore
from .verifier.cache import SqliteVerifierCache


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
    parser.add_argument("--task-metrics", action="store_true", help="Include per-task attempt and repair metrics.")
    return parser


def _build_flowmap_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze EventLog JSONL into offline FlowMap risk/opportunity maps.")
    parser.add_argument("--path", default=".rulecraft/eventlog.jsonl", help="EventLog JSONL file path.")
    parser.add_argument("--group-by", choices=("bucket_key",), default="bucket_key", help="Grouping dimension.")
    return parser


def _build_run_batch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run batch tasks and append canonical EventLog records.")
    parser.add_argument("--tasks", required=True, help="Task JSONL path.")
    parser.add_argument("--adapter", choices=("stub", "openai"), default="stub", help="Batch adapter backend.")
    parser.add_argument("--out", default=".rulecraft/eventlog.jsonl", help="EventLog JSONL output path.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of tasks to execute.")
    parser.add_argument("--instructions", default=None, help="Optional adapter instructions.")
    parser.add_argument("--repair", action="store_true", help="Enable repair attempts for failed tasks.")
    parser.add_argument("--max-attempts", type=int, default=1, help="Maximum attempts per task including primary.")
    parser.add_argument("--budget-usd", type=float, default=None, help="Optional per-task budget ceiling in USD.")
    parser.add_argument("--budget-tokens", type=int, default=None, help="Optional per-task token budget ceiling.")
    parser.add_argument("--rulebook", default=None, help="Optional rulebook JSON path for selection and injection.")
    parser.add_argument(
        "--scale",
        choices=("off", "auto", "probe", "full"),
        default="off",
        help="Scaling mode: off (default), auto policy, probe-only, or forced full rollout.",
    )
    parser.add_argument("--k-probe", type=int, default=3, help="Number of candidates for probe rollout.")
    parser.add_argument("--k-full", type=int, default=8, help="Number of candidates for full rollout.")
    parser.add_argument("--top-m", type=int, default=2, help="How many top candidates to keep before synth.")
    parser.add_argument("--no-synth", action="store_true", help="Disable synth step and return best ranked candidate.")
    parser.add_argument("--verifier-cache", default=None, help="Optional sqlite path for verifier result cache.")
    parser.add_argument("--policy-profile", default=None, help="Optional policy profile JSON path.")
    return parser


def _build_suggest_policy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Suggest a conservative policy profile from EventLog metrics.")
    parser.add_argument("--path", required=True, help="EventLog JSONL file path.")
    parser.add_argument("--out", required=True, help="Output policy profile JSON path.")
    parser.add_argument("--group-by", choices=("bucket_key",), default="bucket_key", help="Grouping dimension.")
    return parser


def _build_regpack_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a micro-regression pack from tasks and EventLog clusters.")
    parser.add_argument("--tasks", required=True, help="Tasks JSONL source of truth.")
    parser.add_argument("--eventlog", required=True, help="EventLog JSONL with failure clusters and pass outcomes.")
    parser.add_argument("--out", required=True, help="Output regpack JSONL path.")
    parser.add_argument("--per-cluster", type=int, default=2, help="Maximum unique tasks sampled per failure cluster.")
    parser.add_argument("--max-total", type=int, default=100, help="Hard cap on total sampled tasks.")
    parser.add_argument("--expand-counterexamples", action="store_true", help="Include deterministic prompt mutations.")
    parser.add_argument(
        "--counterexamples-per-cluster",
        type=int,
        default=2,
        help="Counterexamples generated for each sampled cluster task.",
    )
    parser.add_argument("--seed", type=int, default=1337, help="Deterministic seed for counterexample generation.")
    return parser


def _build_rule_suggest_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Suggest conservative rulebook entries from failure clusters.")
    parser.add_argument("--tasks", required=True, help="Tasks JSONL path.")
    parser.add_argument("--eventlog", required=True, help="EventLog JSONL path.")
    parser.add_argument("--out", required=True, help="Output rulebook JSON path.")
    parser.add_argument("--max-rules", type=int, default=20, help="Maximum suggested rules.")
    return parser


def _build_promote_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run baseline-vs-candidate promotion gate on a task pack.")
    parser.add_argument("--tasks", required=True, help="Task JSONL path (typically regpack output).")
    parser.add_argument("--adapter", choices=("stub", "openai"), default="stub", help="Adapter backend.")
    parser.add_argument("--baseline-profile", required=True, help="Baseline policy profile JSON path.")
    parser.add_argument("--candidate-profile", required=True, help="Candidate policy profile JSON path.")
    parser.add_argument("--tmp-dir", default=".rulecraft", help="Directory for temporary promotion EventLog outputs.")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed metadata for reproducibility.")
    parser.add_argument("--report", default=None, help="Optional output JSON report path.")
    parser.add_argument("--fail-on-regression", action="store_true", help="Return exit code 1 on promotion regressions.")
    return parser


def _build_promote_rules_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run baseline-vs-candidate rulebook promotion gate on a task pack.")
    parser.add_argument("--tasks", required=True, help="Task JSONL path (typically regpack output).")
    parser.add_argument("--adapter", choices=("stub", "openai"), default="stub", help="Adapter backend.")
    parser.add_argument("--baseline-rulebook", required=True, help="Baseline rulebook JSON path.")
    parser.add_argument("--candidate-rulebook", required=True, help="Candidate rulebook JSON path.")
    parser.add_argument("--policy-profile", default=None, help="Optional policy profile JSON path.")
    parser.add_argument("--tmp-dir", default=".rulecraft", help="Directory for temporary promotion EventLog outputs.")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed metadata for reproducibility.")
    parser.add_argument("--report", default=None, help="Optional output JSON report path.")
    parser.add_argument("--fail-on-regression", action="store_true", help="Return exit code 3 on promotion regressions.")
    return parser


def _build_batch_adapter(adapter_spec: str) -> Any:
    if adapter_spec == "stub":
        return StubAdapter(mode="text")
    if adapter_spec == "openai":
        return OpenAIAdapter()
    raise ValueError(f"Unsupported batch adapter: {adapter_spec!r}")


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else list(sys.argv[1:])
    if raw_argv and raw_argv[0] == "metrics":
        parser = _build_metrics_parser()
        args = parser.parse_args(raw_argv[1:])
        summary = summarize_jsonl(args.path, group_by=args.group_by, task_metrics=bool(args.task_metrics))
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if raw_argv and raw_argv[0] == "run-batch":
        parser = _build_run_batch_parser()
        args = parser.parse_args(raw_argv[1:])

        if args.adapter == "openai" and not os.getenv("OPENAI_API_KEY"):
            print("OPENAI_API_KEY is not set. Skipping OpenAI batch run.")
            return 2

        if args.max_attempts < 1:
            parser.error("--max-attempts must be >= 1")

        if args.budget_tokens is not None and args.budget_tokens < 0:
            parser.error("--budget-tokens must be >= 0")
        if args.k_probe < 1:
            parser.error("--k-probe must be >= 1")
        if args.k_full < 1:
            parser.error("--k-full must be >= 1")
        if args.top_m < 1:
            parser.error("--top-m must be >= 1")

        rulebook_store = None
        if args.rulebook:
            try:
                rulebook_store = RulebookStore.load_from_json(args.rulebook)
            except Exception as exc:  # pragma: no cover - parser error path
                parser.error(f"failed to load Rulebook from {args.rulebook!r}: {exc}")
        policy_profile = None
        if args.policy_profile:
            try:
                policy_profile = load_profile(args.policy_profile)
            except Exception as exc:  # pragma: no cover - parser error path
                parser.error(f"failed to load policy profile from {args.policy_profile!r}: {exc}")

        adapter = _build_batch_adapter(args.adapter)
        verifier_cache = SqliteVerifierCache(args.verifier_cache) if args.verifier_cache else None
        summary = run_batch(
            tasks_path=args.tasks,
            adapter=adapter,
            out_path=args.out,
            instructions=args.instructions,
            limit=args.limit,
            repair=bool(args.repair),
            max_attempts=int(args.max_attempts),
            budget_usd=args.budget_usd,
            budget_tokens=args.budget_tokens,
            rulebook_store=rulebook_store,
            scale=args.scale,
            k_probe=int(args.k_probe),
            k_full=int(args.k_full),
            top_m=int(args.top_m),
            synth=not bool(args.no_synth),
            verifier_cache=verifier_cache,
            policy_profile=policy_profile,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if raw_argv and raw_argv[0] == "suggest-policy":
        parser = _build_suggest_policy_parser()
        args = parser.parse_args(raw_argv[1:])
        profile = suggest_policy(args.path, group_by=args.group_by)
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"Suggested policy profile with {len(profile.get('rules', []))} bucket rule(s) from {args.path}.",
            file=sys.stderr,
        )
        return 0
    if raw_argv and raw_argv[0] == "regpack":
        parser = _build_regpack_parser()
        args = parser.parse_args(raw_argv[1:])
        if args.per_cluster < 1:
            parser.error("--per-cluster must be >= 1")
        if args.max_total < 1:
            parser.error("--max-total must be >= 1")
        if args.counterexamples_per_cluster < 1:
            parser.error("--counterexamples-per-cluster must be >= 1")

        summary = build_regpack(
            tasks_path=args.tasks,
            eventlog_path=args.eventlog,
            out_path=args.out,
            per_cluster=int(args.per_cluster),
            max_total=int(args.max_total),
            expand_counterexamples=bool(args.expand_counterexamples),
            counterexamples_per_cluster=int(args.counterexamples_per_cluster),
            seed=int(args.seed),
        )
        if args.expand_counterexamples:
            print(f"Counterexamples added: {summary.get('counterexamples_added', 0)}", file=sys.stderr)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if raw_argv and raw_argv[0] == "rule-suggest":
        parser = _build_rule_suggest_parser()
        args = parser.parse_args(raw_argv[1:])
        if args.max_rules < 1:
            parser.error("--max-rules must be >= 1")

        payload = suggest_rules(
            tasks_path=args.tasks,
            eventlog_path=args.eventlog,
            max_rules=int(args.max_rules),
        )
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary = payload.get("suggestion_summary")
        if isinstance(summary, dict):
            template_counts = summary.get("templates")
            if isinstance(template_counts, dict):
                top_templates = ", ".join(
                    f"{name}:{count}"
                    for name, count in sorted(template_counts.items(), key=lambda item: (-int(item[1]), str(item[0])))[:3]
                )
            else:
                top_templates = "none"
            print(
                f"Suggested {summary.get('rules_total', 0)} rule(s) from {summary.get('clusters_total', 0)} cluster(s). "
                f"Top templates: {top_templates}",
                file=sys.stderr,
            )
        else:
            print("Suggested rules written.", file=sys.stderr)
        return 0
    if raw_argv and raw_argv[0] == "promote":
        parser = _build_promote_parser()
        args = parser.parse_args(raw_argv[1:])

        if args.adapter == "openai" and not os.getenv("OPENAI_API_KEY"):
            print("OPENAI_API_KEY is not set. Skipping OpenAI promotion run.")
            return 2

        try:
            baseline_profile = load_profile(args.baseline_profile)
        except Exception as exc:  # pragma: no cover - parser error path
            parser.error(f"failed to load baseline profile from {args.baseline_profile!r}: {exc}")

        try:
            candidate_profile = load_profile(args.candidate_profile)
        except Exception as exc:  # pragma: no cover - parser error path
            parser.error(f"failed to load candidate profile from {args.candidate_profile!r}: {exc}")

        adapter = _build_batch_adapter(args.adapter)
        report = run_promotion(
            tasks_path=args.tasks,
            adapter=adapter,
            baseline_profile=baseline_profile,
            candidate_profile=candidate_profile,
            tmp_dir=args.tmp_dir,
            seed=args.seed,
        )
        if args.report:
            report_path = Path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        if args.fail_on_regression and not bool(report.get("ok")):
            return 1
        return 0
    if raw_argv and raw_argv[0] == "promote-rules":
        parser = _build_promote_rules_parser()
        args = parser.parse_args(raw_argv[1:])

        if args.adapter == "openai" and not os.getenv("OPENAI_API_KEY"):
            print("OPENAI_API_KEY is not set. Skipping OpenAI rule promotion run.")
            return 2

        if args.policy_profile:
            try:
                load_profile(args.policy_profile)
            except Exception as exc:  # pragma: no cover - parser error path
                parser.error(f"failed to load policy profile from {args.policy_profile!r}: {exc}")

        adapter = _build_batch_adapter(args.adapter)
        try:
            report = run_rule_promotion(
                tasks_path=args.tasks,
                adapter=adapter,
                baseline_rulebook_path=args.baseline_rulebook,
                candidate_rulebook_path=args.candidate_rulebook,
                policy_profile_path=args.policy_profile,
                tmp_dir=args.tmp_dir,
                seed=args.seed,
            )
        except Exception as exc:  # pragma: no cover - parser error path
            parser.error(str(exc))
            return 2

        if args.report:
            report_path = Path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        if args.fail_on_regression and not bool(report.get("ok")):
            return 3
        return 0
    if raw_argv and raw_argv[0] == "flowmap":
        parser = _build_flowmap_parser()
        args = parser.parse_args(raw_argv[1:])
        summary = analyze_flowmap(args.path, group_by=args.group_by)
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
