from __future__ import annotations

from pathlib import Path

from doctransai.models.source import SourceImageAsset, SourceModel, SourceRecord
from doctransai.models.template import SlotAddress, TemplateSlot

from doctransai.mapping.visual_candidates import build_image_candidates_for_slot


_HEADERS = [
    "编号",
    "项目名称",
    "入场照片",
    "过程照片",
    "完工照片",
]


def _slot(slot_id: str, raw_name: str) -> TemplateSlot:
    return TemplateSlot(
        slot_id=slot_id,
        raw_name=raw_name,
        canonical_name=raw_name,
        slot_kind="image",
        address=SlotAddress(format_key="docx", address_kind="placeholder", paragraph_index=0),
    )


def _row_record(*, row_index: int, evidence_id: str) -> SourceRecord:
    return SourceRecord(
        record_id=f"range-{row_index}",
        document_id="doc-1",
        source_path="/input/report.xlsx",
        evidence_id=evidence_id,
        locator={"sheet_name": "Sheet0", "row_index": row_index},
        raw={"parser_signals": {"header_values": list(_HEADERS), "row_index": row_index}},
    )


def _asset(
    tmp_path: Path,
    *,
    asset_id: str,
    row_index: int,
    column_index: int,
    related_evidence_ids: list[str] | None = None,
    create_file: bool = True,
) -> SourceImageAsset:
    asset_path = tmp_path / f"{asset_id}.jpg"
    if create_file:
        asset_path.write_bytes(b"fixture")
    return SourceImageAsset(
        asset_id=asset_id,
        source_ref=f"final_images/{asset_id}.jpg",
        asset_path=str(asset_path),
        sheet_name="Sheet0",
        row_index=row_index,
        column_index=column_index,
        related_evidence_ids=list(related_evidence_ids or []),
        raw={"cell_anchor": f"C{row_index}"},
    )


def test_build_image_candidates_prefers_row_and_header_over_weak_related_evidence_ids(tmp_path: Path) -> None:
    record = _row_record(row_index=12, evidence_id="ev-12")
    source_model = SourceModel(
        records=[record],
        image_assets=[
            _asset(tmp_path, asset_id="entry-12", row_index=12, column_index=3),
            _asset(tmp_path, asset_id="process-12", row_index=12, column_index=4),
            _asset(tmp_path, asset_id="done-12", row_index=12, column_index=5),
            _asset(
                tmp_path,
                asset_id="wrong-row-linked",
                row_index=11,
                column_index=3,
                related_evidence_ids=["ev-12"],
            ),
        ],
    )

    entry = build_image_candidates_for_slot(source_model=source_model, record=record, slot=_slot("slot-entry", "入场照片"))
    process = build_image_candidates_for_slot(source_model=source_model, record=record, slot=_slot("slot-process", "过程照片"))
    done = build_image_candidates_for_slot(source_model=source_model, record=record, slot=_slot("slot-done", "完工照片"))

    assert [candidate.asset_id for candidate in entry.candidates] == ["entry-12"]
    assert [candidate.asset_id for candidate in process.candidates] == ["process-12"]
    assert [candidate.asset_id for candidate in done.candidates] == ["done-12"]
    assert entry.candidates[0].placement_role == "入场照片"
    assert process.candidates[0].placement_role == "过程照片"
    assert done.candidates[0].placement_role == "完工照片"
    assert entry.unresolved_slots == []
    assert entry.diagnostics == []


def test_build_image_candidates_surfaces_unresolved_and_diagnostic_for_missing_file(tmp_path: Path) -> None:
    record = _row_record(row_index=13, evidence_id="ev-13")
    source_model = SourceModel(
        records=[record],
        image_assets=[
            _asset(
                tmp_path,
                asset_id="process-missing",
                row_index=13,
                column_index=4,
                related_evidence_ids=["ev-13"],
                create_file=False,
            )
        ],
    )

    result = build_image_candidates_for_slot(
        source_model=source_model,
        record=record,
        slot=_slot("slot-process", "过程照片"),
    )

    assert result.candidates == []
    assert len(result.unresolved_slots) == 1
    assert result.unresolved_slots[0].slot_id == "slot-process"
    assert result.unresolved_slots[0].reason_code == "missing_image_asset_file"
    assert "过程照片" in result.unresolved_slots[0].message
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "missing_image_asset_file"
    assert result.diagnostics[0].field == "slot-process"
