from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from doctransai.mapping.candidate_builder import build_slot_candidate_packets
from doctransai.mapping.cluster_planner import build_source_cluster_plan
from doctransai.mapping.consistency import apply_cross_slot_consistency_checks
from doctransai.mapping.render_plan_assembler import assemble_slot_actions, target_for_repeat_slot
from doctransai.mapping.slot_decisions import resolve_slot_candidate_packets
from doctransai.mapping.structural_candidates import build_label_echo_filtered_candidates_for_slot
from doctransai.mapping.visual_candidates import (
    build_visual_content_units_for_primary_record,
)
from doctransai.models.mapping import FieldCandidate, UnresolvedSlot
from doctransai.models.render_plan import (
    ImagePlacement,
    OutputRef,
    PlanDiagnostic,
    RenderPlan,
    RowPlan,
    TemplateRef,
    TextFill,
    render_plan_to_dict,
)
from doctransai.models.source import ProvenanceRef, SourceImageAsset, SourceModel, SourceRecord
from doctransai.models.source_instance import SourceInstanceIndex
from doctransai.models.template import TemplateModel, TemplateSlot
from doctransai.source_model.instances import build_source_instance_index


def build_render_plan(
    *,
    template_model: TemplateModel,
    source_model: SourceModel,
    source_bundle_path: str,
    output_path: str,
    primary_record_id: str | None = None,
    source_instance_id: str | None = None,
    plan_id: str | None = None,
    created_at: str | None = None,
    confidence_floor: float = 0.75,
    enable_repeat_region_autofill: bool = True,
) -> dict[str, Any]:
    source_instance_index = build_source_instance_index(source_model)
    primary_record, selection_diagnostics = _select_primary_record(
        source_model,
        primary_record_id,
        source_instance_id=source_instance_id,
        source_instance_index=source_instance_index,
    )

    text_fills: list[TextFill] = []
    image_placements: list[ImagePlacement] = []
    unresolved_slots: list[UnresolvedSlot] = []
    resolved_slot_ids: list[str] = []
    repeat_region_text_fills: list[TextFill] = []
    repeat_region_image_placements: list[ImagePlacement] = []
    repeat_region_slot_ids: set[str] = set()
    if enable_repeat_region_autofill:
        repeat_region_text_fills, repeat_region_image_placements, repeat_region_slot_ids = _repeat_region_actions(
            template_model=template_model,
            source_model=source_model,
            primary_record=primary_record,
        )
    text_fills.extend(repeat_region_text_fills)
    image_placements.extend(repeat_region_image_placements)
    resolved_slot_ids.extend([fill.slot_id for fill in repeat_region_text_fills])
    resolved_slot_ids.extend([placement.slot_id for placement in repeat_region_image_placements])

    candidate_packets = build_slot_candidate_packets(
        template_model=template_model,
        source_model=source_model,
        primary_record=primary_record,
        source_bundle_path=source_bundle_path,
        skip_slot_ids=repeat_region_slot_ids,
    )
    label_echo_filtered_by_slot = {
        packet.slot.slot_id: build_label_echo_filtered_candidates_for_slot(
            slot=packet.slot,
            primary_record=primary_record,
        )
        for packet in candidate_packets
        if packet.slot_kind == "text" and not packet.candidates
    }
    slot_decisions = resolve_slot_candidate_packets(
        candidate_packets,
        confidence_floor=confidence_floor,
    )
    slot_actions = assemble_slot_actions(slot_decisions)
    _mark_label_echo_filtered_unresolved_slots(
        slot_actions.unresolved_slots,
        label_echo_filtered_by_slot=label_echo_filtered_by_slot,
    )
    text_fills.extend(slot_actions.text_fills)
    image_placements.extend(slot_actions.image_placements)
    unresolved_slots.extend(slot_actions.unresolved_slots)
    resolved_slot_ids.extend(slot_actions.resolved_slot_ids)

    consistency_result = apply_cross_slot_consistency_checks(
        template_model=template_model,
        primary_record=primary_record,
        text_fills=text_fills,
        image_placements=image_placements,
        unresolved_slots=unresolved_slots,
        resolved_slot_ids=resolved_slot_ids,
        source_instance_index=source_instance_index,
    )
    text_fills = consistency_result.text_fills
    image_placements = consistency_result.image_placements
    unresolved_slots = consistency_result.unresolved_slots
    resolved_slot_ids = consistency_result.resolved_slot_ids

    diagnostics = [
        PlanDiagnostic(
            severity=diagnostic.severity,
            code=diagnostic.code,
            message=diagnostic.message,
            field=diagnostic.field,
        )
        for diagnostic in template_model.diagnostics
    ]
    diagnostics.extend(selection_diagnostics)
    diagnostics.extend(
        _repeat_region_cluster_hint_diagnostics(
            template_model=template_model,
            source_model=source_model,
        )
    )
    diagnostics.extend(
        PlanDiagnostic(
            severity="warning",
            code=slot.reason_code,
            message=slot.message,
            field=slot.canonical_key,
        )
        for slot in unresolved_slots
    )

    plan = RenderPlan(
        plan_id=plan_id or _default_plan_id(template_model, primary_record),
        source_bundle_path=source_bundle_path,
        template=TemplateRef(
            template_path=template_model.template_path,
            format_key=template_model.format_key,
            template_id=template_model.template_id,
        ),
        output=OutputRef(
            output_path=output_path,
            output_format=_output_format(output_path, template_model.format_key),
        ),
        text_fills=text_fills,
        image_placements=image_placements,
        unresolved_slots=unresolved_slots,
        diagnostics=diagnostics,
        created_at=created_at or _utc_now(),
        record_plans=[
            RowPlan(
                record_id=primary_record.record_id,
                repeat_region_id=None,
                slot_ids=resolved_slot_ids,
            )
        ],
    )
    return render_plan_to_dict(plan)


