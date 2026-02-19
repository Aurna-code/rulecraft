# Security Notes (v0.1)

## Threat Model (Concise)

- Input prompt injection can attempt to override `Rulebook`/guardrails.
- Rule injection can occur through malformed or untrusted rule sources.
- Adapter outputs can include unsafe or policy-breaking content.
- Secret exfiltration can happen if prompts or outputs echo credentials/tokens.
- PII leakage can happen if raw user data is persisted directly in logs.
- Reference spoofing can mislead downstream systems if refs are not validated.
- Escalation/repair loops can amplify bad prompts without bounded policy.
- Over-logging can expose unnecessary operational data.
- Schema drift can hide policy signals if keys are renamed ad hoc.
- Legacy-term usage can reintroduce deprecated contracts unexpectedly.

## Non-Negotiables

- Never store raw secrets/PII in `RunLog` or `TraceBundle`; store refs only.
- Default posture is untrusted.
- Keep `Rulebook` linting and legacy-term guardrails enabled in CI/local checks.

## Practical Controls in This Repo

- L1 validation (`validator.l1.static`) enforces basic format constraints.
- `control_signals` records `should_escalate`, `repair_attempted`, `exit_stage`, and related signals for auditability.
- `scripts/check_legacy_terms.py` blocks deprecated naming patterns in runtime/example code.
