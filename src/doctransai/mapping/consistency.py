from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import ImagePlacement, TextFill
from doctransai.models.source import ProvenanceRef, SourceRecord
from doctransai.models.source_instance import SourceInstance
from doctransai.models.source_instance import SourceInstanceIndex
from doctransai.models.template import TemplateModel
from doctransai.source_model.instances import (
    constraint_scoped_instance_for_provenance,
    constraint_scoped_instance_for_record,
)


MISMATCH_REASON_CODE = "cross_slot_source_instance_mismatch"


@dataclass(slots=True)
class ConsistencyResult:
    text_fills: list[TextFill] = field(default_factory=list)
    image_placements: list[ImagePlacement] = field(default_factory=list)
    unresolved_slots: list[UnresolvedSlot] = field(default_factory=list)
    resolved_slot_ids: list[str] = field(default_factory=list)


def apply_cross_slot_consistency_checks(
    *,
    template_model: TemplateModel,
    primary_record: SourceRecord,
    text_fills: list[TextFill],
    image_placements: list[ImagePlacement],
    unresolved_slots: list[UnresolvedSlot],
    resolved_slot_ids: list[str],
    source_instance_index: SourceInstanceIndex | None = None,
) -> ConsistencyResult:
    primary_instance = _primary_instance(primary_record, source_instance_index)
    if primary_instance is None:
        return ConsistencyResult(
            text_fills=list(text_fills),
            image_placements=list(image_placements),
            unresolved_slots=list(unresolved_slots),
            resolved_slot_ids=list(resolved_slot_ids),
        )

    slots_by_id = {slot.slot_id: slot for slot in template_model.slots}
    kept_text_fills: list[TextFill] = []
    kept_image_placements: list[ImagePlacement] = []
    added_unresolved: list[UnresolvedSlot] = []
    mismatched_slot_ids: set[str] = set()

    for fill in text_fills:
        if _has_source_instance_mismatch(
            fill.provenance_refs,
            primary_instance,
            source_instance_index,
        ) and _is_non_repeat_action(fill):
            slot = slots_by_id.get(_base_slot_id(fill.slot_id))
            added_unresolved.append(
                UnresolvedSlot(
                    slot_id=fill.slot_id,
                    canonical_key=slot.raw_name if slot is not None else fill.slot_id,
                    reason_code=MISMATCH_REASON_CODE,
                    message=(
                        "Resolved candidate was withheld because its row/table provenance "
                        "does not match the selected source instance."
                    ),
                    provenance_refs=list(fill.provenance_refs),
                )
            )
            mismatched_slot_ids.add(fill.slot_id)
            continue
        kept_text_fills.append(fill)

    for placement in image_placements:
        if _has_source_instance_mismatch(
            placement.provenance_refs,
            primary_instance,
            source_instance_index,
        ) and _is_non_repeat_action(placement):
            slot = slots_by_id.get(_base_slot_id(placement.slot_id))
            added_unresolved.append(
                UnresolvedSlot(
                    slot_id=placement.slot_id,
                    canonical_key=slot.raw_name if slot is not None else placement.slot_id,
                    reason_code=MISMATCH_REASON_CODE,
                    message=(
                        "Resolved candidate was withheld because its row/table provenance "
                        "does not match the selected source instance."
                    ),
                    candidate_ids=[placement.asset_id],
                    provenance_refs=list(placement.provenance_refs),
                )
            )
            mismatched_slot_ids.add(placement.slot_id)
            continue
        kept_image_placements.append(placement)

    return ConsistencyResult(
        text_fills=kept_text_fills,
        image_placements=kept_image_placements,
        unresolved_slots=[*unresolved_slots, *added_unresolved],
        resolved_slot_ids=[slot_id for slot_id in resolved_slot_ids if slot_id not in mismatched_slot_ids],
    )


