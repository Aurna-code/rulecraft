# Changelog
All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-02-20
### Added
- SSOT-aligned contracts (RunLog, ValidationResult, TraceBundle) and JSONL logging
- Rulebook loader + rule selection + injection plan (system_guard / prepend / inline)
- Orchestrator hot-loop (select -> inject -> generate -> L1 validate -> optional JSON-only repair -> log)
- L1 static validator (JSON-only, length_lte) with stable failure_cluster_id
- Single auto-repair attempt for JSON-only failures (hot tier), with stable control_signals:
  - exit_stage: l1 / l1_repair
  - exit_reason: confirmed_pass / repaired_pass / needs_escalation
  - repair_attempted / repair_succeeded / adapter_calls
- Minimal CLI (`python -m rulecraft ...`)
- Guardrail script to prevent legacy term reintroduction
- GitHub Actions CI (pytest + legacy term check)
