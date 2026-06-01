from __future__ import annotations

from typing import Sequence

from doctransai.models.mapping import (
    FieldCandidate,
    ImageCandidate,
    ResolvedSlot,
    ResolverDecision,
    UnresolvedSlot,
)
from doctransai.models.source import ProvenanceRef


Candidate = FieldCandidate | ImageCandidate

_RULE_PRIORITY = {
    "exact_label": 5,
    "label_overlap": 4,
    "same_record_row": 4,
    "table_context": 3,
    "text_fact": 2,
    "weak_context": 1,
}
_AMBIGUITY_TOLERANCE = 0.01


def resolve_slot_candidates(
    *,
    slot_id: str,
    canonical_key: str,
    candidates: Sequence[Candidate],
    confidence_floor: float = 0.75,
    missing_reason_code: str = "missing_value",
) -> ResolverDecision:
    if not candidates:
        return ResolverDecision(
            unresolved_slots=[
                UnresolvedSlot(
                    slot_id=slot_id,
                    canonical_key=canonical_key,
                    reason_code=missing_reason_code,
                    message=f"No candidate was found for {canonical_key}.",
                )
            ]
        )

    ranked = sorted(
        candidates,
        key=lambda candidate: (_candidate_priority(candidate), candidate.confidence, candidate.candidate_id),
        reverse=True,
    )
    best = ranked[0]

    if best.confidence < confidence_floor:
        return ResolverDecision(
            unresolved_slots=[
                UnresolvedSlot(
                    slot_id=slot_id,
                    canonical_key=canonical_key,
                    reason_code="low_confidence",
                    message=f"Best candidate for {canonical_key} is below the confidence floor.",
                    candidate_ids=[best.candidate_id],
                    provenance_refs=list(best.provenance_refs),
                )
            ]
        )

    ambiguous = [
        candidate
        for candidate in ranked[1:]
        if _candidate_priority(candidate) == _candidate_priority(best)
        and abs(candidate.confidence - best.confidence) <= _AMBIGUITY_TOLERANCE
    ]
    if ambiguous:
        tied_candidates = [best, *ambiguous]
        return ResolverDecision(
            unresolved_slots=[
                UnresolvedSlot(
                    slot_id=slot_id,
                    canonical_key=canonical_key,
                    reason_code="ambiguous_match",
                    message=f"Multiple candidates remain tied for {canonical_key}.",
                    candidate_ids=[candidate.candidate_id for candidate in tied_candidates],
                    provenance_refs=_collect_provenance(tied_candidates),
                )
            ]
        )

    return ResolverDecision(
        resolved_slots=[
            ResolvedSlot(
                slot_id=slot_id,
                candidate_id=best.candidate_id,
                confidence=best.confidence,
                decision_reason=f"{best.rule}:{best.confidence:.2f}",
            )
        ]
    )


def _candidate_priority(candidate: Candidate) -> int:
    return _RULE_PRIORITY.get(candidate.rule, 0)


def _collect_provenance(candidates: Sequence[Candidate]) -> list[ProvenanceRef]:
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
