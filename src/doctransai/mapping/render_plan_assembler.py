from __future__ import annotations

from dataclasses import dataclass, field

from doctransai.mapping.slot_decisions import SlotDecision
from doctransai.models.mapping import FieldCandidate, ImageCandidate, UnresolvedSlot
from doctransai.models.render_plan import ImagePlacement, TargetRef, TextFill
from doctransai.models.template import SlotAddress


@dataclass(slots=True)
class SlotActions:
    text_fills: list[TextFill] = field(default_factory=list)
    image_placements: list[ImagePlacement] = field(default_factory=list)
    unresolved_slots: list[UnresolvedSlot] = field(default_factory=list)
    resolved_slot_ids: list[str] = field(default_factory=list)


def assemble_slot_actions(decisions: list[SlotDecision]) -> SlotActions:
    actions = SlotActions()
    for decision in decisions:
        actions.unresolved_slots.extend(decision.resolver_decision.unresolved_slots)
        if not decision.resolver_decision.resolved_slots:
            continue

        resolved = decision.resolver_decision.resolved_slots[0]
        chosen = next(candidate for candidate in decision.candidates if candidate.candidate_id == resolved.candidate_id)
        if isinstance(chosen, ImageCandidate):
            actions.image_placements.append(
                ImagePlacement(
                    slot_id=decision.slot.slot_id,
                    asset_id=chosen.asset_id,
                    source_ref=chosen.source_ref,
                    target=target_for_slot(decision.slot.address, placeholder_name=decision.slot.raw_name),
                    provenance_refs=list(chosen.provenance_refs),
                )
            )
        elif isinstance(chosen, FieldCandidate):
            actions.text_fills.append(
                TextFill(
                    slot_id=decision.slot.slot_id,
                    target=target_for_slot(decision.slot.address, placeholder_name=decision.slot.raw_name),
                    value=chosen.value,
                    provenance_refs=list(chosen.provenance_refs),
                    confidence=chosen.confidence,
                    transform=chosen.transform,
                )
            )
        actions.resolved_slot_ids.append(decision.slot.slot_id)
    return actions


def target_for_slot(address: SlotAddress, placeholder_name: str | None = None) -> TargetRef:
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
        notes=placeholder_name,
        repeat_region_id=None,
        instance_index=None,
    )


def target_for_repeat_slot(
    address: SlotAddress,
    *,
    placeholder_name: str | None,
    repeat_region_id: str,
    instance_index: int,
) -> TargetRef:
    target = target_for_slot(address, placeholder_name=placeholder_name)
    target.repeat_region_id = repeat_region_id
    target.instance_index = instance_index
    return target