def _primary_instance(
    primary_record: SourceRecord,
    source_instance_index: SourceInstanceIndex | None,
) -> SourceInstance | None:
    if source_instance_index is not None:
        indexed_instance = constraint_scoped_instance_for_record(source_instance_index, primary_record.record_id)
        if indexed_instance is not None:
            return indexed_instance
    return _legacy_instance_from_record(primary_record)


def _has_source_instance_mismatch(
    refs: list[ProvenanceRef],
    primary_instance: SourceInstance,
    source_instance_index: SourceInstanceIndex | None,
) -> bool:
    instances = [_instance_from_provenance(ref, source_instance_index) for ref in refs]
    scoped_instances = [instance for instance in instances if instance is not None]
    return any(not _same_source_instance(instance, primary_instance) for instance in scoped_instances)


def _same_source_instance(left: SourceInstance, right: SourceInstance) -> bool:
    if left.instance_kind != right.instance_kind:
        return False
    if left.container_id != right.container_id or left.row_index != right.row_index:
        return False
    if left.document_id is not None and right.document_id is not None and left.document_id != right.document_id:
        return False
    if left.source_path is not None and right.source_path is not None and left.source_path != right.source_path:
        return False
    return True


def _is_non_repeat_action(action: TextFill | ImagePlacement) -> bool:
    target = action.target
    return target.repeat_region_id is None and target.instance_index is None


def _legacy_instance_from_record(record: SourceRecord) -> SourceInstance | None:
    locator = record.locator
    row_index = _int_value(locator.get("row_index"))
    if row_index is None:
        return None

    table_id = _string_value(record.table_id) or _string_value(locator.get("table_id"))
    if table_id is not None:
        return _legacy_row_instance(
            instance_kind="table_row",
            document_id=record.document_id,
            source_path=record.source_path,
            container_id=table_id,
            row_index=row_index,
            locator=locator,
        )

    sheet_name = _string_value(locator.get("sheet_name"))
    if sheet_name is not None:
        return _legacy_row_instance(
            instance_kind="sheet_row",
            document_id=record.document_id,
            source_path=record.source_path,
            container_id=sheet_name,
            row_index=row_index,
            locator=locator,
        )

    return None


def _instance_from_provenance(
    ref: ProvenanceRef,
    source_instance_index: SourceInstanceIndex | None,
) -> SourceInstance | None:
    if source_instance_index is not None:
        indexed_instance = constraint_scoped_instance_for_provenance(source_instance_index, ref)
        if indexed_instance is not None:
            return indexed_instance
    return _legacy_instance_from_provenance(ref)


def _legacy_instance_from_provenance(ref: ProvenanceRef) -> SourceInstance | None:
    locator = ref.locator
    row_index = _int_value(locator.get("row_index"))
    if row_index is None:
        return None

    table_id = _string_value(locator.get("table_id"))
    if table_id is not None:
        return _legacy_row_instance(
            instance_kind="table_row",
            document_id=ref.document_id,
            source_path=ref.source_path,
            container_id=table_id,
            row_index=row_index,
            locator=locator,
        )

    sheet_name = _string_value(locator.get("sheet_name"))
    if sheet_name is not None:
        return _legacy_row_instance(
            instance_kind="sheet_row",
            document_id=ref.document_id,
            source_path=ref.source_path,
            container_id=sheet_name,
            row_index=row_index,
            locator=locator,
        )

    return None


def _legacy_row_instance(
    *,
    instance_kind: str,
    document_id: str | None,
    source_path: str | None,
    container_id: str,
    row_index: int,
    locator: dict[str, Any],
) -> SourceInstance:
    return SourceInstance(
        instance_id=f"legacy:{instance_kind}:{document_id or source_path or 'unknown'}:{container_id}:{row_index}",
        instance_kind=instance_kind,
        document_id=document_id,
        source_path=source_path,
        container_id=container_id,
        row_index=row_index,
        locator=dict(locator),
    )


def _base_slot_id(slot_id: str) -> str:
    return slot_id.split("@", 1)[0]


def _int_value(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
