from __future__ import annotations

from dataclasses import dataclass, field

from doctransai.models.source import ProvenanceRef


@dataclass(slots=True)
class FieldCandidate:
    candidate_id: str
    slot_id: str
    canonical_key: str
    value: str
    confidence: float
    rule: str
    provenance_refs: list[ProvenanceRef] = field(default_factory=list)
    transform: str | None = None


@dataclass(slots=True)
class ImageCandidate:
    candidate_id: str
    slot_id: str
    asset_id: str
    source_ref: str | None
    confidence: float
    rule: str
    provenance_refs: list[ProvenanceRef] = field(default_factory=list)
    placement_role: str | None = None


@dataclass(slots=True)
class ResolvedSlot:
    slot_id: str
    candidate_id: str
    confidence: float
    decision_reason: str


@dataclass(slots=True)
class UnresolvedSlot:
    slot_id: str
    canonical_key: str
    reason_code: str
    message: str
    candidate_ids: list[str] = field(default_factory=list)
    provenance_refs: list[ProvenanceRef] = field(default_factory=list)


@dataclass(slots=True)
class ResolverDecision:
    resolved_slots: list[ResolvedSlot] = field(default_factory=list)
    unresolved_slots: list[UnresolvedSlot] = field(default_factory=list)
