"""Minimal Rulebook load/select/injection-plan example for Rulecraft v0.1."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.rulebook.injection import build_injection_plan  # noqa: E402
from rulecraft.rulebook.select import RuleSelectRequest, select_rules  # noqa: E402
from rulecraft.rulebook.store import RulebookStore  # noqa: E402


def main() -> None:
    store = RulebookStore.load_from_json(ROOT / "rules" / "sample_rulebook.json")

    request = RuleSelectRequest(
        request_id="req-example-0001",
        input_ref="sha1:example",
        bucket_id="support",
        context={"domain_tag": "payments", "task_family": "answer"},
        constraints={"max_rules": 3, "allow_types": ["StrategyRule", "GuardrailRule"]},
        status=None,
    )

    response = select_rules(request, store)
    injection_plan = build_injection_plan(
        applied_rules=response.applied_rules,
        input_text="I lost my card. How can I replace it?",
    )

    print("applied_rules")
    print(json.dumps(response.applied_rules, ensure_ascii=False, sort_keys=True, indent=2))
    print()
    print("injection_plan")
    print(json.dumps(injection_plan, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
