# Contributing

## Local Checks

- `python -m pytest`
- `python scripts/check_legacy_terms.py`

## Style (Minimal)

- Keep changes small and reviewable.
- Preserve SSOT stable key names (`run_id`, `input_ref`, `output_ref`, `control_signals`, `context_select`, etc.).
- Keep default behavior untrusted and avoid logging raw PII/secrets.
- Prefer adding tests when behavior changes.
