from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from doctransai.mapping.structural_candidates import build_text_candidates_for_slot
from doctransai.mapping.visual_candidates import build_image_availability_for_slot, build_image_header_index
from doctransai.models.mapping import FieldCandidate, ImageCandidate
from doctransai.models.source import SourceImageAsset, SourceModel, SourceRecord
from doctransai.models.template import TemplateModel, TemplateSlot


Candidate = FieldCandidate | ImageCandidate


@dataclass(slots=True)
class SlotCandidatePacket:
    slot: TemplateSlot
    slot_kind: str
    candidates: list[Candidate] = field(default_factory=list)
    missing_candidates: list[Candidate] = field(default_factory=list)


def build_slot_candidate_packets(
    *,
    template_model: TemplateModel,
    source_model: SourceModel,
    primary_record: SourceRecord,
    source_bundle_path: str,
    skip_slot_ids: set[str] | None = None,
) -> list[SlotCandidatePacket]:
    skipped = skip_slot_ids or set()
    header_by_sheet = build_image_header_index(source_model.records)
    packets: list[SlotCandidatePacket] = []

    for slot in template_model.slots:
        if slot.slot_id in skipped:
            continue

        if slot.slot_kind == "image":
            availability = build_image_availability_for_slot(
                slot=slot,
                primary_record=primary_record,
                source_model=source_model,
                header_by_sheet=header_by_sheet,
            )
            packets.append(
                SlotCandidatePacket(
                    slot=slot,
                    slot_kind="image",
                    candidates=[
                        item.candidate
                        for item in availability
                        if _asset_exists(item.asset, source_bundle_path)
                    ],
                    missing_candidates=[
                        item.candidate
                        for item in availability
                        if not _asset_exists(item.asset, source_bundle_path)
                    ],
                )
            )
            continue

        packets.append(
            SlotCandidatePacket(
                slot=slot,
                slot_kind="text",
                candidates=build_text_candidates_for_slot(
                    slot=slot,
                    primary_record=primary_record,
                    source_model=source_model,
                ),
            )
        )

    return packets


def _asset_exists(asset: SourceImageAsset, source_bundle_path: str) -> bool:
    bundle_dir = Path(source_bundle_path).expanduser().resolve().parent
    candidates: list[Path] = []
    if asset.asset_path:
        candidates.append(Path(asset.asset_path).expanduser())
    if asset.source_ref:
        candidates.append((bundle_dir / asset.source_ref).expanduser())
        parsed_dir = bundle_dir / "parsed"
        if parsed_dir.exists():
            candidates.extend(parsed_dir.glob(f"*/{asset.source_ref}"))
    return any(path.exists() for path in candidates)
