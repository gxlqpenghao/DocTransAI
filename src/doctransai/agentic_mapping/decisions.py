from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
from typing import Any


VALID_DECISION_TYPES = frozenset({"text_fill", "image_placement", "unresolved"})


@dataclass(slots=True)
class AgentDecision:
    slot_id: str
    decision_type: str
    value: str | None = None
    asset_ref: str | None = None
    source_ref: str | None = None
    source_refs: list[str] = field(default_factory=list)
    target_ref: str | dict[str, Any] | None = None
    confidence: float = 1.0
    reason: str | None = None
    reason_code: str | None = None
    candidate_ids: list[str] = field(default_factory=list)
    value_type: str | None = None
    transform: str | None = None
    sizing_policy: str | None = None
    caption: str | None = None
    caption_slot_id: str | None = None
    caption_target: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.slot_id, str) or not self.slot_id:
            raise ValueError("AgentDecision.slot_id must be a non-empty string.")
        if self.decision_type not in VALID_DECISION_TYPES:
            valid_types = ", ".join(sorted(VALID_DECISION_TYPES))
            raise ValueError(f"AgentDecision.decision_type must be one of: {valid_types}.")
        self.source_refs = _normalize_source_refs(self.source_refs)
        self.candidate_ids = _normalize_string_list(self.candidate_ids, field_name="candidate_ids")
        self.confidence = _normalize_confidence(self.confidence)
        if self.target_ref is not None and not isinstance(self.target_ref, (str, dict)):
            raise ValueError("AgentDecision.target_ref must be a string, a dict, or None.")
        if self.caption_target is not None and not isinstance(self.caption_target, dict):
            raise ValueError("AgentDecision.caption_target must be a dict or None.")


def parse_agent_decisions(payload: Any) -> list[AgentDecision]:
    """Parse an agent decision payload without doing evidence validation."""

    decision_items = _extract_decision_items(payload)
    decisions: list[AgentDecision] = []
    for index, item in enumerate(decision_items):
        if not isinstance(item, Mapping):
            raise ValueError(f"Decision at index {index} must be an object.")
        decision_type = _decision_type(item, index)
        slot_id = _required_string(item, "slot_id", index)
        decisions.append(
            AgentDecision(
                slot_id=slot_id,
                decision_type=decision_type,
                value=_optional_text_value(item, "value", index),
                asset_ref=_optional_string(item, "asset_ref", index)
                or _optional_string(item, "asset_id", index)
                or _optional_string(item, "image_asset_id", index),
                source_ref=_optional_string(item, "source_ref", index),
                source_refs=_optional_source_refs(_source_refs_payload(item, decision_type), index),
                target_ref=_target_ref_payload(item, slot_id=slot_id),
                confidence=item.get("confidence", 1.0),
                reason=_optional_string(item, "reason", index)
                or _optional_string(item, "message", index),
                reason_code=_optional_string(item, "reason_code", index),
                candidate_ids=_optional_string_list(item.get("candidate_ids"), index, field_name="candidate_ids"),
                value_type=_optional_string(item, "value_type", index),
                transform=_optional_string(item, "transform", index),
                sizing_policy=_optional_string(item, "sizing_policy", index),
                caption=_optional_string(item, "caption", index),
                caption_slot_id=_optional_string(item, "caption_slot_id", index),
                caption_target=_optional_mapping(item, "caption_target", index),
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


def _optional_text_value(item: Mapping[str, Any], key: str, index: int) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        parts = []
        for part in value:
            if not isinstance(part, str):
                raise ValueError(f"Decision at index {index} field '{key}' must contain only strings when present as a list.")
            stripped = part.strip()
            if stripped:
                parts.append(stripped)
        return "\n".join(parts)
    raise ValueError(f"Decision at index {index} field '{key}' must be a string when present.")


def _optional_mapping(item: Mapping[str, Any], key: str, index: int) -> dict[str, Any] | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"Decision at index {index} field '{key}' must be an object when present.")
    return dict(value)


def _source_refs_payload(item: Mapping[str, Any], decision_type: str) -> Any:
    if "source_refs" in item:
        return item["source_refs"]
    if "provenance_refs" in item:
        return item["provenance_refs"]
    if decision_type != "image_placement":
        return item.get("source_ref")
    return None


def _target_ref_payload(item: Mapping[str, Any], *, slot_id: str) -> Any:
    for key in ("target_ref", "target", "visual_target"):
        value = item.get(key)
        if value is not None:
            return value
    if slot_id.startswith("visual-target-"):
        label = slot_id.removeprefix("visual-target-").strip()
        if label:
            return {
                "format_key": "docx",
                "target_kind": "visual_text_anchor",
                "label_or_nearby_text": label,
            }
    return None


def _optional_source_refs(value: Any, index: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _normalize_source_refs([value])
    if isinstance(value, bytes) or not isinstance(value, Sequence):
        raise ValueError(f"Decision at index {index} field 'source_refs' must be a list of refs.")
    return _normalize_source_refs(value)


def _optional_string_list(value: Any, index: int, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes) or isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"Decision at index {index} field '{field_name}' must be a list of strings.")
    return _normalize_string_list(value, field_name=field_name)


def _normalize_string_list(value: Sequence[Any], *, field_name: str) -> list[str]:
    items = [item for item in value]
    if any(not isinstance(item, str) or not item for item in items):
        raise ValueError(f"AgentDecision.{field_name} must contain only non-empty strings.")
    return items


def _normalize_source_refs(value: Sequence[Any]) -> list[str]:
    refs = [_normalize_source_ref(ref) for ref in value]
    if any(not ref for ref in refs):
        raise ValueError("AgentDecision.source_refs must contain only non-empty refs.")
    return refs


def _normalize_source_ref(ref: Any) -> str:
    if isinstance(ref, str):
        return ref
    if not isinstance(ref, Mapping):
        raise ValueError("AgentDecision.source_refs must contain strings or objects.")
    for key in ("object_ref", "source_ref", "ref", "object_key"):
        value = ref.get(key)
        if isinstance(value, str) and value:
            return value
    object_type = ref.get("object_type") or ref.get("object_kind") or ref.get("source_kind")
    object_id = ref.get("object_id")
    if isinstance(object_type, str) and isinstance(object_id, str) and object_type and object_id:
        return f"{object_type}:{object_id}"
    record_id = ref.get("record_id")
    if isinstance(record_id, str) and record_id:
        return f"record:{record_id}"
    asset_id = ref.get("asset_id")
    if isinstance(asset_id, str) and asset_id:
        return f"image_asset:{asset_id}"
    return "unresolved_source_ref:" + json.dumps(ref, ensure_ascii=False, sort_keys=True)


def _normalize_confidence(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("AgentDecision.confidence must be a number.")
    if isinstance(value, str):
        normalized = value.strip().casefold()
        confidence_label = {
            "very high": 0.95,
            "high": 0.9,
            "medium": 0.5,
            "low": 0.2,
            "高": 0.9,
            "中": 0.5,
            "低": 0.2,
        }.get(normalized)
        if confidence_label is not None:
            return confidence_label
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("AgentDecision.confidence must be a number.") from exc
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError("AgentDecision.confidence must be between 0.0 and 1.0.")
    return confidence


__all__ = ["AgentDecision", "VALID_DECISION_TYPES", "parse_agent_decisions"]
