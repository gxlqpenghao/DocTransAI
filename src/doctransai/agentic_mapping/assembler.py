from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from doctransai.agentic_mapping.visual_targets import resolve_visual_target_mapping
from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import (
    ImagePlacement,
    OutputRef,
    PlanDiagnostic,
    RenderPlan,
    TargetRef,
    TemplateRef,
    TextFill,
)
from doctransai.models.source import ProvenanceRef
from doctransai.models.template import SlotAddress, TemplateModel, TemplateSlot


def assemble_render_plan_from_decisions(
    *,
    source_bundle_path: str,
    template_model: TemplateModel,
    output_path: str,
    decisions: list[Any],
    evidence_package: dict[str, Any] | None = None,
    diagnostics: list[Any] | None = None,
) -> RenderPlan:
    slots_by_id = {slot.slot_id: slot for slot in template_model.slots}
    text_fills: list[TextFill] = []
    image_placements: list[ImagePlacement] = []
    unresolved_slots: list[UnresolvedSlot] = []

    for decision in decisions:
        payload = _object_payload(decision)
        if not _is_accepted(payload):
            continue
        decision_kind = _decision_kind(payload)
        if decision_kind == "text_fill":
            text_fills.extend(_text_fills(payload, slots_by_id, template_model, decisions, evidence_package))
        elif decision_kind == "image_placement":
            image_placements.extend(_image_placements(payload, slots_by_id, template_model, evidence_package))
        elif decision_kind == "unresolved":
            unresolved_slots.append(_unresolved_slot(payload, slots_by_id))

    return RenderPlan(
        plan_id=f"agentic:{template_model.template_id}",
        source_bundle_path=str(source_bundle_path),
        template=TemplateRef(
            template_path=template_model.template_path,
            format_key=template_model.format_key,
            template_id=template_model.template_id,
        ),
        output=OutputRef(
            output_path=str(output_path),
            output_format=_output_format(str(output_path), template_model.format_key),
        ),
        text_fills=text_fills,
        image_placements=image_placements,
        unresolved_slots=unresolved_slots,
        diagnostics=[_plan_diagnostic(item) for item in diagnostics or []],
        created_at=_utc_now(),
    )


def _text_fills(
    payload: dict[str, Any],
    slots_by_id: dict[str, TemplateSlot],
    template_model: TemplateModel,
    decisions: list[Any],
    evidence_package: dict[str, Any] | None,
) -> list[TextFill]:
    slot_id = str(payload["slot_id"])
    slot = _slot_for_payload(payload, slots_by_id)
    value = str(payload.get("value", payload.get("generated_value", "")))
    base_target = _target_ref(payload, slots_by_id, template_model)
    base_fill = TextFill(
        slot_id=slot_id,
        target=base_target,
        value=value,
        provenance_refs=_provenance_refs(payload),
        value_type=str(payload.get("value_type") or "text"),
        confidence=float(payload.get("confidence", 1.0)),
        transform=_optional_string(payload.get("transform")),
    )
    if slot is None or not _slot_allows_repeat_text_expansion(slot):
        return [base_fill]

    lines = _repeat_text_lines(value)
    paired_image_payload = _paired_image_payload(slot, decisions)
    expected_count = len(_selected_asset_ids(paired_image_payload)) if paired_image_payload is not None else 0
    if expected_count > len(lines):
        lines.extend(
            _fallback_repeat_text_lines(
                selected_asset_ids=_selected_asset_ids(paired_image_payload)[len(lines):],
                evidence_package=evidence_package,
            )
        )
        lines = [line for line in lines if line]
    if len(lines) < 2:
        return [base_fill]

    fills: list[TextFill] = []
    for index, line in enumerate(lines):
        fills.append(
            TextFill(
                slot_id=f"{slot_id}@{index}",
                target=_repeat_instance_target(base_target, repeat_region_id=slot.repeat_region_id, instance_index=index),
                value=line,
                provenance_refs=_provenance_refs(payload),
                value_type=str(payload.get("value_type") or "text"),
                confidence=float(payload.get("confidence", 1.0)),
                transform=_optional_string(payload.get("transform")),
            )
        )
    return fills


