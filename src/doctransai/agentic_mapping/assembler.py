from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
            text_fills.append(_text_fill(payload, slots_by_id))
        elif decision_kind == "image_placement":
            image_placements.append(_image_placement(payload, slots_by_id))
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


def _text_fill(payload: dict[str, Any], slots_by_id: dict[str, TemplateSlot]) -> TextFill:
    slot_id = str(payload["slot_id"])
    return TextFill(
        slot_id=slot_id,
        target=_target_ref(payload, slots_by_id),
        value=str(payload.get("value", payload.get("generated_value", ""))),
        provenance_refs=_provenance_refs(payload),
        value_type=str(payload.get("value_type", "text")),
        confidence=float(payload.get("confidence", 1.0)),
        transform=_optional_string(payload.get("transform")),
    )


def _image_placement(payload: dict[str, Any], slots_by_id: dict[str, TemplateSlot]) -> ImagePlacement:
    slot_id = str(payload["slot_id"])
    return ImagePlacement(
        slot_id=slot_id,
        asset_id=str(payload.get("asset_id", payload.get("asset_ref", payload.get("image_asset_id", "")))),
        source_ref=_optional_string(payload.get("source_ref")),
        target=_target_ref(payload, slots_by_id),
        provenance_refs=_provenance_refs(payload),
        sizing_policy=str(payload.get("sizing_policy", "contain")),
        caption=_optional_string(payload.get("caption")),
        caption_slot_id=_optional_string(payload.get("caption_slot_id")),
        caption_target=_target_from_mapping(payload["caption_target"])
        if isinstance(payload.get("caption_target"), dict)
        else None,
    )


def _unresolved_slot(payload: dict[str, Any], slots_by_id: dict[str, TemplateSlot]) -> UnresolvedSlot:
    slot_id = str(payload["slot_id"])
    slot = slots_by_id.get(slot_id)
    return UnresolvedSlot(
        slot_id=slot_id,
        canonical_key=str(payload.get("canonical_key") or (slot.canonical_name if slot else slot_id)),
        reason_code=str(payload.get("reason_code", "agentic_unresolved")),
        message=str(payload.get("message") or payload.get("reason") or "Agent did not find supported source evidence."),
        candidate_ids=[str(item) for item in _list_value(payload.get("candidate_ids"))],
        provenance_refs=_provenance_refs(payload),
    )


def _target_ref(payload: dict[str, Any], slots_by_id: dict[str, TemplateSlot]) -> TargetRef:
    target_payload = payload.get("target_ref") or payload.get("target")
    if isinstance(target_payload, TargetRef):
        return target_payload
    if isinstance(target_payload, dict):
        return _target_from_mapping(target_payload)

    slot = slots_by_id.get(str(payload["slot_id"]))
    if slot is None:
        raise ValueError(f"Decision for slot {payload['slot_id']} has no target_ref and no matching template slot.")
    return _target_from_address(slot.address)


def _target_from_address(address: SlotAddress) -> TargetRef:
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
        notes=_optional_string(payload.get("notes")),
        repeat_region_id=_optional_string(payload.get("repeat_region_id")),
        instance_index=_optional_int(payload.get("instance_index")),
        allow_same_name_residual_fill=bool(payload.get("allow_same_name_residual_fill", False)),
    )


def _provenance_refs(payload: dict[str, Any]) -> list[ProvenanceRef]:
    raw_refs = payload.get("source_refs", payload.get("provenance_refs", []))
    return [_provenance_ref(item) for item in _list_value(raw_refs)]


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
