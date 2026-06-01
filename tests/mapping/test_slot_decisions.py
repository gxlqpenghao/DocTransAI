from __future__ import annotations

from doctransai.mapping.candidate_builder import SlotCandidatePacket
from doctransai.mapping.render_plan_assembler import assemble_slot_actions
from doctransai.mapping.slot_decisions import resolve_slot_candidate_packets
from doctransai.models.mapping import FieldCandidate, ImageCandidate
from doctransai.models.source import ProvenanceRef
from doctransai.models.template import SlotAddress, TemplateSlot


def _provenance() -> ProvenanceRef:
    return ProvenanceRef(source_kind="cell_range", document_id="doc-1", object_id="value-1")


def test_resolve_slot_candidate_packets_and_assemble_actions() -> None:
    text_slot = TemplateSlot(
        slot_id="slot-project",
        raw_name="项目名称",
        canonical_name="项目名称",
        slot_kind="text",
        address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
    )
    image_slot = TemplateSlot(
        slot_id="slot-photo",
        raw_name="现场照片",
        canonical_name="现场照片",
        slot_kind="image",
        address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=1),
    )
    missing_slot = TemplateSlot(
        slot_id="slot-missing",
        raw_name="负责人",
        canonical_name="负责人",
        slot_kind="text",
        address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=2),
    )
    packets = [
        SlotCandidatePacket(
            slot=text_slot,
            slot_kind="text",
            candidates=[
                FieldCandidate(
                    candidate_id="cand-text",
                    slot_id=text_slot.slot_id,
                    canonical_key=text_slot.raw_name,
                    value="西香TJ3标",
                    confidence=0.99,
                    rule="exact_label",
                    provenance_refs=[_provenance()],
                )
            ],
        ),
        SlotCandidatePacket(
            slot=image_slot,
            slot_kind="image",
            candidates=[
                ImageCandidate(
                    candidate_id="asset-1",
                    slot_id=image_slot.slot_id,
                    asset_id="asset-1",
                    source_ref="final_images/photo.jpg",
                    confidence=0.99,
                    rule="exact_label",
                    provenance_refs=[_provenance()],
                )
            ],
        ),
        SlotCandidatePacket(slot=missing_slot, slot_kind="text", candidates=[]),
    ]

    decisions = resolve_slot_candidate_packets(packets)
    actions = assemble_slot_actions(decisions)

    assert [fill.slot_id for fill in actions.text_fills] == ["slot-project"]
    assert actions.text_fills[0].value == "西香TJ3标"
    assert [placement.slot_id for placement in actions.image_placements] == ["slot-photo"]
    assert actions.image_placements[0].source_ref == "final_images/photo.jpg"
    assert [slot.slot_id for slot in actions.unresolved_slots] == ["slot-missing"]
    assert actions.resolved_slot_ids == ["slot-project", "slot-photo"]


def test_resolve_slot_candidate_packets_marks_missing_image_assets() -> None:
    image_slot = TemplateSlot(
        slot_id="slot-photo",
        raw_name="现场照片",
        canonical_name="现场照片",
        slot_kind="image",
        address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=1),
    )
    packet = SlotCandidatePacket(
        slot=image_slot,
        slot_kind="image",
        candidates=[],
        missing_candidates=[
            ImageCandidate(
                candidate_id="asset-missing",
                slot_id=image_slot.slot_id,
                asset_id="asset-missing",
                source_ref="final_images/missing.jpg",
                confidence=0.99,
                rule="exact_label",
                provenance_refs=[_provenance()],
            )
        ],
    )

    decisions = resolve_slot_candidate_packets([packet])
    actions = assemble_slot_actions(decisions)

    assert actions.image_placements == []
    assert [slot.reason_code for slot in actions.unresolved_slots] == ["missing_asset"]
    assert actions.unresolved_slots[0].candidate_ids == ["asset-missing"]
