from __future__ import annotations

from collections import defaultdict
from typing import Any

from doctransai.agentic_mapping.decisions import AgentDecision


def repair_duplicate_decisions(
    decisions: list[AgentDecision],
) -> tuple[list[AgentDecision], list[dict[str, Any]]]:
    by_slot: dict[str, list[AgentDecision]] = defaultdict(list)
    for decision in decisions:
        by_slot[decision.slot_id].append(decision)

    repaired: list[AgentDecision] = []
    diagnostics: list[dict[str, Any]] = []
    for slot_id, slot_decisions in by_slot.items():
        if len(slot_decisions) == 1:
            normalized = _repair_single_decision(slot_decisions[0])
            repaired.append(normalized.decision)
            if normalized.diagnostic:
                diagnostics.append(normalized.diagnostic)
            continue
        normalized = _repair_slot_decisions(slot_id, slot_decisions)
        repaired.append(normalized.decision)
        diagnostics.append(normalized.diagnostic)
    return repaired, diagnostics


class _RepairResult:
    def __init__(self, decision: AgentDecision, diagnostic: dict[str, Any] | None) -> None:
        self.decision = decision
        self.diagnostic = diagnostic


def _repair_single_decision(decision: AgentDecision) -> _RepairResult:
    if decision.decision_type == "text_fill" and not (decision.value or "").strip():
        return _RepairResult(
            decision=AgentDecision(
                slot_id=decision.slot_id,
                decision_type="unresolved",
                source_refs=list(decision.source_refs),
                target_ref=decision.target_ref,
                reason=decision.reason or "Agent returned an empty text fill.",
                reason_code="empty_text_fill",
            ),
            diagnostic={
                "severity": "warning",
                "code": "empty_text_fill_converted_to_unresolved",
                "message": "Agent returned an empty text_fill; converted the target to unresolved.",
                "slot_id": decision.slot_id,
            },
        )
    return _RepairResult(decision=decision, diagnostic=None)


def _repair_slot_decisions(slot_id: str, decisions: list[AgentDecision]) -> _RepairResult:
    render_decisions = [decision for decision in decisions if decision.decision_type != "unresolved"]
    if render_decisions and _equivalent_render_decisions(render_decisions):
        return _RepairResult(
            decision=render_decisions[0],
            diagnostic={
                "severity": "warning",
                "code": "duplicate_decisions_collapsed",
                "message": "Collapsed equivalent duplicate decisions for one template target.",
                "slot_id": slot_id,
                "decision_count": len(decisions),
            },
        )
    if len(render_decisions) == 1:
        return _RepairResult(
            decision=render_decisions[0],
            diagnostic={
                "severity": "warning",
                "code": "duplicate_decisions_collapsed",
                "message": "Collapsed duplicate unresolved/fill decisions for one template target.",
                "slot_id": slot_id,
                "decision_count": len(decisions),
            },
        )
    return _RepairResult(
        decision=AgentDecision(
            slot_id=slot_id,
            decision_type="unresolved",
            source_refs=_combined_source_refs(decisions),
            reason="Agent returned conflicting fill decisions for this template target.",
            reason_code="duplicate_conflicting_decisions",
        ),
        diagnostic={
            "severity": "warning",
            "code": "duplicate_conflicting_decisions",
            "message": (
                "Agent returned conflicting fill decisions for one template target; "
                "converted the target to unresolved."
            ),
            "slot_id": slot_id,
            "decision_count": len(decisions),
        },
    )


def _equivalent_render_decisions(decisions: list[AgentDecision]) -> bool:
    if not decisions:
        return False
    first_key = _render_decision_key(decisions[0])
    return all(_render_decision_key(decision) == first_key for decision in decisions[1:])


def _render_decision_key(decision: AgentDecision) -> tuple[Any, ...]:
    return (
        decision.decision_type,
        decision.value,
        decision.asset_ref,
        decision.source_ref,
        tuple(decision.source_refs),
        _target_key(decision.target_ref),
    )


def _target_key(target_ref: str | dict[str, Any] | None) -> Any:
    if isinstance(target_ref, dict):
        return tuple(sorted((key, _target_key(value)) for key, value in target_ref.items()))
    if isinstance(target_ref, list):
        return tuple(_target_key(item) for item in target_ref)
    return target_ref


def _combined_source_refs(decisions: list[AgentDecision]) -> list[str]:
    refs: list[str] = []
    for decision in decisions:
        for source_ref in decision.source_refs:
            if source_ref not in refs:
                refs.append(source_ref)
    return refs


__all__ = ["repair_duplicate_decisions"]