def _repeat_region_cluster_hint_diagnostics(
    *,
    template_model: TemplateModel,
    source_model: SourceModel,
) -> list[PlanDiagnostic]:
    if not template_model.repeat_regions:
        return []
    cluster_plan = build_source_cluster_plan(source_model=source_model, template_model=template_model)
    diagnostics: list[PlanDiagnostic] = []
    for region_plan in cluster_plan.repeat_region_plans:
        for cluster_id in region_plan.candidate_cluster_ids:
            coverage = region_plan.coverage_by_cluster_id.get(cluster_id, {})
            diagnostics.append(
                PlanDiagnostic(
                    severity="info",
                    code="repeat_region_cluster_hint",
                    message=(
                        f"Repeat region {region_plan.region_id} has candidate cluster {cluster_id} "
                        f"with instance_count={coverage.get('instance_count', 0)}, "
                        f"record_count={coverage.get('record_count', 0)}, "
                        f"asset_count={coverage.get('asset_count', 0)}."
                    ),
                    field=region_plan.region_id,
                )
            )
    return diagnostics


def _repeat_region_actions(
    *,
    template_model: TemplateModel,
    source_model: SourceModel,
    primary_record: SourceRecord,
) -> tuple[list[TextFill], list[ImagePlacement], set[str]]:
    if template_model.format_key != "docx":
        return [], [], set()

    slots_by_region: dict[str, list[TemplateSlot]] = {}
    for slot in template_model.slots:
        if slot.repeat_region_id is None:
            continue
        if slot.address.address_kind != "paragraph" or slot.address.paragraph_index is None:
            continue
        slots_by_region.setdefault(slot.repeat_region_id, []).append(slot)

    text_fills: list[TextFill] = []
    image_placements: list[ImagePlacement] = []
    reserved_slot_ids: set[str] = set()
    for region in template_model.repeat_regions:
        if region.region_kind != "docx_paragraph_media_region":
            continue

        region_slots = sorted(
            slots_by_region.get(region.region_id, []),
            key=lambda slot: slot.address.paragraph_index if slot.address.paragraph_index is not None else -1,
        )
        image_slots = [slot for slot in region_slots if slot.slot_kind == "image"]
        text_slots = [slot for slot in region_slots if slot.slot_kind == "text"]
        if len(image_slots) != 1 or len(text_slots) > 1:
            continue

        image_slot = image_slots[0]
        description_slot = text_slots[0] if text_slots else None
        if description_slot is None:
            continue
        visual_units = build_visual_content_units_for_primary_record(source_model=source_model, primary_record=primary_record)
        visual_units = [unit for unit in visual_units if unit.description_text]
        if not visual_units:
            continue

        reserved_slot_ids.update(slot.slot_id for slot in region_slots)
        for instance_index, unit in enumerate(visual_units):
            image_placements.append(
                ImagePlacement(
                    slot_id=f"{image_slot.slot_id}@{instance_index}",
                    asset_id=unit.asset.asset_id,
                    source_ref=unit.asset.source_ref,
                    target=target_for_repeat_slot(
                        image_slot.address,
                        placeholder_name=image_slot.raw_name,
                        repeat_region_id=region.region_id,
                        instance_index=instance_index,
                    ),
                    provenance_refs=[_asset_provenance(unit.asset, primary_record)],
                )
            )
            if unit.description_text is not None:
                text_fills.append(
                    TextFill(
                        slot_id=f"{description_slot.slot_id}@{instance_index}",
                        target=target_for_repeat_slot(
                            description_slot.address,
                            placeholder_name=description_slot.raw_name,
                            repeat_region_id=region.region_id,
                            instance_index=instance_index,
                        ),
                        value=unit.description_text,
                        provenance_refs=[_asset_provenance(unit.asset, primary_record)],
                        confidence=unit.confidence,
                        transform=f"repeat_region_{unit.relation}",
                    )
                )

    return text_fills, image_placements, reserved_slot_ids


