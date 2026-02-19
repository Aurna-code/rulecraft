"""Rule selection for Rulebook runtime v0.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..contracts import SCHEMA_VERSION
from .store import RulebookStore, RuleStatus

RuleType = Literal["StrategyRule", "GuardrailRule"]
InjectionMode = Literal["system_guard", "prepend", "inline"]


@dataclass(slots=True)
class RuleSelectRequest:
    schema_version: str = SCHEMA_VERSION
    request_id: str = ""
    input_ref: str = ""
    bucket_id: str | None = None
    context: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None

    # Backward-compatible fallbacks for older callers.
    domain_tag: str | None = None
    task_family: str | None = None
    max_rules: int = 3
    allow_types: list[RuleType] | None = None
    status: RuleStatus | None = "active"


@dataclass(slots=True)
class RuleSelectResponse:
    schema_version: str = SCHEMA_VERSION
    request_id: str = ""
    applied_rules: list[dict[str, Any]] = field(default_factory=list)
    exploration: dict[str, Any] | None = None


def select_rules(request: RuleSelectRequest, store: RulebookStore) -> RuleSelectResponse:
    candidates = store.list(status=request.status)
    scored_rules: list[tuple[int, int, str, str, dict[str, Any], RuleType, list[str]]] = []

    context = request.context or {}
    constraints = request.constraints or {}
    domain_tag = str(context.get("domain_tag") or request.domain_tag or "")
    task_family = str(context.get("task_family") or request.task_family or "")

    constraint_max_rules = constraints.get("max_rules")
    if isinstance(constraint_max_rules, int):
        max_rules = max(constraint_max_rules, 0)
    else:
        max_rules = max(request.max_rules, 0)

    allow_types = _normalize_allow_types(constraints.get("allow_types"), request.allow_types)

    for candidate in candidates:
        rule_type = _normalize_rule_type(candidate.get("type"))
        if rule_type is None:
            continue
        if allow_types and rule_type not in allow_types:
            continue

        score, reasons = _score_rule(
            candidate=candidate,
            domain_tag=domain_tag,
            task_family=task_family,
            bucket_id=request.bucket_id,
            rule_type=rule_type,
        )
        if score <= 0:
            continue

        rank = _normalize_rank(_read_priority_rank(candidate))
        scored_rules.append(
            (
                -score,
                rank,
                str(candidate.get("rule_id", "")),
                str(candidate.get("version", "")),
                candidate,
                rule_type,
                reasons,
            )
        )

    scored_rules.sort(key=lambda item: item[:4])

    selected: list[dict[str, Any]] = []
    for neg_score, _, _, _, candidate, rule_type, reasons in scored_rules[:max_rules]:
        body = _read_rule_body(candidate)

        item = {
            "rule_id": str(candidate.get("rule_id", "")),
            "version": str(candidate.get("version", "")),
            "type": rule_type,
            "injection_mode": _normalize_injection_mode(candidate.get("injection_mode"), rule_type),
            "score": float(max(-neg_score, 0)),
            "reasons": reasons or None,
        }
        if body:
            # Local runtime convenience for building injection plans.
            item["body"] = body
        selected.append(item)

    return RuleSelectResponse(
        request_id=request.request_id,
        applied_rules=selected,
        exploration={"used_debias": False, "debias_weight": None},
    )


def _score_rule(
    candidate: dict[str, Any],
    domain_tag: str,
    task_family: str,
    bucket_id: str | None,
    rule_type: RuleType,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    applicability = candidate.get("applicability")
    if not isinstance(applicability, dict):
        applicability = {}

    candidate_domain_tag = str(applicability.get("domain_tag") or candidate.get("domain_tag") or "")
    candidate_task_family = str(applicability.get("task_family") or candidate.get("task_family") or "")
    candidate_bucket_id = str(candidate.get("bucket_id") or "")
    candidate_bucket_ids = applicability.get("bucket_ids")
    if not isinstance(candidate_bucket_ids, list):
        candidate_bucket_ids = []

    if domain_tag and candidate_domain_tag == domain_tag:
        score += 2
        reasons.append("domain_tag_match")
    if task_family and candidate_task_family == task_family:
        score += 2
        reasons.append("task_family_match")
    if bucket_id and (candidate_bucket_id == bucket_id or bucket_id in candidate_bucket_ids):
        score += 1
        reasons.append("bucket_id_match")
    if rule_type == "GuardrailRule":
        score += 1
        reasons.append("guardrail_bias")

    return score, reasons


def _normalize_allow_types(value: Any, fallback: list[RuleType] | None) -> list[RuleType]:
    source = value if isinstance(value, list) else fallback
    if not source:
        return ["StrategyRule", "GuardrailRule"]

    normalized: list[RuleType] = []
    for item in source:
        if item == "StrategyRule":
            normalized.append("StrategyRule")
        elif item == "GuardrailRule":
            normalized.append("GuardrailRule")
    if not normalized:
        return ["StrategyRule", "GuardrailRule"]
    return normalized


def _normalize_rule_type(value: Any) -> RuleType | None:
    if value == "StrategyRule":
        return "StrategyRule"
    if value == "GuardrailRule":
        return "GuardrailRule"
    return None


def _read_priority_rank(candidate: dict[str, Any]) -> Any:
    priority = candidate.get("priority")
    if isinstance(priority, dict):
        return priority.get("rank")
    return candidate.get("rank")


def _read_rule_body(candidate: dict[str, Any]) -> str:
    body = candidate.get("body")
    if isinstance(body, str) and body.strip():
        return body.strip()
    return ""


def _normalize_injection_mode(value: Any, rule_type: RuleType) -> InjectionMode:
    if value in {"system_guard", "prepend", "inline"}:
        return value
    if rule_type == "GuardrailRule":
        return "system_guard"
    return "prepend"


def _normalize_rank(value: Any) -> int:
    if isinstance(value, bool):
        return 999_999
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 999_999
    return 999_999