def _image_placements(
    payload: dict[str, Any],
    slots_by_id: dict[str, TemplateSlot],
    template_model: TemplateModel,
    evidence_package: dict[str, Any] | None,
) -> list[ImagePlacement]:
    slot_id = str(payload["slot_id"])
    slot = _slot_for_payload(payload, slots_by_id)
    base_target = _target_ref(payload, slots_by_id, template_model)
    base_asset_id = str(payload.get("asset_id", payload.get("asset_ref", payload.get("image_asset_id", ""))))
    base_placement = ImagePlacement(
        slot_id=slot_id,
        asset_id=base_asset_id,
        source_ref=_optional_string(payload.get("source_ref")),
        target=base_target,
        provenance_refs=_provenance_refs(payload),
        sizing_policy=str(payload.get("sizing_policy") or "contain"),
        caption=_optional_string(payload.get("caption")),
        caption_slot_id=_optional_string(payload.get("caption_slot_id")),
        caption_target=_target_from_mapping(payload["caption_target"])
        if isinstance(payload.get("caption_target"), dict)
        else None,
    )
    if slot is None or not _slot_allows_multi_value_image(slot):
        return [base_placement]

    asset_ids = _selected_asset_ids(payload)
    if len(asset_ids) < 2:
        return [base_placement]

    placements: list[ImagePlacement] = []
    for index, asset_id in enumerate(asset_ids):
        placements.append(
            ImagePlacement(
                slot_id=f"{slot_id}@{index}",
                asset_id=asset_id,
                source_ref=_source_ref_for_asset(asset_id, payload=payload, evidence_package=evidence_package),
                target=(
                    _repeat_instance_target(base_target, repeat_region_id=slot.repeat_region_id, instance_index=index)
                    if slot.repeat_region_id is not None
                    else base_target
                ),
                provenance_refs=_asset_provenance_refs(asset_id, payload),
                sizing_policy=str(payload.get("sizing_policy") or "contain"),
                caption=_optional_string(payload.get("caption")),
                caption_slot_id=_optional_string(payload.get("caption_slot_id")),
                caption_target=_target_from_mapping(payload["caption_target"])
                if isinstance(payload.get("caption_target"), dict)
                else None,
            )
        )
    return placements


def _unresolved_slot(payload: dict[str, Any], slots_by_id: dict[str, TemplateSlot]) -> UnresolvedSlot:
    slot_id = str(payload["slot_id"])
    slot = slots_by_id.get(slot_id)
    return UnresolvedSlot(
        slot_id=slot_id,
        canonical_key=str(payload.get("canonical_key") or (slot.raw_name if slot else slot_id)),
        reason_code=str(payload.get("reason_code") or "agentic_unresolved"),
        message=str(payload.get("message") or payload.get("reason") or "Agent did not find supported source evidence."),
        candidate_ids=[str(item) for item in _list_value(payload.get("candidate_ids"))],
        provenance_refs=_provenance_refs(payload),
    )


def _target_ref(
    payload: dict[str, Any],
    slots_by_id: dict[str, TemplateSlot],
    template_model: TemplateModel,
) -> TargetRef:
    target_payload = payload.get("target_ref") or payload.get("target") or payload.get("visual_target")
    if isinstance(target_payload, TargetRef):
        return target_payload
    if isinstance(target_payload, dict):
        target_payload = resolve_visual_target_mapping(target_payload, template_model)
        target_object_key = _target_object_key(target_payload)
        if target_object_key is not None:
            slot_id = target_object_key.removeprefix("template_slot:")
            slot = slots_by_id.get(slot_id)
            if slot is not None:
                return _target_from_slot(slot)
        if "format_key" not in target_payload:
            slot = _slot_for_payload(payload, slots_by_id)
            if slot is not None:
                return _target_from_slot(slot)
        return _target_from_mapping(target_payload)

    slot = _slot_for_payload(payload, slots_by_id)
    if slot is None:
        raise ValueError(f"Decision for slot {payload['slot_id']} has no target_ref and no matching template slot.")
    return _target_from_slot(slot)


def _slot_for_payload(payload: dict[str, Any], slots_by_id: dict[str, TemplateSlot]) -> TemplateSlot | None:
    slot_id = str(payload["slot_id"])
    slot = slots_by_id.get(slot_id)
    if slot is not None:
        return slot
    repeat_base = _repeat_suffix_base_slot_id(slot_id)
    if repeat_base is not None:
        return slots_by_id.get(repeat_base)
    return None


def _repeat_suffix_base_slot_id(slot_id: str) -> str | None:
    marker = "-repeat-"
    if marker not in slot_id:
        return None
    base, repeat_index = slot_id.rsplit(marker, 1)
    if base and repeat_index.isdigit():
        return base
    return None


def _target_from_slot(slot: TemplateSlot) -> TargetRef:
    return _target_from_address(slot.address, notes=slot.raw_name)


def _target_from_address(address: SlotAddress, *, notes: str | None = None) -> TargetRef:
    return TargetRef(
        format_key=address.format_key,
        target_kind=address.address_kind,
        paragraph_index=address.paragraph_index,
        cell_paragraph_index=address.cell_paragraph_index,
        run_index=address.run_index,
        run_end_index=address.run_end_index,
        table_index=address.table_index,
        row_index=address.row_index,
        column_index=address.column_index,
        sheet_name=address.sheet_name,
        cell_ref=address.cell_ref,
        page_index=address.page_index,
        form_field_name=address.form_field_name,
        bbox=address.bbox,
        notes=notes,
    )


