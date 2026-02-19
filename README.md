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

## Core Components

- `Orchestrator`: runtime hot-loop (`select -> inject -> generate -> validate -> repair(optional) -> log`).
- `Rulebook`: JSON rules loaded by `RulebookStore`, selected by context and constraints, then injected via `system_guard`, `prepend`, or `inline`.
- `Validator (L1)`: `validator.l1.static` checks `json_only` and `length_lte`, returning `verdict`, `outcome`, `reason_codes`, and `violated_constraints`.
- `RunLog`: JSONL run summary keyed by stable fields like `run_id`, `input_ref`, `outputs.output_ref`, `control_signals`, and `validator`.

## Safety Defaults

- Default posture is untrusted.
- Never store raw PII/secrets in `RunLog` or `TraceBundle`; store refs only (`input_ref`, `output_ref`, external artifact refs).
