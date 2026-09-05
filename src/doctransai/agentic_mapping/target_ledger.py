from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from doctransai.agentic_mapping.decisions import AgentDecision
from doctransai.agentic_mapping.validator import ValidationResult
from doctransai.models.render_plan import RenderPlan
from doctransai.renderers.models import RenderResult


def build_target_ledger(
    *,
    evidence_package: dict[str, Any],
    decisions: list[AgentDecision],
    validation_result: ValidationResult,
    render_plan: RenderPlan,
    render_result: RenderResult,
) -> list[dict[str, Any]]:
    """Build a per-template-target audit view without changing mapping behavior."""

    del decisions
    accepted_by_slot = _decisions_by_slot(validation_result.accepted_decisions)
    rejected_by_slot = _decisions_by_slot(validation_result.rejected_decisions)
    validation_codes_by_slot = _diagnostic_codes_by_slot(validation_result.diagnostics)
    render_codes_by_slot = _render_diagnostic_codes_by_slot(render_result)
    unresolved_slot_ids = {slot.slot_id for slot in render_plan.unresolved_slots}
    applied_text_slot_ids = set(render_result.applied_text_slots)
    applied_image_slot_ids = set(render_result.applied_image_slots)

    ledger: list[dict[str, Any]] = []
    for target in _template_targets(evidence_package):
        target_id = _target_id(target)
        if target_id is None:
            continue
        decision = accepted_by_slot.get(target_id)
        rejected_decision = rejected_by_slot.get(target_id)
        active_decision = decision or rejected_decision
        entry = _base_entry(target, target_id)
        diagnostics = [
            *validation_codes_by_slot.get(target_id, []),
            *render_codes_by_slot.get(target_id, []),
        ]

        if decision is not None:
            entry["decision_type"] = _ledger_decision_type(decision)
            entry["decision_status"] = "accepted"
            entry["render_status"] = _accepted_render_status(
                decision,
                unresolved_slot_ids=unresolved_slot_ids,
                applied_text_slot_ids=applied_text_slot_ids,
                applied_image_slot_ids=applied_image_slot_ids,
            )
            _add_decision_fields(entry, decision)
        elif rejected_decision is not None:
            entry["decision_type"] = _ledger_decision_type(rejected_decision)
            entry["decision_status"] = "rejected"
            entry["render_status"] = (
                "not_applicable"
                if _is_not_applicable_decision(rejected_decision)
                else
                "unresolved"
                if rejected_decision.slot_id in unresolved_slot_ids
                else "rejected"
            )
            _add_decision_fields(entry, rejected_decision)
        else:
            entry["decision_type"] = "missing"
            entry["decision_status"] = "missing"
            entry["render_status"] = "missing"
            entry["source_refs"] = []
            entry["reason"] = "Agent returned no decision for this template target."

        if active_decision is not None and "source_refs" not in entry:
            entry["source_refs"] = []
        entry["diagnostics"] = diagnostics
        ledger.append(entry)
    return ledger


def _template_targets(evidence_package: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    targets = evidence_package.get("template", {}).get("targets", [])
    if isinstance(targets, list):
        return (target for target in targets if isinstance(target, Mapping))
    return ()


def _target_id(target: Mapping[str, Any]) -> str | None:
    value = target.get("target_id")
    return value if isinstance(value, str) and value else None


def _base_entry(target: Mapping[str, Any], target_id: str) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "origin": _string_field(target, "origin"),
        "label": _string_field(target, "label"),
        "expected_content_type": _string_field(target, "expected_content_type"),
    }


def _string_field(target: Mapping[str, Any], key: str) -> str | None:
    value = target.get(key)
    return value if isinstance(value, str) else None


def _accepted_render_status(
    decision: AgentDecision,
    *,
    unresolved_slot_ids: set[str],
    applied_text_slot_ids: set[str],
    applied_image_slot_ids: set[str],
) -> str:
    if _is_not_applicable_decision(decision):
        return "not_applicable"
    if decision.decision_type == "unresolved" or decision.slot_id in unresolved_slot_ids:
        return "unresolved"
    if decision.decision_type == "text_fill":
        return "applied" if _slot_or_repeat_instance_applied(decision.slot_id, applied_text_slot_ids) else "not_applied"
    if decision.decision_type == "image_placement":
        return "applied" if _slot_or_repeat_instance_applied(decision.slot_id, applied_image_slot_ids) else "not_applied"
    return "not_applied"


def _ledger_decision_type(decision: AgentDecision) -> str:
    if _is_not_applicable_decision(decision):
        return "not_applicable"
    return decision.decision_type


def _slot_or_repeat_instance_applied(slot_id: str, applied_slot_ids: set[str]) -> bool:
    if slot_id in applied_slot_ids:
        return True
    prefix = f"{slot_id}@"
    return any(applied_slot_id.startswith(prefix) for applied_slot_id in applied_slot_ids)


def _is_not_applicable_decision(decision: AgentDecision) -> bool:
    if decision.decision_type != "unresolved":
        return False
    reason = (decision.reason or "").casefold()
    return any(
        marker in reason
        for marker in (
            "not applicable",
            "does not apply",
            "does not require filling",
            "not require filling",
            "not required",
            "not needed",
            "no other specification is needed",
            "no additional specification is needed",
            "only relevant when",
            "conditional",
            "不适用",
            "无需填写",
            "不需要填写",
            "不需填写",
        )
    )


def _add_decision_fields(entry: dict[str, Any], decision: AgentDecision) -> None:
    value_preview = _value_preview(decision.value)
    if value_preview is not None:
        entry["value_preview"] = value_preview
    if decision.asset_ref:
        entry["asset_ref"] = decision.asset_ref
    entry["source_refs"] = list(decision.source_refs)
    if decision.reason:
        entry["reason"] = decision.reason


def _value_preview(value: Any, *, limit: int = 80) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _decisions_by_slot(decisions: Iterable[AgentDecision]) -> dict[str, AgentDecision]:
    by_slot: dict[str, AgentDecision] = {}
    for decision in decisions:
        by_slot.setdefault(decision.slot_id, decision)
    return by_slot


def _diagnostic_codes_by_slot(diagnostics: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    by_slot: dict[str, list[str]] = {}
    for diagnostic in diagnostics:
        slot_id = diagnostic.get("slot_id")
        code = diagnostic.get("code")
        if isinstance(slot_id, str) and slot_id and isinstance(code, str) and code:
            by_slot.setdefault(slot_id, []).append(code)
    return by_slot


def _render_diagnostic_codes_by_slot(render_result: RenderResult) -> dict[str, list[str]]:
    by_slot: dict[str, list[str]] = {}
    for diagnostic in render_result.diagnostics:
        slot_id = diagnostic.slot_id
        if slot_id:
            by_slot.setdefault(slot_id, []).append(diagnostic.code)
    return by_slot


__all__ = ["build_target_ledger"]
