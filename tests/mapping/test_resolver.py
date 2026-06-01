from __future__ import annotations

from doctransai.models.mapping import FieldCandidate
from doctransai.models.source import ProvenanceRef

from doctransai.mapping.resolver import resolve_slot_candidates


def _provenance(*, object_id: str, row_index: int = 3) -> ProvenanceRef:
    return ProvenanceRef(
        source_kind="cell_range",
        document_id="doc-1",
        object_id=object_id,
        locator={"sheet_name": "Sheet0", "row_index": row_index},
        source_path="/input/source.xlsx",
    )


def _field_candidate(
    candidate_id: str,
    *,
    rule: str,
    value: str,
    confidence: float,
    row_index: int = 3,
) -> FieldCandidate:
    return FieldCandidate(
        candidate_id=candidate_id,
        slot_id="slot-desc",
        canonical_key="隐患描述",
        value=value,
        confidence=confidence,
        rule=rule,
        provenance_refs=[_provenance(object_id=candidate_id, row_index=row_index)],
    )


def test_resolve_slot_candidates_prefers_exact_field_over_lower_rank_context() -> None:
    decision = resolve_slot_candidates(
        slot_id="slot-desc",
        canonical_key="隐患描述",
        candidates=[
            _field_candidate("cand-table", rule="table_context", value="表格值", confidence=0.99),
            _field_candidate("cand-text", rule="text_fact", value="正文值", confidence=0.99),
            _field_candidate("cand-row", rule="same_record_row", value="同行值", confidence=0.98),
            _field_candidate("cand-exact", rule="exact_label", value="精确值", confidence=0.90),
        ],
    )

    assert [item.candidate_id for item in decision.resolved_slots] == ["cand-exact"]
    assert decision.unresolved_slots == []
    assert "exact_label" in decision.resolved_slots[0].decision_reason


def test_resolve_slot_candidates_marks_same_rank_tie_as_ambiguous() -> None:
    decision = resolve_slot_candidates(
        slot_id="slot-desc",
        canonical_key="隐患描述",
        candidates=[
            _field_candidate("cand-a", rule="exact_label", value="值A", confidence=0.92, row_index=3),
            _field_candidate("cand-b", rule="same_record_row", value="值B", confidence=0.92, row_index=4),
            _field_candidate("cand-c", rule="table_context", value="值C", confidence=0.99, row_index=5),
        ],
    )

    assert [item.candidate_id for item in decision.resolved_slots] == ["cand-a"]
    assert decision.unresolved_slots == []


def test_resolve_slot_candidates_marks_same_value_from_distinct_provenance_as_ambiguous() -> None:
    decision = resolve_slot_candidates(
        slot_id="slot-project",
        canonical_key="项目名称",
        candidates=[
            _field_candidate("cand-row-3", rule="exact_label", value="同名项目", confidence=0.99, row_index=3),
            _field_candidate("cand-row-4", rule="exact_label", value="同名项目", confidence=0.99, row_index=4),
        ],
    )

    assert decision.resolved_slots == []
    assert [slot.reason_code for slot in decision.unresolved_slots] == ["ambiguous_match"]
    assert decision.unresolved_slots[0].candidate_ids == ["cand-row-4", "cand-row-3"]
    assert [ref.locator["row_index"] for ref in decision.unresolved_slots[0].provenance_refs] == [4, 3]


def test_resolve_slot_candidates_marks_low_confidence_as_unresolved() -> None:
    decision = resolve_slot_candidates(
        slot_id="slot-desc",
        canonical_key="隐患描述",
        confidence_floor=0.75,
        candidates=[
            _field_candidate("cand-low", rule="exact_label", value="精确值", confidence=0.51),
        ],
    )

    assert decision.resolved_slots == []
    assert [item.reason_code for item in decision.unresolved_slots] == ["low_confidence"]
    assert decision.unresolved_slots[0].candidate_ids == ["cand-low"]


def test_resolve_slot_candidates_marks_missing_value_when_no_candidates_exist() -> None:
    decision = resolve_slot_candidates(
        slot_id="slot-desc",
        canonical_key="隐患描述",
        candidates=[],
    )

    assert decision.resolved_slots == []
    assert [item.reason_code for item in decision.unresolved_slots] == ["missing_value"]
