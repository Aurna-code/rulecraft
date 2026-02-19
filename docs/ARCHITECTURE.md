# Rulecraft v0.1 Architecture

## Scope

Rulecraft v0.1 ships a minimal runtime kernel:

- `Orchestrator`
- `BackendAdapter`
- `Validator` (L1 static default)
- `Rulebook` selection/injection
- `RunLog` JSONL logging with refs

Advanced modules are out of scope for this release and treated as off-by-default/optional contracts.

## Data Plane

- `RunLog` is the primary execution summary record (`logs/runlog.jsonl`).
- `RunLog` stores stable keys such as `run_id`, `input_ref`, `outputs.output_ref`, `applied_rules`, `validator`, `cost`, `control_signals`, and optional `context_select`.
- `TraceBundle` is ref-centric for detailed traces and joins to `RunLog` by `run_id`.
- Log records should store refs, not raw sensitive payloads.

## Control Plane

`RunLog.control_signals` captures runtime policy decisions and outcomes:

- `budget_tier` (`hot` default in current runtime)
- `should_escalate`
- `early_exit`
- `repair_attempted`
- `repair_succeeded`
- `adapter_calls`
- `exit_stage` (`l1` or `l1_repair` in v0.1 core flow)
- `exit_reason` (`confirmed_pass`, `repaired_pass`, `needs_escalation` in current code path)

These keys reflect current `Orchestrator` behavior and SSOT stable naming.

## Runtime Flow

1. `select`: select matching `Rulebook` rules by context/constraints.
2. `inject`: build injection plan (`system_guard` / `prepend` / `inline`) and prompt messages.
3. `generate`: call `BackendAdapter.generate(...)` for first output.
4. `validate`: run L1 static validator (`json_only`, `length_lte` checks).
5. `repair` (optional): if `json_only` fails, retry once with repair prompt and re-validate.
6. `log`: append one `RunLog` JSON line with validator/cost/control results.
