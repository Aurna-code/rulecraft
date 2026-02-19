"""Budget policy signals for v0.1 core runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import ValidationResult


@dataclass(slots=True)
class BudgetController:
    tier: str = "hot"

    def should_escalate(self, vr: ValidationResult, context: dict[str, Any]) -> bool:
        _ = context
        return (vr.verdict != "PASS") or (vr.outcome != "OK")
