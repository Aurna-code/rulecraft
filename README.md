# Rulecraft v0.1

Rulecraft is an ops-kernel middleware layer for LLM/runtime calls: it runs `Rulebook` selection and injection, calls a `BackendAdapter`, applies `Validator` checks (L1 static by default), and writes minimal ref-centric run telemetry (`RunLog` JSONL with `TraceBundle`-style refs).

## 60-second Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python examples/minimal_run.py
```

CLI single-run example:

```bash
python -m rulecraft --text "Return a short JSON object." --json-only
```

This writes `logs/runlog.jsonl`. Example record (shortened):

```json
{"run_id":"39568b25-b4a6-47ff-a25b-43cd3c4189c3","input_ref":"mem://input/39568b25-b4a6-47ff-a25b-43cd3c4189c3","outputs":{"output_ref":"mem://output/39568b25-b4a6-47ff-a25b-43cd3c4189c3"},"validator":{"validator_id":"validator.l1.static","verdict":"PASS","outcome":"OK"},"control_signals":{"budget_tier":"hot","should_escalate":false,"early_exit":true,"repair_attempted":false,"repair_succeeded":false,"adapter_calls":1,"exit_stage":"l1","exit_reason":"confirmed_pass"}}
```

## EventLog and Metrics

Run the minimal EventLog writer:

```bash
python examples/minimal_runner.py
```

Aggregate EventLog metrics:

```bash
python -m rulecraft metrics --path .rulecraft/eventlog.jsonl
```

Analyze an offline FlowMap by `bucket_key`:

```bash
python -m rulecraft flowmap --path .rulecraft/eventlog.jsonl
```

Aggregate by `bucket_key`:

```bash
python -m rulecraft metrics --path .rulecraft/eventlog.jsonl --group-by bucket_key
```

Include task-level metrics from `run.extra.task_id` and `run.extra.attempt_idx`:

```bash
python -m rulecraft metrics --path .rulecraft/eventlog.jsonl --task-metrics
```

Task pass semantics: a task is counted as passed when any attempt for that task passes.

## Batch Experiments

Run a batch with the local stub adapter:

```bash
python -m rulecraft run-batch \
  --tasks examples/tasks/sample_tasks.jsonl \
  --adapter stub \
  --out .rulecraft/batch_eventlog.jsonl
```

Run with repair attempts and per-task budgets:

```bash
python -m rulecraft run-batch \
  --tasks examples/tasks/sample_tasks.jsonl \
  --adapter stub \
  --out .rulecraft/batch_eventlog_repair.jsonl \
  --repair \
  --max-attempts 3 \
  --budget-usd 0.10 \
  --budget-tokens 2000
```

Run with test-time scaling:

```bash
python -m rulecraft run-batch \
  --tasks examples/tasks/sample_tasks.jsonl \
  --adapter stub \
  --out .rulecraft/batch_eventlog_scale_auto.jsonl \
  --scale auto
```

Choose explicit scaling tiers:

```bash
python -m rulecraft run-batch \
  --tasks examples/tasks/sample_tasks.jsonl \
  --adapter stub \
  --out .rulecraft/batch_eventlog_scale_probe.jsonl \
  --scale probe \
  --k-probe 3 \
  --top-m 2
```

```bash
python -m rulecraft run-batch \
  --tasks examples/tasks/sample_tasks.jsonl \
  --adapter stub \
  --out .rulecraft/batch_eventlog_scale_full.jsonl \
  --scale full \
  --k-full 8
```

Scaling defaults are conservative: `--scale off` unless explicitly enabled. Budget ceilings still cap escalation from probe to full.

Apply bucket-aware policy profile overrides:

```bash
python -m rulecraft run-batch \
  --tasks examples/tasks/sample_tasks.jsonl \
  --adapter stub \
  --out .rulecraft/batch_eventlog_policy.jsonl \
  --policy-profile examples/policies/sample_policy_profile.json
```

Policy profiles support per-bucket overrides for `max_attempts`, scaling mode, rollout K values, synth toggle, and budgets. First matching rule wins.

Suggest a conservative policy profile from EventLog analytics:

```bash
python -m rulecraft suggest-policy \
  --path .rulecraft/eventlog.jsonl \
  --out .rulecraft/suggested_policy_profile.json
```

The generated profile is conservative and bucket-aware:

- Increase `max_attempts` when repair gain is high and repair cost is low.
- Enable `scale=auto` when unknown outcomes are high but format leaks are low.
- Cap or disable costly low-yield full rollout paths.
- Keep synth enabled for schema-heavy failure buckets.

Suggest conservative rulebook entries from observed failure clusters:

```bash
python -m rulecraft rule-suggest \
  --tasks examples/tasks/sample_tasks.jsonl \
  --eventlog .rulecraft/eventlog.jsonl \
  --out .rulecraft/suggested_rulebook.json \
  --max-rules 20
```

`rule-suggest` focuses on format/schema compliance, contract restatement, and deterministic output guidance. Suggestions are conservative and avoid adding factual claims.

Lint a rulebook for structural issues, duplicates, conflicts, and optional eventlog usage:

```bash
python -m rulecraft rule-lint \
  --rulebook .rulecraft/suggested_rulebook.json \
  --eventlog .rulecraft/eventlog.jsonl
```

`rule-lint` exit codes:

- `0`: no errors (warnings are allowed)
- `4`: lint errors, or warnings when `--strict` is set

Prune low-value rules from a rulebook using eventlog selection/impact stats:

```bash
python -m rulecraft rule-prune \
  --rulebook .rulecraft/suggested_rulebook.json \
  --eventlog .rulecraft/eventlog.jsonl \
  --out .rulecraft/pruned_rulebook.json \
  --min-selected 3
