from __future__ import annotations

from pathlib import Path

from doctransai.mapping.candidate_builder import build_slot_candidate_packets
from doctransai.models.source import ProvenanceRef, SourceImageAsset, SourceModel, SourceRecord, SourceValue
from doctransai.models.template import SlotAddress, TemplateModel, TemplateSlot


def _provenance(*, object_id: str, row_index: int, column_index: int) -> ProvenanceRef:
    return ProvenanceRef(
        source_kind="cell_range",
        document_id="doc-1",
        object_id=object_id,
        locator={"sheet_name": "Sheet0", "row_index": row_index, "column_index": column_index},
        source_path="/input/source.xlsx",
    )


def test_build_slot_candidate_packets_unifies_text_and_image_candidates(tmp_path: Path) -> None:
    image_path = tmp_path / "parsed" / "checksum-1" / "final_images" / "photo.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"image")
    bundle_path = tmp_path / "parsed_document_bundle.json"

    primary_record = SourceRecord(
        record_id="range-3",
        document_id="doc-1",
        source_path="/input/source.xlsx",
        evidence_id="ev-1",
        locator={"sheet_name": "Sheet0", "row_index": 3},
        values=[
            SourceValue(
                canonical_key="项目名称",
                raw_label="项目名称",
                value="西香TJ3标",
                provenance=[_provenance(object_id="range-3", row_index=3, column_index=2)],
            )
        ],
    )
    header_record = SourceRecord(
        record_id="range-header",
        document_id="doc-1",
        source_path="/input/source.xlsx",
        locator={"sheet_name": "Sheet0", "row_index": 2},
        values=[
            SourceValue(
                canonical_key="现场照片",
                value="现场照片",
                provenance=[_provenance(object_id="range-header", row_index=2, column_index=4)],
            )
        ],
    )
    source_model = SourceModel(
        records=[header_record, primary_record],
        image_assets=[
            SourceImageAsset(
                asset_id="asset-1",
                source_ref="final_images/photo.jpg",
                asset_path=str(image_path),
                sheet_name="Sheet0",
                row_index=3,
                column_index=4,
            )
        ],
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/template.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=[
            TemplateSlot(
                slot_id="slot-project",
                raw_name="项目名称",
                canonical_name="项目名称",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            ),
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="现场照片",
                canonical_name="现场照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=1),
            ),
        ],
    )

    packets = build_slot_candidate_packets(
        template_model=template_model,
        source_model=source_model,
        primary_record=primary_record,
        source_bundle_path=str(bundle_path),
    )

    assert [packet.slot.slot_id for packet in packets] == ["slot-project", "slot-photo"]
    assert [packet.slot_kind for packet in packets] == ["text", "image"]
    assert [(candidate.candidate_id, candidate.value) for candidate in packets[0].candidates] == [
        ("range-3:0:exact_label", "西香TJ3标")
    ]
    assert [(candidate.candidate_id, candidate.asset_id) for candidate in packets[1].candidates] == [
        ("asset-1", "asset-1")
    ]
    assert packets[1].missing_candidates == []


def test_build_slot_candidate_packets_tracks_missing_image_candidates(tmp_path: Path) -> None:
    bundle_path = tmp_path / "parsed_document_bundle.json"
    primary_record = SourceRecord(
        record_id="range-3",
        document_id="doc-1",
        source_path="/input/source.xlsx",
        locator={"sheet_name": "Sheet0", "row_index": 3},
        values=[],
    )
    header_record = SourceRecord(
        record_id="range-header",
        document_id="doc-1",
        source_path="/input/source.xlsx",
        locator={"sheet_name": "Sheet0", "row_index": 2},
        values=[
            SourceValue(
                canonical_key="现场照片",
                value="现场照片",
                provenance=[_provenance(object_id="range-header", row_index=2, column_index=4)],
            )
        ],
    )
    source_model = SourceModel(
        records=[header_record, primary_record],
        image_assets=[
            SourceImageAsset(
                asset_id="asset-missing",
                source_ref="final_images/missing.jpg",
                asset_path=str(tmp_path / "final_images" / "missing.jpg"),
                sheet_name="Sheet0",
                row_index=3,
                column_index=4,
            )
        ],
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/template.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=[
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="现场照片",
                canonical_name="现场照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            ),
        ],
    )

    packets = build_slot_candidate_packets(
        template_model=template_model,
        source_model=source_model,
        primary_record=primary_record,
        source_bundle_path=str(bundle_path),
    )

    assert packets[0].candidates == []
    assert [candidate.candidate_id for candidate in packets[0].missing_candidates] == ["asset-missing"]