def _target_from_mapping(payload: dict[str, Any]) -> TargetRef:
    return TargetRef(
        format_key=str(payload["format_key"]),
        target_kind=str(payload.get("target_kind", payload.get("address_kind", "placeholder"))),
        paragraph_index=_optional_int(payload.get("paragraph_index")),
        cell_paragraph_index=_optional_int(payload.get("cell_paragraph_index")),
        run_index=_optional_int(payload.get("run_index")),
        run_end_index=_optional_int(payload.get("run_end_index")),
        table_index=_optional_int(payload.get("table_index")),
        row_index=_optional_int(payload.get("row_index")),
        column_index=_optional_int(payload.get("column_index")),
        sheet_name=_optional_string(payload.get("sheet_name")),
        cell_ref=_optional_string(payload.get("cell_ref")),
        page_index=_optional_int(payload.get("page_index")),
        form_field_name=_optional_string(payload.get("form_field_name")),
        bbox=[float(item) for item in payload["bbox"]] if isinstance(payload.get("bbox"), list) else None,
        notes=_optional_string(payload.get("notes") or payload.get("label_or_nearby_text") or payload.get("nearby_text")),
        repeat_region_id=_optional_string(payload.get("repeat_region_id")),
        instance_index=_optional_int(payload.get("instance_index")),
        allow_same_name_residual_fill=bool(payload.get("allow_same_name_residual_fill", False)),
    )


def _repeat_instance_target(target: TargetRef, *, repeat_region_id: str | None, instance_index: int) -> TargetRef:
    return TargetRef(
        format_key=target.format_key,
        target_kind=target.target_kind,
        paragraph_index=target.paragraph_index,
        cell_paragraph_index=target.cell_paragraph_index,
        run_index=target.run_index,
        run_end_index=target.run_end_index,
        table_index=target.table_index,
        row_index=target.row_index,
        column_index=target.column_index,
        sheet_name=target.sheet_name,
        cell_ref=target.cell_ref,
        page_index=target.page_index,
        form_field_name=target.form_field_name,
        bbox=list(target.bbox) if target.bbox is not None else None,
        notes=target.notes,
        repeat_region_id=repeat_region_id,
        instance_index=instance_index,
        allow_same_name_residual_fill=target.allow_same_name_residual_fill,
    )


