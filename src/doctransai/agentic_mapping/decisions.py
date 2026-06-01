from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


VALID_DECISION_TYPES = frozenset({"text_fill", "image_placement", "unresolved"})


@dataclass(slots=True)
class AgentDecision:
    slot_id: str
    decision_type: str
    value: str | None = None
    asset_ref: str | None = None
    source_refs: list[str] = field(default_factory=list)
    target_ref: str | dict[str, Any] | None = None
    confidence: float = 1.0
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.slot_id, str) or not self.slot_id:
            raise ValueError("AgentDecision.slot_id must be a non-empty string.")
        if self.decision_type not in VALID_DECISION_TYPES:
            valid_types = ", ".join(sorted(VALID_DECISION_TYPES))
            raise ValueError(f"AgentDecision.decision_type must be one of: {valid_types}.")
        self.source_refs = _normalize_source_refs(self.source_refs)
        self.confidence = _normalize_confidence(self.confidence)
        if self.target_ref is not None and not isinstance(self.target_ref, (str, dict)):
            raise ValueError("AgentDecision.target_ref must be a string, a dict, or None.")


def parse_agent_decisions(payload: Any) -> list[AgentDecision]:
    """Parse an agent decision payload without doing evidence validation."""

    decision_items = _extract_decision_items(payload)
    decisions: list[AgentDecision] = []
    for index, item in enumerate(decision_items):
        if not isinstance(item, Mapping):
            raise ValueError(f"Decision at index {index} must be an object.")
        decisions.append(
            AgentDecision(
                slot_id=_required_string(item, "slot_id", index),
                decision_type=_decision_type(item, index),
                value=_optional_string(item, "value", index),
                asset_ref=_optional_string(item, "asset_ref", index)
                or _optional_string(item, "asset_id", index)
                or _optional_string(item, "image_asset_id", index),
                source_refs=_optional_source_refs(item.get("source_refs"), index),
                target_ref=item.get("target_ref"),
                confidence=item.get("confidence", 1.0),
                reason=_optional_string(item, "reason", index)
                or _optional_string(item, "message", index),
            )
        )
    return decisions


def _extract_decision_items(payload: Any) -> Sequence[Any]:
    if isinstance(payload, Mapping):
        if "decisions" not in payload:
            raise ValueError("Decision payload object must contain a 'decisions' field.")
        decisions = payload["decisions"]
    else:
        decisions = payload
    if isinstance(decisions, (str, bytes)) or not isinstance(decisions, Sequence):
        raise ValueError("Decision payload must be a list or an object containing a decisions list.")
    return decisions


def _required_string(item: Mapping[str, Any], key: str, index: int) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Decision at index {index} must contain non-empty string field '{key}'.")
    return value


def _decision_type(item: Mapping[str, Any], index: int) -> str:
    value = item.get("decision_type", item.get("decision"))
    if not isinstance(value, str) or not value:
        raise ValueError(f"Decision at index {index} must contain non-empty string field 'decision_type'.")
    return value


def _optional_string(item: Mapping[str, Any], key: str, index: int) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Decision at index {index} field '{key}' must be a string when present.")
    return value


def _optional_source_refs(value: Any, index: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"Decision at index {index} field 'source_refs' must be a list of strings.")
    return _normalize_source_refs(value)


def _normalize_source_refs(value: Sequence[str]) -> list[str]:
    refs = list(value)
    if any(not isinstance(ref, str) or not ref for ref in refs):
        raise ValueError("AgentDecision.source_refs must contain only non-empty strings.")
    return refs


def _normalize_confidence(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("AgentDecision.confidence must be a number.")
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("AgentDecision.confidence must be a number.") from exc
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError("AgentDecision.confidence must be between 0.0 and 1.0.")
    return confidence


__all__ = ["AgentDecision", "VALID_DECISION_TYPES", "parse_agent_decisions"]
