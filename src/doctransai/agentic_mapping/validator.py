from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from doctransai.agentic_mapping.decisions import AgentDecision


@dataclass(slots=True)
class ValidationResult:
    accepted_decisions: list[AgentDecision] = field(default_factory=list)
    rejected_decisions: list[AgentDecision] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def validate_agent_decisions(
    decisions: list[AgentDecision],
    evidence_package: dict[str, Any],
) -> ValidationResult:
    source_index = _object_index(evidence_package, "source")
    template_index = _object_index(evidence_package, "template")
    result = ValidationResult()

    for decision in decisions:
        diagnostics = _validate_decision(decision, source_index, template_index)
        if diagnostics:
            result.rejected_decisions.append(decision)
            result.diagnostics.extend(diagnostics)
        else:
            result.accepted_decisions.append(decision)

    return result


def _validate_decision(
    decision: AgentDecision,
    source_index: dict[str, Any],
    template_index: dict[str, Any],
) -> list[dict[str, Any]]:
    if decision.decision_type == "unresolved":
        return _validate_unresolved(decision)

    diagnostics: list[dict[str, Any]] = []
    diagnostics.extend(_validate_source_refs(decision, source_index))
    diagnostics.extend(_validate_target_ref(decision, template_index))

    if decision.decision_type == "image_placement":
        diagnostics.extend(_validate_image_asset(decision, source_index))

    return diagnostics


def _validate_unresolved(decision: AgentDecision) -> list[dict[str, Any]]:
    if decision.reason:
        return []
    return [
        _diagnostic(
            "error",
            "missing_reason",
            "Unresolved decisions must include a reason.",
            decision,
        )
    ]


def _validate_source_refs(
    decision: AgentDecision,
    source_index: dict[str, Any],
) -> list[dict[str, Any]]:
    if not decision.source_refs:
        return [
            _diagnostic(
                "error",
                "missing_source_refs",
                f"{decision.decision_type} decisions must include at least one source ref.",
                decision,
            )
        ]

    diagnostics: list[dict[str, Any]] = []
    for source_ref in decision.source_refs:
        if source_ref not in source_index:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "source_ref_not_found",
                    f"Source ref '{source_ref}' does not exist in source structured object_index.",
                    decision,
                    source_ref=source_ref,
                )
            )
    return diagnostics


def _validate_target_ref(
    decision: AgentDecision,
    template_index: dict[str, Any],
) -> list[dict[str, Any]]:
    target_key = _target_object_key(decision.target_ref)
    if not target_key:
        return [
            _diagnostic(
                "error",
                "missing_target_ref",
                f"{decision.decision_type} decisions must include a target_ref.",
                decision,
            )
        ]
    if target_key not in template_index:
        return [
            _diagnostic(
                "error",
                "target_ref_not_found",
                f"Target ref '{target_key}' does not exist in template structured object_index.",
                decision,
                target_ref=target_key,
            )
        ]
    return []


def _validate_image_asset(
    decision: AgentDecision,
    source_index: dict[str, Any],
) -> list[dict[str, Any]]:
    if not decision.asset_ref:
        return [
            _diagnostic(
                "error",
                "missing_asset_ref",
                "image_placement decisions must include an asset_ref.",
                decision,
            )
        ]

    asset_key = (
        decision.asset_ref
        if decision.asset_ref.startswith("image_asset:")
        else f"image_asset:{decision.asset_ref}"
    )
    if asset_key not in source_index:
        return [
            _diagnostic(
                "error",
                "image_asset_not_found",
                f"Image asset '{decision.asset_ref}' does not exist in source structured object_index.",
                decision,
                asset_ref=decision.asset_ref,
            )
        ]
    return []


def _object_index(evidence_package: dict[str, Any], side: str) -> dict[str, Any]:
    structured = evidence_package.get(side, {}).get("structured", {})
    object_index = structured.get("object_index", {})
    if isinstance(object_index, dict):
        return object_index
    return {}


def _target_object_key(target_ref: str | dict[str, Any] | None) -> str | None:
    if isinstance(target_ref, str):
        return target_ref
    if not isinstance(target_ref, dict):
        return None

    for key in ("object_ref", "target_ref", "ref"):
        value = target_ref.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _diagnostic(
    severity: str,
    code: str,
    message: str,
    decision: AgentDecision,
    **extra: Any,
) -> dict[str, Any]:
    diagnostic = {
        "severity": severity,
        "code": code,
        "message": message,
        "slot_id": decision.slot_id,
    }
    diagnostic.update(extra)
    return diagnostic


__all__ = ["ValidationResult", "validate_agent_decisions"]