def _select_primary_record(
    source_model: SourceModel,
    primary_record_id: str | None,
    *,
    source_instance_id: str | None = None,
    source_instance_index: SourceInstanceIndex | None = None,
) -> tuple[SourceRecord, list[PlanDiagnostic]]:
    if primary_record_id is not None:
        for record in source_model.records:
            if record.record_id == primary_record_id:
                return record, []
        raise ValueError(f"Primary record not found: {primary_record_id}")

    if source_instance_id is not None:
        index = source_instance_index or build_source_instance_index(source_model)
        instance = index.instances_by_id.get(source_instance_id)
        if instance is None:
            raise ValueError(f"Source instance not found: {source_instance_id}")
        records_by_id = {record.record_id: record for record in source_model.records}
        instance_records = [records_by_id[record_id] for record_id in instance.record_ids if record_id in records_by_id]
        if not instance_records:
            raise ValueError(f"No source record is available for source instance: {source_instance_id}")
        return _select_primary_record_from_candidates(
            instance_records,
            header_fallback_code="source_instance_header_like_fallback",
            header_fallback_message=(
                "No non-header-like source record was available in the selected source instance; "
                "selected the first instance record with values."
            ),
        )

    return _select_primary_record_from_candidates(
        source_model.records,
        header_fallback_code="primary_record_header_like_fallback",
        header_fallback_message=(
            "No non-header-like source record was available; selected the first record with values."
        ),
    )


def _select_primary_record_from_candidates(
    records: list[SourceRecord],
    *,
    header_fallback_code: str,
    header_fallback_message: str,
) -> tuple[SourceRecord, list[PlanDiagnostic]]:
    for record in records:
        if _row_index(record) is not None and record.values and not _is_header_like_record(record):
            return record, []

    for record in records:
        if record.values and not _is_header_like_record(record):
            return record, []

    for record in records:
        if record.values:
            return record, [
                PlanDiagnostic(
                    severity="warning",
                    code=header_fallback_code,
                    message=header_fallback_message,
                    field=record.record_id,
                )
            ]

    raise ValueError("No source record is available for planning.")


def _mark_label_echo_filtered_unresolved_slots(
    unresolved_slots: list[UnresolvedSlot],
    *,
    label_echo_filtered_by_slot: dict[str, list[FieldCandidate]],
) -> None:
    for slot in unresolved_slots:
        if slot.reason_code != "missing_value" or slot.candidate_ids:
            continue
        filtered_candidates = label_echo_filtered_by_slot.get(slot.slot_id, [])
        if not filtered_candidates:
            continue
        slot.reason_code = "label_echo_filtered"
        slot.message = (
            f"Only label-echo candidates were found for {slot.canonical_key}; "
            "they were withheld to avoid copying a label as content."
        )
        slot.candidate_ids = [candidate.candidate_id for candidate in filtered_candidates]
        slot.provenance_refs = _candidate_provenance(filtered_candidates)


def _candidate_provenance(candidates: list[FieldCandidate]) -> list[ProvenanceRef]:
    provenance: list[ProvenanceRef] = []
    seen: set[tuple[str | None, str | None, str | None, str | None]] = set()
    for candidate in candidates:
        for ref in candidate.provenance_refs:
            key = (ref.source_kind, ref.document_id, ref.object_id, ref.source_path)
            if key in seen:
                continue
            seen.add(key)
            provenance.append(ref)
    return provenance


def _asset_provenance(asset: SourceImageAsset, primary_record: SourceRecord) -> ProvenanceRef:
    return ProvenanceRef(
        source_kind="asset",
        document_id=_string_value(asset.raw.get("document_id")) or primary_record.document_id,
        asset_id=asset.asset_id,
        object_id=asset.asset_id,
        locator={
            "sheet_name": asset.sheet_name,
            "cell_anchor": asset.cell_anchor,
            "row_index": asset.row_index,
            "column_index": asset.column_index,
        },
        source_path=_string_value(asset.raw.get("source_path")) or primary_record.source_path,
    )


def _row_index(record: SourceRecord) -> int | None:
    value = record.locator.get("row_index")
    return value if isinstance(value, int) else None


def _is_header_like_record(record: SourceRecord) -> bool:
    if bool(record.raw.get("is_header")):
        return True

    comparable_count = 0
    echo_count = 0
    for value in record.values:
        label = value.raw_label or value.canonical_key
        if not label or not value.value:
            continue
        comparable_count += 1
        if _normalize_label(label) == _normalize_label(value.value):
            echo_count += 1

    return comparable_count >= 2 and echo_count / comparable_count >= 0.8


def _output_format(output_path: str, default_format: str) -> str:
    suffix = Path(output_path).suffix.lstrip(".")
    return suffix or default_format


def _default_plan_id(template_model: TemplateModel, primary_record: SourceRecord) -> str:
    return f"{template_model.template_id}:{primary_record.record_id}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value or None


def _normalize_label(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value).casefold()
