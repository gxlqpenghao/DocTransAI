from __future__ import annotations

import re
from typing import Any


def build_template_targets(
    template_structured: dict[str, Any],
    *,
    visual_targets: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    covered_labels: list[str] = []

    for slot in _list_of_dicts(template_structured.get("slots")):
        target = _structured_target(slot)
        if target is None:
            continue
        targets.append(target)
        label = target.get("label")
        if isinstance(label, str) and label:
            covered_labels.append(label)

    seen_target_ids = {str(target["target_id"]) for target in targets}
    for visual_target in visual_targets or []:
        target = _visual_target(visual_target)
        if target is None:
            continue
        target_id = str(target["target_id"])
        if target_id in seen_target_ids:
            continue
        label = str(target.get("label") or "")
        if _covered_by_structured_slot(label, covered_labels):
            continue
        targets.append(target)
        seen_target_ids.add(target_id)

    return targets


def _structured_target(slot: dict[str, Any]) -> dict[str, Any] | None:
    slot_id = _text(slot.get("slot_id"))
    if slot_id is None:
        return None
    return _compact(
        {
            "target_id": slot_id,
            "origin": "structured",
            "label": _text(slot.get("raw_name")) or slot_id,
            "canonical_name": _text(slot.get("canonical_name")),
            "expected_content_type": _text(slot.get("slot_kind")) or "text",
            "target_kind": "structured_slot",
            "repeat_region_id": _text(slot.get("repeat_region_id")),
            "placement_constraints": dict(slot["placement_constraints"]) if isinstance(slot.get("placement_constraints"), dict) else None,
            "target_ref": {"object_ref": f"template_slot:{slot_id}"},
            "address": dict(slot["address"]) if isinstance(slot.get("address"), dict) else None,
        }
    )


def _visual_target(item: dict[str, Any]) -> dict[str, Any] | None:
    target_id = _text(item.get("target_id") or item.get("slot_id"))
    visual_target = item.get("visual_target") or item.get("target_ref") or item.get("target")
    if not isinstance(visual_target, dict):
        return None
    label = (
        _text(item.get("label_or_nearby_text"))
        or _text(item.get("label"))
        or _text(visual_target.get("label_or_nearby_text"))
        or _text(visual_target.get("nearby_text"))
        or target_id
    )
    if target_id is None or label is None:
        return None
    return _compact(
        {
            "target_id": target_id,
            "origin": "visual",
            "label": label,
            "expected_content_type": _text(item.get("expected_content_type")) or "text",
            "target_kind": str(visual_target.get("target_kind") or "visual_text_anchor"),
            "target_ref": dict(visual_target),
            "approx_location": _text(item.get("approx_location") or visual_target.get("approx_location")),
            "visual_reason": _text(item.get("visual_reason") or item.get("reason")),
        }
    )


def _covered_by_structured_slot(visual_label: str, structured_labels: list[str]) -> bool:
    normalized_visual = _normalize_label(visual_label)
    if not normalized_visual:
        return False
    return any(
        normalized_slot
        and (
            normalized_visual == normalized_slot
            or f"{{{normalized_slot}}}" in normalized_visual
            or _labels_overlap(normalized_visual, normalized_slot)
        )
        for normalized_slot in (_normalize_label(label) for label in structured_labels)
    )


def _labels_overlap(normalized_visual: str, normalized_slot: str) -> bool:
    shorter_length = min(len(normalized_visual), len(normalized_slot))
    if shorter_length < 4:
        return False
    return normalized_visual in normalized_slot or normalized_slot in normalized_visual


def _normalize_label(value: str) -> str:
    normalized = (
        value.strip()
        .replace(" ", "")
        .replace("\t", "")
        .replace("\n", "")
        .replace("：", ":")
    )
    return _strip_placeholder_x_markers(normalized)


def _strip_placeholder_x_markers(value: str) -> str:
    if not any("\u4e00" <= character <= "\u9fff" for character in value):
        return value
    return re.sub(r"X+$", "", re.sub(r"^X+", "", value))


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, {}, [])
    }


__all__ = ["build_template_targets"]
