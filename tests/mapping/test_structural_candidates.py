from __future__ import annotations

from doctransai.mapping.structural_candidates import build_text_candidates_for_slot
from doctransai.models.source import ProvenanceRef, SourceModel, SourceRecord, SourceValue
from doctransai.models.template import SlotAddress, TemplateSlot


def _provenance(*, object_id: str, row_index: int, column_index: int) -> ProvenanceRef:
    return ProvenanceRef(
        source_kind="cell_range",
        document_id="doc-1",
        object_id=object_id,
        locator={"sheet_name": "Sheet0", "row_index": row_index, "column_index": column_index},
        source_path="/input/source.xlsx",
    )


def test_structural_candidates_use_exact_label_and_unique_typed_row_without_domain_pack() -> None:
    primary_record = SourceRecord(
        record_id="range-3",
        document_id="doc-1",
        source_path="/input/source.xlsx",
        locator={"sheet_name": "Sheet0", "row_index": 3},
        values=[
            SourceValue(
                canonical_key="项目名称",
                value="西香TJ3标",
                raw_label="项目名称",
                provenance=[_provenance(object_id="range-3", row_index=3, column_index=2)],
            ),
            SourceValue(
                canonical_key="联系电话",
                value="13800138000",
                raw_label="联系电话",
                provenance=[_provenance(object_id="range-3", row_index=3, column_index=8)],
            ),
        ],
    )
    source_model = SourceModel(records=[primary_record])

    project_slot = TemplateSlot(
        slot_id="slot-project",
        raw_name="项目名称",
        canonical_name="项目名称",
        slot_kind="text",
        address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
    )
    phone_slot = TemplateSlot(
        slot_id="slot-phone",
        raw_name="手机号",
        canonical_name="手机号",
        slot_kind="text",
        address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=1),
    )

    project_candidates = build_text_candidates_for_slot(
        slot=project_slot,
        primary_record=primary_record,
        source_model=source_model,
    )
    phone_candidates = build_text_candidates_for_slot(
        slot=phone_slot,
        primary_record=primary_record,
        source_model=source_model,
    )

    assert [(item.rule, item.value) for item in project_candidates] == [("exact_label", "西香TJ3标")]
    assert [(item.rule, item.value) for item in phone_candidates] == [("same_record_row", "13800138000")]


def test_structural_candidates_keep_same_value_rule_when_provenance_differs() -> None:
    primary_record = SourceRecord(
        record_id="range-3",
        document_id="doc-1",
        source_path="/input/source.xlsx",
        locator={"sheet_name": "Sheet0", "row_index": 3},
        values=[
            SourceValue(
                canonical_key="项目名称",
                value="西香TJ3标",
                raw_label="项目名称",
                provenance=[_provenance(object_id="range-3", row_index=3, column_index=2)],
            ),
            SourceValue(
                canonical_key="项目名称",
                value="西香TJ3标",
                raw_label="项目名称",
                provenance=[_provenance(object_id="range-4", row_index=4, column_index=2)],
            ),
        ],
    )
    source_model = SourceModel(records=[primary_record])
    slot = TemplateSlot(
        slot_id="slot-project",
        raw_name="项目名称",
        canonical_name="项目名称",
        slot_kind="text",
        address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
    )

    candidates = build_text_candidates_for_slot(
        slot=slot,
        primary_record=primary_record,
        source_model=source_model,
    )

    assert [candidate.candidate_id for candidate in candidates] == [
        "range-3:0:exact_label",
        "range-3:1:exact_label",
    ]
    assert [candidate.provenance_refs[0].object_id for candidate in candidates] == ["range-3", "range-4"]
