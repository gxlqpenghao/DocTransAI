from __future__ import annotations

from dataclasses import dataclass

from doctransai.mapping.candidate_builder import Candidate, SlotCandidatePacket
from doctransai.mapping.resolver import resolve_slot_candidates
from doctransai.models.mapping import ResolverDecision, UnresolvedSlot
from doctransai.models.template import TemplateSlot


@dataclass(slots=True)
class SlotDecision:
    slot: TemplateSlot
    slot_kind: str
    candidates: list[Candidate]
    resolver_decision: ResolverDecision


def resolve_slot_candidate_packets(
    packets: list[SlotCandidatePacket],
    *,
    confidence_floor: float = 0.75,
) -> list[SlotDecision]:
    decisions: list[SlotDecision] = []
    for packet in packets:
        if packet.slot_kind == "image" and not packet.candidates and packet.missing_candidates:
            resolver_decision = ResolverDecision(
                unresolved_slots=[
                    UnresolvedSlot(
                        slot_id=packet.slot.slot_id,
                        canonical_key=packet.slot.raw_name,
                        reason_code="missing_asset",
                        message=f"Resolved image candidate for {packet.slot.raw_name} points to a missing asset.",
                        candidate_ids=[candidate.candidate_id for candidate in packet.missing_candidates],
                        provenance_refs=_collect_candidate_provenance(packet.missing_candidates),
                    )
                ]
            )
        else:
            resolver_decision = resolve_slot_candidates(
                slot_id=packet.slot.slot_id,
                canonical_key=packet.slot.raw_name,
                candidates=packet.candidates,
                confidence_floor=confidence_floor,
                missing_reason_code="missing_asset" if packet.slot_kind == "image" else "missing_value",
            )
        decisions.append(
            SlotDecision(
                slot=packet.slot,
                slot_kind=packet.slot_kind,
                candidates=list(packet.candidates),
                resolver_decision=resolver_decision,
            )
        )
    return decisions


def _collect_candidate_provenance(candidates: list[Candidate]):
    refs = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for candidate in candidates:
        for ref in candidate.provenance_refs:
            key = (ref.asset_id, ref.object_id, ref.source_path)
            if key in seen:
                continue
            seen.add(key)
            refs.append(ref)
    return refs
