# Rulecraft Public Terminology Mapping (v0.1.0)

- 목적: 공개 릴리즈 문서/코드/스키마에서 사용하는 **공식 용어**와 기존(레거시) 용어의 대응표.
- 원칙: Rulebook은 유지. SSOT는 계약으로서 버전업 후 새 필드명을 정본으로 사용.

## Core components

| Public (권장) | Legacy (기존) |
|---|---|
| `Orchestrator` | `Runner / Runner/Orchestrator` |
| `BackendAdapter` | `Adapter` |
| `Validator` | `Verifier` |
| `ValidationResult` | `VerifierResult` |
| `RunLog` | `EventLog` |
| `TraceBundle` | `TraceCapsule` |
| `RuleSelect` | `CandidateSelect` |
| `ContextBlock` | `ContextUnit` |
| `Selective Context Injection` | `SIEVE-lite` |
| `BudgetController` | `BudgetRouter` |
| `should_escalate` | `should_scale` |
| `K-drafts` | `K-rollout` |
| `SummaryBuilder` | `Compactor` |
| `Composer` | `Synth` |
| `SelfReview-1pass` | `SoT-1pass` |
| `DraftSummarizeCompose-lite` | `PaCoRe-lite` |
| `SeededMultiDraft` | `MaTTS` |
| `Rulebook` | `Rulebook (unchanged)` |



## Process terms (권장)

| Public (권장) | Legacy (기존) |
|---|---|
| `Compose Pass` | `Synthesis Pass` |
| `ContextBlockSpec` | `CUSpec` |

## Naming conventions (권장)

- `ContextBlock` ID는 `cb_` 프리픽스를 권장한다. (예: `cb_format_json_only_v1`)
- 집계/메트릭 키에서는 `cu_*` 대신 `context_*`를 권장한다. (예: `context_unknown_rate`)

## SSOT field rename highlights

| Public field | Legacy field |
|---|---|
| `run_id` | `trace_id` |
| `run_ids` | `trace_ids` |
| `input_ref` | `x_ref` |
| `output_ref` | `y_ref` |
| `bucket_id` | `bucket_key` |
| `bucket_ids` | `bucket_keys` |
| `run_tags` | `flow_tags` |
| `control_signals` | `policy_signals` |
| `applied_rules` | `selected_rules` |
| `draft_select` | `rollout_select` |
| `draft_summary` | `rollout_summary` |
| `self_review_signals` | `sot_signals` |
| `compose_inputs` | `synth_inputs` |
| `context_select` | `cu_select` |
| `context_select_v1` | `cu_select_v1` |
| `candidate_context_ids` | `candidate_cu_ids` |
| `applicable_context_ids` | `applicable_cu_ids` |
| `rejected_context_ids` | `rejected_cu_ids` |
| `unknown_context_ids` | `unknown_cu_ids` |
| `conflict_pruned_context_ids` | `conflict_pruned_cu_ids` |
| `injected_context_ids` | `injected_cu_ids` |
| `context_id` | `cu_id` |
| `context_hint` | `cu_hint` |
| `context_pack` | `cu_pack` |