def _target_object_key(payload: dict[str, Any]) -> str | None:
    for key in ("object_ref", "target_ref", "ref", "object_key"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _provenance_refs(payload: dict[str, Any]) -> list[ProvenanceRef]:
    raw_refs = payload.get("source_refs", payload.get("provenance_refs", []))
    return [_provenance_ref(item) for item in _list_value(raw_refs)]


def _asset_provenance_refs(asset_id: str, payload: dict[str, Any]) -> list[ProvenanceRef]:
    refs = _provenance_refs(payload)
    asset_object_id = f"image_asset:{asset_id}"
    if any(ref.object_id == asset_object_id for ref in refs):
        return refs
    refs.append(ProvenanceRef(source_kind="image_asset", asset_id=asset_id, object_id=asset_object_id))
    return refs


def _provenance_ref(item: Any) -> ProvenanceRef:
    if isinstance(item, ProvenanceRef):
        return item
    if isinstance(item, str):
        return ProvenanceRef(source_kind="agentic_ref", object_id=item)
    payload = _object_payload(item)
    return ProvenanceRef(
        source_kind=str(payload.get("source_kind", "agentic_ref")),
        document_id=_optional_string(payload.get("document_id")),
        evidence_id=_optional_string(payload.get("evidence_id")),
        asset_id=_optional_string(payload.get("asset_id")),
        object_id=_optional_string(payload.get("object_id")),
        locator=dict(payload.get("locator", {})),
        source_path=_optional_string(payload.get("source_path")),
    )


def _plan_diagnostic(item: Any) -> PlanDiagnostic:
    if isinstance(item, PlanDiagnostic):
        return item
    payload = _object_payload(item)
    return PlanDiagnostic(
        severity=str(payload.get("severity", "info")),
        code=str(payload.get("code", "agentic_mapping")),
        message=str(payload.get("message", "")),
        field=_optional_string(payload.get("field")),
    )


def _object_payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if is_dataclass(item):
        return asdict(item)
    payload: dict[str, Any] = {}
    for name in dir(item):
        if name.startswith("_"):
            continue
        value = getattr(item, name)
        if callable(value):
            continue
        payload[name] = value
    return payload


def _is_accepted(payload: dict[str, Any]) -> bool:
    if payload.get("accepted") is False:
        return False
    status = payload.get("status")
    return status not in {"rejected", "skipped", "ignored"}


def _decision_kind(payload: dict[str, Any]) -> str:
    return str(payload.get("decision_type", payload.get("decision", payload.get("kind", ""))))


def _output_format(output_path: str, default_format: str) -> str:
    suffix = Path(output_path).suffix.lstrip(".")
    return suffix or default_format


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _slot_allows_repeat_text_expansion(slot: TemplateSlot) -> bool:
    return slot.repeat_region_id is not None and slot.placement_constraints.get("multi_value_allowed") is True


def _slot_allows_multi_value_image(slot: TemplateSlot) -> bool:
    return slot.slot_kind == "image" and slot.placement_constraints.get("multi_value_allowed") is True


def _selected_asset_ids(payload: dict[str, Any] | None) -> list[str]:
    if payload is None:
        return []
    selected = [str(item) for item in _list_value(payload.get("candidate_ids")) if str(item)]
    if selected:
        return selected
    asset_id = payload.get("asset_id", payload.get("asset_ref", payload.get("image_asset_id")))
    if asset_id in (None, ""):
        return []
    return [str(asset_id)]


def _paired_image_payload(slot: TemplateSlot, decisions: list[Any]) -> dict[str, Any] | None:
    paired_image_slot_id = slot.placement_constraints.get("paired_image_slot_id")
    if not isinstance(paired_image_slot_id, str) or not paired_image_slot_id:
        return None
    for item in decisions:
        payload = _object_payload(item)
        if not _is_accepted(payload):
            continue
        if str(payload.get("slot_id")) == paired_image_slot_id and _decision_kind(payload) == "image_placement":
            return payload
    return None


def _repeat_text_lines(value: str) -> list[str]:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    raw_parts = normalized.split("\n") if "\n" in normalized else re.split(r"[；;]\s*", normalized)
    return [cleaned for part in raw_parts if (cleaned := _clean_repeat_text(part))]


def _clean_repeat_text(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^\s*(?:[-*•]+|\d+[、.)．]|[（(]\s*[一二三四五六七八九十\d]+\s*[）)]|[一二三四五六七八九十]+[、.．])\s*", "", text)
    return text.strip("：:；;，,。.、 ")


def _fallback_repeat_text_lines(*, selected_asset_ids: list[str], evidence_package: dict[str, Any] | None) -> list[str]:
    if evidence_package is None:
        return []
    lines: list[str] = []
    for asset_id in selected_asset_ids:
        line = _caption_like_text_for_asset(asset_id, evidence_package)
        if line:
            lines.append(line)
    return lines


def _caption_like_text_for_asset(asset_id: str, evidence_package: dict[str, Any]) -> str | None:
    structured = evidence_package.get("source", {}).get("structured", {})
    image_assets = structured.get("image_assets", [])
    if not isinstance(image_assets, list):
        return None
    asset = next(
        (
            item
            for item in image_assets
            if isinstance(item, dict) and item.get("asset_id") == asset_id
        ),
        None,
    )
    if asset is None:
        return None
    for key in ("nearby_text_after", "nearby_text_before"):
        value = asset.get(key)
        if isinstance(value, list):
            for item in value:
                cleaned = _clean_repeat_text(str(item))
                if cleaned:
                    return cleaned
        elif isinstance(value, str):
            cleaned = _clean_repeat_text(value)
            if cleaned:
                return cleaned
    return None


def _source_ref_for_asset(
    asset_id: str,
    *,
    payload: dict[str, Any],
    evidence_package: dict[str, Any] | None,
) -> str | None:
    payload_asset_id = str(payload.get("asset_id", payload.get("asset_ref", payload.get("image_asset_id", ""))))
    payload_source_ref = _optional_string(payload.get("source_ref"))
    if payload_source_ref and payload_asset_id == asset_id:
        return payload_source_ref
    if evidence_package is None:
        return payload_source_ref
    structured = evidence_package.get("source", {}).get("structured", {})
    object_index = structured.get("object_index", {})
    if isinstance(object_index, dict):
        entry = object_index.get(f"image_asset:{asset_id}")
        if isinstance(entry, dict):
            source_ref = entry.get("source_ref")
            if isinstance(source_ref, str) and source_ref:
                return source_ref
    image_assets = structured.get("image_assets", [])
    if isinstance(image_assets, list):
        for asset in image_assets:
            if isinstance(asset, dict) and asset.get("asset_id") == asset_id:
                source_ref = asset.get("source_ref")
                if isinstance(source_ref, str) and source_ref:
                    return source_ref
    return payload_source_ref