```

Dry-run pruning without writing output:

```bash
python -m rulecraft rule-prune \
  --rulebook .rulecraft/suggested_rulebook.json \
  --eventlog .rulecraft/eventlog.jsonl \
  --out .rulecraft/pruned_rulebook.json \
  --dry-run
```

## Regression Packs and Promotion Gates

Build a micro-regression pack from failure clusters and pass-task canaries:

```bash
python -m rulecraft regpack \
  --tasks examples/tasks/sample_tasks.jsonl \
  --eventlog .rulecraft/eventlog.jsonl \
  --out .rulecraft/regpack.jsonl \
  --per-cluster 2 \
  --max-total 100
```

Expand regpack tasks with deterministic counterexample mutations:

```bash
python -m rulecraft regpack \
  --tasks examples/tasks/sample_tasks.jsonl \
  --eventlog .rulecraft/eventlog.jsonl \
  --out .rulecraft/regpack_with_ce.jsonl \
  --expand-counterexamples \
  --counterexamples-per-cluster 2 \
  --seed 1337
```

Run promotion gate on baseline vs candidate policy profiles:

```bash
python -m rulecraft promote \
  --tasks .rulecraft/regpack.jsonl \
  --adapter stub \
  --baseline-profile examples/policies/sample_policy_profile.json \
  --candidate-profile .rulecraft/suggested_policy_profile.json \
  --fail-on-regression \
  --report .rulecraft/promotion_report.json
```

Promotion report highlights:

- `deltas.task_pass_rate`: candidate minus baseline task pass rate.
- `deltas.avg_attempts_per_task`: candidate minus baseline attempts per task.
- `deltas.cost_usd_total`: candidate minus baseline total cost (when available).
- `deltas.schema_violation_rate`: candidate minus baseline schema violation rate.
- `regressions`: threshold violations that fail the gate when `--fail-on-regression` is set.
- `warnings`: non-fatal degradations to inspect.

Run promotion gate on baseline vs candidate rulebooks:

```bash
python -m rulecraft promote-rules \
  --tasks .rulecraft/regpack_with_ce.jsonl \
  --adapter stub \
  --baseline-rulebook rules/sample_rulebook.json \
  --candidate-rulebook .rulecraft/suggested_rulebook.json \
  --fail-on-regression \
  --report .rulecraft/rule_promotion_report.json
```

Rule gate report highlights:

- `deltas.task_pass_rate` and `deltas.strong_pass_rate`: candidate minus baseline task success deltas.
- `deltas.schema_violation_rate` and `deltas.format_leak_rate`: quality and compliance regressions.
- `top_worsened_clusters`: baseline top failure clusters that got worse in candidate runs.
- `rule_impact.baseline.rule_selection_counts` and `rule_impact.candidate.rule_selection_counts`: rule usage counts by `rule_id`.
- `rule_impact.improvements.top_rules_on_improvements`: candidate rules most associated with improved tasks.
- `rule_impact.regressions.top_rules_on_regressions`: candidate rules most associated with regressed tasks.
- `rule_impact.*.unused_rules`: rule IDs that were never selected in the corresponding run.
- `regressions`: hard threshold failures (with `--fail-on-regression`, CLI returns exit code `3`).

## Task Contracts and L3 Validation

Task JSONL rows can include an optional `contract` object:

```json
{
  "task_id": "contract-json-1",
  "prompt": "Return JSON with status and count.",
  "mode": "json",
  "contract": {
    "type": "jsonschema",
    "schema_id": "contract.status_count.v1",
    "schema": {
      "type": "object",
      "required": ["status", "count"],
      "properties": {
        "status": {"type": "string"},
        "count": {"type": "integer"}
      },
      "additionalProperties": false
    }
  }
}
```

Verification behavior:

- L1 still checks parse/format.
- For `mode=json` with `contract.type=jsonschema`, L3 validates against the schema.
- Parseable JSON that violates schema is `FAIL/FAIL` (not `PASS`).

Event logs keep contract metadata only (`type`, `schema_id`, `has_schema`) under `run.extra.contract`. Full schemas are not stored in EventLog lines.

Run with rulebook selection and injection:

```bash
python -m rulecraft run-batch \
  --tasks examples/tasks/sample_tasks.jsonl \
  --adapter stub \
  --out .rulecraft/batch_eventlog_rulebook.jsonl \
  --rulebook rules/sample_rulebook.json
```

Run the example wrapper script:

```bash
python examples/minimal_batch_run.py
```

Run the contract-focused batch example:

```bash
python examples/minimal_contract_batch_run.py
```

Run a batch with OpenAI Responses API:

```bash
python -m rulecraft run-batch \
  --tasks examples/tasks/sample_tasks.jsonl \
  --adapter openai \
  --out .rulecraft/batch_eventlog_openai.jsonl
```

The OpenAI adapter is optional. Set `OPENAI_API_KEY` before using `--adapter openai`.

## Core Components

- `Orchestrator`: runtime hot-loop (`select -> inject -> generate -> validate -> repair(optional) -> log`).
- `Rulebook`: JSON rules loaded by `RulebookStore`, selected by context and constraints, then injected via `system_guard`, `prepend`, or `inline`.
- `Validator (L1)`: `validator.l1.static` checks `json_only` and `length_lte`, returning `verdict`, `outcome`, `reason_codes`, and `violated_constraints`.
- `RunLog`: JSONL run summary keyed by stable fields like `run_id`, `input_ref`, `outputs.output_ref`, `control_signals`, and `validator`.

## Safety Defaults

- Default posture is untrusted.
- Never store raw PII/secrets in `RunLog` or `TraceBundle`; store refs only (`input_ref`, `output_ref`, external artifact refs).
