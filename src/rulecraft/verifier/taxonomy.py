"""Canonical verifier taxonomy for reason codes and violated constraints."""

from __future__ import annotations

import re
from typing import Iterable

# Canonical reason codes.
FORMAT_LEAK = "FORMAT_LEAK"
JSON_PARSE = "JSON_PARSE"
SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
COST_META_COERCED = "COST_META_COERCED"
EXEC_UNAVAILABLE = "EXEC_UNAVAILABLE"
SANDBOX_TIMEOUT = "SANDBOX_TIMEOUT"
SANDBOX_DENIED = "SANDBOX_DENIED"
TOOL_TIMEOUT = "TOOL_TIMEOUT"
TOOL_FAILURE = "TOOL_FAILURE"
ENV_NONDETERMINISM = "ENV_NONDETERMINISM"
RETRY_RECOVERED = "RETRY_RECOVERED"

# Canonical violated constraints.
VC_FORMAT_JSON_ONLY = "FORMAT:JSON_ONLY"
VC_FORMAT_JSON_PARSE = "FORMAT:JSON_PARSE"
VC_POLICY_NO_NETWORK = "POLICY:NO_NETWORK"
VC_TOOL_EXEC_TIMEOUT = "TOOL:EXEC_TIMEOUT"
VC_TOOL_EXEC_FAILED = "TOOL:EXEC_FAILED"
VC_TOOL_OUTPUT_INVALID = "TOOL:OUTPUT_INVALID"


def _sanitize_segment(value: str) -> str:
    compact = value.strip()
    if not compact:
        return "_"
    compact = compact.replace(" ", "_")
    compact = re.sub(r"[^A-Za-z0-9._\-\[\]\$]", "_", compact)
    return compact[:48]


def vc_jsonschema(path: str, validator: str) -> str:
    """Build a stable JSON Schema violation identifier."""
    return f"SCHEMA:JSONSCHEMA:{_sanitize_segment(path)}:{_sanitize_segment(validator)}"


def normalize_codes(codes: Iterable[str] | None) -> list[str] | None:
    """Normalize reason/constraint lists to deterministic unique ordering."""
    if codes is None:
        return None
    normalized = sorted({str(code) for code in codes if isinstance(code, str) and code})
    if not normalized:
        return None
    return normalized


__all__ = [
    "FORMAT_LEAK",
    "JSON_PARSE",
    "SCHEMA_VIOLATION",
    "COST_META_COERCED",
    "EXEC_UNAVAILABLE",
    "SANDBOX_TIMEOUT",
    "SANDBOX_DENIED",
    "TOOL_TIMEOUT",
    "TOOL_FAILURE",
    "ENV_NONDETERMINISM",
    "RETRY_RECOVERED",
    "VC_FORMAT_JSON_ONLY",
    "VC_FORMAT_JSON_PARSE",
    "VC_POLICY_NO_NETWORK",
    "VC_TOOL_EXEC_TIMEOUT",
    "VC_TOOL_EXEC_FAILED",
    "VC_TOOL_OUTPUT_INVALID",
    "vc_jsonschema",
    "normalize_codes",
]
