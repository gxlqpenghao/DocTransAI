from __future__ import annotations

from pathlib import Path

from doctransai.mapping.planner import build_render_plan
from doctransai.models.render_plan import render_plan_from_dict
from doctransai.models.source import ProvenanceRef, SourceImageAsset, SourceModel, SourceRecord, SourceValue
from doctransai.models.template import RepeatRegion, SlotAddress, TemplateModel, TemplateSlot


def _provenance(
    *,
    object_id: str,
    row_index: int,
    column_index: int,
    source_kind: str = "cell_range",
) -> ProvenanceRef:
    return ProvenanceRef(
        source_kind=source_kind,
        document_id="doc-1",
        object_id=object_id,
        locator={
            "sheet_name": "Sheet0",
            "row_index": row_index,
            "column_index": column_index,
        },
        source_path="/input/source.xlsx",
    )


def _cell_value(key: str, value: str, *, object_id: str, row_index: int, column_index: int) -> SourceValue:
    return SourceValue(
        canonical_key=key,
        value=value,
        provenance=[_provenance(object_id=object_id, row_index=row_index, column_index=column_index)],
    )


def _header_record() -> SourceRecord:
    return SourceRecord(
        record_id="range-header",
        document_id="doc-1",
        source_path="/input/source.xlsx",
        cell_range_id="range-header",
        locator={"sheet_name": "Sheet0", "row_index": 2, "cell_range": "A2:Y2"},
        values=[
            _cell_value("项目名称", "项目名称", object_id="range-header", row_index=2, column_index=2),
            _cell_value("隐患描述", "隐患描述", object_id="range-header", row_index=2, column_index=10),
            _cell_value("整改要求", "整改要求", object_id="range-header", row_index=2, column_index=12),
            _cell_value("隐患照片", "隐患照片", object_id="range-header", row_index=2, column_index=11),
            _cell_value("整改照片", "整改照片", object_id="range-header", row_index=2, column_index=20),
            _cell_value("复查照片", "复查照片", object_id="range-header", row_index=2, column_index=25),
        ],
    )


def _primary_record() -> SourceRecord:
    return SourceRecord(
        record_id="range-3",
        document_id="doc-1",
        source_path="/input/source.xlsx",
        evidence_id="ev-1",
        cell_range_id="range-3",
        locator={"sheet_name": "Sheet0", "row_index": 3, "cell_range": "A3:Y3"},
        values=[
            _cell_value("项目名称", "西香TJ3标", object_id="range-3", row_index=3, column_index=2),
            _cell_value("隐患描述", "右幅作业人员安全带缺少缓冲包", object_id="range-3", row_index=3, column_index=10),
            _cell_value("整改要求", "及时更换作业人员安全带", object_id="range-3", row_index=3, column_index=12),
        ],
    )


def _narrative_record() -> SourceRecord:
    return SourceRecord(
        record_id="ev-99",
        document_id="doc-1",
        source_path="/input/source.docx",
        evidence_id="ev-99",
        locator={"page_anchor": "page_1"},
        values=[
            SourceValue(
                canonical_key="text",
                value="项目名称：旧项目",
                provenance=[_provenance(object_id="ev-99", row_index=1, column_index=1, source_kind="evidence")],
            )
        ],
    )


def _template_model(*, include_missing_owner: bool = True) -> TemplateModel:
    slots = [
        TemplateSlot(
            slot_id="slot-project",
            raw_name="项目名称",
            canonical_name="项目名称",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        ),
        TemplateSlot(
            slot_id="slot-desc",
            raw_name="隐患描述",
            canonical_name="隐患描述",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=1),
        ),
        TemplateSlot(
            slot_id="slot-demand",
            raw_name="整改要求",
            canonical_name="整改要求",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=2),
        ),
        TemplateSlot(
            slot_id="slot-photo",
            raw_name="隐患照片",
            canonical_name="隐患照片",
            slot_kind="image",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=3),
        ),
    ]
    if include_missing_owner:
        slots.append(
            TemplateSlot(
                slot_id="slot-owner",
                raw_name="责任单位负责人",
                canonical_name="责任单位负责人",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=4),
            )
        )

    return TemplateModel(
        template_id="template-docx",
        template_path="/templates/result.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=slots,
    )


def test_build_render_plan_returns_render_plan_json_and_keeps_primary_record_context(tmp_path: Path) -> None:
    asset_path = tmp_path / "final_images" / "photo-1.jpg"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"fixture")

    source_model = SourceModel(
        records=[_header_record(), _primary_record(), _narrative_record()],
        image_assets=[
            SourceImageAsset(
                asset_id="asset-1",
                source_ref="final_images/photo-1.jpg",
                asset_path=str(asset_path),
                sheet_name="Sheet0",
                row_index=3,
                column_index=11,
                related_evidence_ids=["ev-1"],
            )
        ],
    )

    payload = build_render_plan(
        template_model=_template_model(),
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "result.docx"),
        primary_record_id="range-3",
        plan_id="plan-1",
        created_at="2026-05-21T12:00:00Z",
    )

    plan = render_plan_from_dict(payload)
    text_by_slot = {fill.slot_id: fill.value for fill in plan.text_fills}
    unresolved_by_slot = {slot.slot_id: slot for slot in plan.unresolved_slots}

    assert isinstance(payload, dict)
    assert plan.plan_id == "plan-1"
    assert text_by_slot["slot-project"] == "西香TJ3标"
    assert text_by_slot["slot-project"] != "旧项目"
    assert text_by_slot["slot-desc"] == "右幅作业人员安全带缺少缓冲包"
    assert text_by_slot["slot-demand"] == "及时更换作业人员安全带"
    assert {placement.slot_id for placement in plan.image_placements} == {"slot-photo"}
    assert unresolved_by_slot["slot-owner"].reason_code == "missing_value"
    assert plan.record_plans[0].record_id == "range-3"
    assert set(plan.record_plans[0].slot_ids) == {"slot-project", "slot-desc", "slot-demand", "slot-photo"}


def test_build_render_plan_marks_missing_image_asset_as_unresolved(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[_header_record(), _primary_record()],
        image_assets=[
            SourceImageAsset(
                asset_id="asset-missing",
                source_ref="final_images/photo-missing.jpg",
                asset_path=str(tmp_path / "final_images" / "photo-missing.jpg"),
                sheet_name="Sheet0",
                row_index=3,
                column_index=11,
                related_evidence_ids=["ev-1"],
            )
        ],
    )

    payload = build_render_plan(
        template_model=_template_model(include_missing_owner=False),
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "result.docx"),
        primary_record_id="range-3",
        plan_id="plan-missing-image",
        created_at="2026-05-21T12:30:00Z",
    )

    plan = render_plan_from_dict(payload)

    assert plan.image_placements == []
    assert [slot.slot_id for slot in plan.unresolved_slots] == ["slot-photo"]
    assert [slot.reason_code for slot in plan.unresolved_slots] == ["missing_asset"]
    assert plan.unresolved_slots[0].candidate_ids == ["asset-missing"]


def test_build_render_plan_can_select_table_row_record_without_primary_record_id(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="tblrow-header",
                document_id="doc-1",
                source_path="/input/source.docx",
                table_id="tbl-1",
                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 1},
                raw={"is_header": True},
                values=[],
            ),
            SourceRecord(
                record_id="tblrow-2",
                document_id="doc-1",
                source_path="/input/source.docx",
                table_id="tbl-1",
                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 2},
                values=[
                    SourceValue(
                        canonical_key="项目名称",
                        value="项目B",
                        provenance=[
                            ProvenanceRef(
                                source_kind="table_cell",
                                document_id="doc-1",
                                object_id="tblcell-1",
                                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 2, "column_index": 1},
                                source_path="/input/source.docx",
                            )
                        ],
                    ),
                    SourceValue(
                        canonical_key="隐患描述",
                        value="脚手架未封闭",
                        provenance=[
                            ProvenanceRef(
                                source_kind="table_cell",
                                document_id="doc-1",
                                object_id="tblcell-2",
                                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 2, "column_index": 2},
                                source_path="/input/source.docx",
                            )
                        ],
                    ),
                ],
            ),
        ]
    )

    payload = build_render_plan(
        template_model=_template_model(include_missing_owner=False),
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "result.docx"),
    )

    plan = render_plan_from_dict(payload)
    text_by_slot = {fill.slot_id: fill.value for fill in plan.text_fills}

    assert plan.record_plans[0].record_id == "tblrow-2"
    assert text_by_slot["slot-project"] == "项目B"
    assert text_by_slot["slot-desc"] == "脚手架未封闭"


def test_build_render_plan_skips_label_echo_header_row_without_primary_record_id(tmp_path: Path) -> None:
    source_model = SourceModel(records=[_header_record(), _primary_record()])

    payload = build_render_plan(
        template_model=_template_model(include_missing_owner=False),
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "result.docx"),
    )

    plan = render_plan_from_dict(payload)
    text_by_slot = {fill.slot_id: fill.value for fill in plan.text_fills}

    assert plan.record_plans[0].record_id == "range-3"
    assert text_by_slot["slot-project"] == "西香TJ3标"
    assert text_by_slot["slot-desc"] == "右幅作业人员安全带缺少缓冲包"
    assert text_by_slot["slot-demand"] == "及时更换作业人员安全带"


def test_build_render_plan_can_select_primary_record_by_source_instance_id(tmp_path: Path) -> None:
    row_4 = SourceRecord(
        record_id="range-4",
        document_id="doc-1",
        source_path="/input/source.xlsx",
        cell_range_id="range-4",
        locator={"sheet_name": "Sheet0", "row_index": 4, "cell_range": "A4:Y4"},
        values=[
            _cell_value("项目名称", "西香TJ4标", object_id="range-4", row_index=4, column_index=2),
            _cell_value("隐患描述", "临边防护缺失", object_id="range-4", row_index=4, column_index=10),
            _cell_value("整改要求", "补齐临边防护", object_id="range-4", row_index=4, column_index=12),
        ],
    )
    source_model = SourceModel(records=[_header_record(), _primary_record(), row_4])

    payload = build_render_plan(
        template_model=_template_model(include_missing_owner=False),
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "result.docx"),
        source_instance_id="sheet_row:doc-1:Sheet0:4",
    )

    plan = render_plan_from_dict(payload)
    text_by_slot = {fill.slot_id: fill.value for fill in plan.text_fills}

    assert plan.record_plans[0].record_id == "range-4"
    assert text_by_slot["slot-project"] == "西香TJ4标"
    assert text_by_slot["slot-desc"] == "临边防护缺失"
    assert text_by_slot["slot-demand"] == "补齐临边防护"


def test_build_render_plan_keeps_primary_record_id_precedence_over_source_instance_id(tmp_path: Path) -> None:
    row_4 = SourceRecord(
        record_id="range-4",
        document_id="doc-1",
        source_path="/input/source.xlsx",
        cell_range_id="range-4",
        locator={"sheet_name": "Sheet0", "row_index": 4, "cell_range": "A4:Y4"},
        values=[
            _cell_value("项目名称", "西香TJ4标", object_id="range-4", row_index=4, column_index=2),
            _cell_value("隐患描述", "临边防护缺失", object_id="range-4", row_index=4, column_index=10),
            _cell_value("整改要求", "补齐临边防护", object_id="range-4", row_index=4, column_index=12),
        ],
    )
    source_model = SourceModel(records=[_header_record(), _primary_record(), row_4])

    payload = build_render_plan(
        template_model=_template_model(include_missing_owner=False),
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "result.docx"),
        primary_record_id="range-3",
        source_instance_id="sheet_row:doc-1:Sheet0:4",
    )

    plan = render_plan_from_dict(payload)
    text_by_slot = {fill.slot_id: fill.value for fill in plan.text_fills}

    assert plan.record_plans[0].record_id == "range-3"
    assert text_by_slot["slot-project"] == "西香TJ3标"


def test_build_render_plan_falls_back_when_all_records_are_header_like(tmp_path: Path) -> None:
    source_model = SourceModel(records=[_header_record()])

    payload = build_render_plan(
        template_model=_template_model(include_missing_owner=False),
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "result.docx"),
    )

    plan = render_plan_from_dict(payload)

    assert plan.record_plans[0].record_id == "range-header"
    assert any(
        diagnostic.severity == "warning" and diagnostic.code == "primary_record_header_like_fallback"
        for diagnostic in plan.diagnostics
    )


def test_build_render_plan_marks_label_echo_filtered_slots_as_traceable(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="row-label",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 3},
                values=[
                    SourceValue(
                        canonical_key="审批状态",
                        raw_label="审批状态",
                        value="审批状态",
                        provenance=[_provenance(object_id="row-label", row_index=3, column_index=1)],
                    )
                ],
            )
        ]
    )
    template_model = TemplateModel(
        template_id="template-status",
        template_path="/templates/status.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=[
            TemplateSlot(
                slot_id="slot-status",
                raw_name="审批状态",
                canonical_name="审批状态",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    payload = build_render_plan(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "status.docx"),
    )

    plan = render_plan_from_dict(payload)

    assert plan.text_fills == []
    assert [(slot.slot_id, slot.reason_code) for slot in plan.unresolved_slots] == [
        ("slot-status", "label_echo_filtered")
    ]
    assert plan.unresolved_slots[0].candidate_ids == ["row-label:0:label_echo_filtered"]
    assert plan.unresolved_slots[0].provenance_refs
    assert any(diagnostic.code == "label_echo_filtered" and diagnostic.field == "审批状态" for diagnostic in plan.diagnostics)


def test_build_render_plan_marks_cross_row_table_context_mismatch_as_unresolved(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="tblrow-3",
                document_id="doc-1",
                source_path="/input/source.docx",
                table_id="tbl-1",
                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 3},
                values=[
                    SourceValue(
                        canonical_key="项目名称",
                        value="项目A",
                        provenance=[
                            ProvenanceRef(
                                source_kind="table_cell",
                                document_id="doc-1",
                                object_id="tbl-1-r3-c1",
                                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 3, "column_index": 1},
                                source_path="/input/source.docx",
                            )
                        ],
                    )
                ],
            ),
            SourceRecord(
                record_id="tblrow-4",
                document_id="doc-1",
                source_path="/input/source.docx",
                table_id="tbl-1",
                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 4},
                values=[
                    SourceValue(
                        canonical_key="table_text",
                        value="隐患描述：来自另一行的描述",
                        provenance=[
                            ProvenanceRef(
                                source_kind="table_cell",
                                document_id="doc-1",
                                object_id="tbl-1-r4-c2",
                                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 4, "column_index": 2},
                                source_path="/input/source.docx",
                            )
                        ],
                    )
                ],
            ),
        ]
    )

    payload = build_render_plan(
        template_model=_template_model(include_missing_owner=False),
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "result.docx"),
        primary_record_id="tblrow-3",
    )

    plan = render_plan_from_dict(payload)

    assert {fill.slot_id for fill in plan.text_fills} == {"slot-project"}
    unresolved_by_slot = {slot.slot_id: slot for slot in plan.unresolved_slots}
    assert unresolved_by_slot["slot-desc"].reason_code == "cross_slot_source_instance_mismatch"
    assert unresolved_by_slot["slot-desc"].provenance_refs[0].locator["row_index"] == 4
    assert any(
        diagnostic.code == "cross_slot_source_instance_mismatch"
        and diagnostic.field == "隐患描述"
        for diagnostic in plan.diagnostics
    )


def test_build_render_plan_falls_back_to_first_value_record_when_no_row_scoped_record_exists(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.doc",
                evidence_id="ev-1",
                locator={"page_anchor": "page_1"},
                values=[
                    SourceValue(
                        canonical_key="text",
                        value="项目名称：项目C | 隐患描述：高处作业未系安全带 | 整改要求：立即整改",
                        provenance=[
                            ProvenanceRef(
                                source_kind="evidence",
                                document_id="doc-1",
                                object_id="ev-1",
                                locator={"page_anchor": "page_1"},
                                source_path="/input/source.doc",
                            )
                        ],
                    )
                ],
            )
        ]
    )

    payload = build_render_plan(
        template_model=_template_model(include_missing_owner=False),
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "result.docx"),
    )

    plan = render_plan_from_dict(payload)
    text_by_slot = {fill.slot_id: fill.value for fill in plan.text_fills}

    assert plan.record_plans[0].record_id == "ev-1"
    assert text_by_slot["slot-project"] == "项目C"
    assert text_by_slot["slot-desc"] == "高处作业未系安全带"
    assert text_by_slot["slot-demand"] == "立即整改"


def test_build_render_plan_keeps_unscoped_record_context_with_source_instance_index(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-primary",
                document_id="doc-1",
                source_path="/input/source.docx",
                evidence_id="ev-primary",
                locator={"page_anchor": "page_1"},
                values=[
                    SourceValue(
                        canonical_key="text",
                        value="项目名称：项目C",
                        provenance=[
                            ProvenanceRef(
                                source_kind="evidence",
                                document_id="doc-1",
                                object_id="ev-primary",
                                locator={"page_anchor": "page_1"},
                                source_path="/input/source.docx",
                            )
                        ],
                    )
                ],
            ),
            SourceRecord(
                record_id="ev-other",
                document_id="doc-1",
                source_path="/input/source.docx",
                evidence_id="ev-other",
                locator={"page_anchor": "page_2"},
                values=[
                    SourceValue(
                        canonical_key="text",
                        value="隐患描述：来自另一条证据的描述",
                        provenance=[
                            ProvenanceRef(
                                source_kind="evidence",
                                document_id="doc-1",
                                object_id="ev-other",
                                locator={"page_anchor": "page_2"},
                                source_path="/input/source.docx",
                            )
                        ],
                    )
                ],
            ),
        ]
    )
    template_model = TemplateModel(
        template_id="template-narrative",
        template_path="/templates/result.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=[
            TemplateSlot(
                slot_id="slot-desc",
                raw_name="隐患描述",
                canonical_name="隐患描述",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    payload = build_render_plan(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "result.docx"),
        primary_record_id="ev-primary",
        confidence_floor=0.7,
    )

    plan = render_plan_from_dict(payload)

    assert [(fill.slot_id, fill.value) for fill in plan.text_fills] == [
        ("slot-desc", "来自另一条证据的描述")
    ]
    assert plan.unresolved_slots == []


def test_build_render_plan_expands_docx_paragraph_media_region_for_multiple_visual_units(tmp_path: Path) -> None:
    image_one = tmp_path / "parsed" / "checksum-1" / "final_images" / "hazard-1.jpg"
    image_two = tmp_path / "parsed" / "checksum-1" / "final_images" / "hazard-2.jpg"
    image_one.parent.mkdir(parents=True, exist_ok=True)
    image_one.write_bytes(b"img-1")
    image_two.write_bytes(b"img-2")

    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.doc",
                evidence_id="ev-1",
                locator={"page_anchor": "page_1"},
                values=[
                    SourceValue(
                        canonical_key="text",
                        value="发现的隐患问题：围挡未及时封闭；有村民进入施工现场。",
                        raw_label="text",
                    )
                ],
            )
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="asset-1",
                source_ref="final_images/hazard-1.jpg",
                asset_path=str(image_one),
                document_id="doc-1",
                source_path="/input/source.doc",
                page_anchor="page_1",
                order_index=28,
                nearby_text_after=["二工区围挡未及时封闭"],
                nearby_evidence_ids=["ev-1"],
            ),
            SourceImageAsset(
                asset_id="asset-2",
                source_ref="final_images/hazard-2.jpg",
                asset_path=str(image_two),
                document_id="doc-1",
                source_path="/input/source.doc",
                page_anchor="page_1",
                order_index=30,
                nearby_text_after=["有村民进入施工现场"],
                nearby_evidence_ids=["ev-1"],
            ),
        ],
    )
    template_model = TemplateModel(
        template_id="template-docx-repeat",
        template_path="/templates/repeat.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=[
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="隐患照片",
                canonical_name="隐患照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=3),
                repeat_region_id="region-1",
            ),
            TemplateSlot(
                slot_id="slot-photo-desc",
                raw_name="隐患描述",
                canonical_name="隐患描述",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=4),
                repeat_region_id="region-1",
            ),
        ],
        repeat_regions=[
            RepeatRegion(
                region_id="region-1",
                format_key="docx",
                region_kind="docx_paragraph_media_region",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=3),
            )
        ],
    )

    payload = build_render_plan(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "repeat.docx"),
        primary_record_id="ev-1",
    )

    plan = render_plan_from_dict(payload)

    assert [fill.slot_id for fill in plan.text_fills] == ["slot-photo-desc@0", "slot-photo-desc@1"]
    assert [fill.value for fill in plan.text_fills] == ["二工区围挡未及时封闭", "有村民进入施工现场"]
    assert [(fill.target.repeat_region_id, fill.target.instance_index, fill.target.paragraph_index) for fill in plan.text_fills] == [
        ("region-1", 0, 4),
        ("region-1", 1, 4),
    ]
    assert [placement.slot_id for placement in plan.image_placements] == ["slot-photo@0", "slot-photo@1"]
    assert [placement.asset_id for placement in plan.image_placements] == ["asset-1", "asset-2"]
    assert [(placement.target.repeat_region_id, placement.target.instance_index, placement.target.paragraph_index) for placement in plan.image_placements] == [
        ("region-1", 0, 3),
        ("region-1", 1, 3),
    ]
    assert plan.unresolved_slots == []


def test_build_render_plan_uses_structured_row_description_for_xlsx_media_region(tmp_path: Path) -> None:
    image_path = tmp_path / "parsed" / "checksum-1" / "final_images" / "hazard.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"img")

    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="range-1",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 6},
                raw={
                    "parser_signals": {
                        "header_values": [
                            "序号",
                            "项目名称",
                            "隐患描述",
                            "隐患照片",
                            "整改结果描述",
                        ]
                    }
                },
                values=[
                    SourceValue(canonical_key="隐患描述", value="电线杂乱", raw_label="隐患描述"),
                    SourceValue(canonical_key="整改结果描述", value="已整改完成", raw_label="整改结果描述"),
                ],
            )
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="asset-1",
                source_ref="final_images/hazard.jpg",
                asset_path=str(image_path),
                document_id="doc-1",
                source_path="/input/source.xlsx",
                sheet_name="Sheet0",
                row_index=6,
                column_index=4,
                nearby_text_after=[
                    "Sheet=Sheet0 | Range=A8:U8 | 隐患描述=下一行错误描述 | 整改要求=下一行整改"
                ],
                raw={
                    "related_evidence_preview": "Sheet=Sheet0 | Range=A6:X6 | 隐患描述=电线杂乱 | 整改结果描述=已整改完成"
                },
            )
        ],
    )
    template_model = TemplateModel(
        template_id="template-docx-repeat",
        template_path="/templates/repeat.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=[
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="隐患照片",
                canonical_name="隐患照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=3),
                repeat_region_id="region-1",
            ),
            TemplateSlot(
                slot_id="slot-photo-desc",
                raw_name="隐患描述",
                canonical_name="隐患描述",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=4),
                repeat_region_id="region-1",
            ),
        ],
        repeat_regions=[
            RepeatRegion(
                region_id="region-1",
                format_key="docx",
                region_kind="docx_paragraph_media_region",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=3),
            )
        ],
    )

    payload = build_render_plan(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "repeat.docx"),
        primary_record_id="range-1",
    )

    plan = render_plan_from_dict(payload)

    assert [fill.value for fill in plan.text_fills] == ["电线杂乱"]


def test_build_render_plan_surfaces_repeat_region_cluster_hints_without_changing_default_plan_shape(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="row-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 3},
                values=[SourceValue(canonical_key="问题", value="围挡缺失", raw_label="问题")],
            ),
            SourceRecord(
                record_id="row-4",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 4},
                values=[SourceValue(canonical_key="问题", value="临边防护缺失", raw_label="问题")],
            ),
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="img-3",
                source_ref="final_images/row3.jpg",
                asset_path=str(tmp_path / "row3.jpg"),
                document_id="doc-1",
                source_path="/input/source.xlsx",
                sheet_name="Sheet0",
                row_index=3,
            )
        ],
    )
    template_model = TemplateModel(
        template_id="template-docx-repeat",
        template_path="/templates/repeat.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=[
            TemplateSlot(
                slot_id="slot-problem",
                raw_name="问题",
                canonical_name="问题",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=3),
                repeat_region_id="region-1",
            )
        ],
        repeat_regions=[
            RepeatRegion(
                region_id="region-1",
                format_key="docx",
                region_kind="docx_paragraph_text_region",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=3),
            )
        ],
    )

    payload = build_render_plan(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "repeat.docx"),
        primary_record_id="row-3",
        enable_repeat_region_autofill=False,
    )

    plan = render_plan_from_dict(payload)
    hint_diagnostics = [diagnostic for diagnostic in plan.diagnostics if diagnostic.code == "repeat_region_cluster_hint"]

    assert len(plan.record_plans) == 1
    assert plan.record_plans[0].record_id == "row-3"
    assert all(not slot_id.startswith("cluster:") for slot_id in plan.record_plans[0].slot_ids)
    assert hint_diagnostics
    assert hint_diagnostics[0].field == "region-1"
    assert "instance_count=2" in hint_diagnostics[0].message
    assert "record_count=2" in hint_diagnostics[0].message
    assert "asset_count=1" in hint_diagnostics[0].message


def test_build_render_plan_uses_first_data_record_without_domain_bias(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="row-ok",
                document_id="doc-1",
                source_path="/input/source.docx",
                locator={"row_index": 2},
                values=[
                    SourceValue(canonical_key="检查项", value="安全生产标准化总体情况", raw_label="检查项"),
                    SourceValue(canonical_key="检查情况", value="项目资料完整，符合要求。", raw_label="检查情况"),
                ],
            ),
            SourceRecord(
                record_id="row-risk",
                document_id="doc-1",
                source_path="/input/source.docx",
                locator={"row_index": 3},
                values=[
                    SourceValue(canonical_key="检查项", value="临时电箱标准", raw_label="检查项"),
                    SourceValue(canonical_key="检查情况", value="预埋线路未隔20m设置标识牌。", raw_label="检查情况"),
                ],
            ),
        ]
    )
    template_model = TemplateModel(
        template_id="template-risk",
        template_path="/templates/risk.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=[],
    )

    payload = build_render_plan(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "risk.docx"),
    )

    plan = render_plan_from_dict(payload)

    assert plan.plan_id == "template-risk:row-ok"
    assert plan.record_plans[0].record_id == "row-ok"
    assert plan.record_plans[0].slot_ids == []


def test_build_render_plan_does_not_promote_finding_sections_without_template_signal(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-intro",
                document_id="doc-1",
                source_path="/input/source.doc",
                evidence_id="ev-intro",
                locator={"section_title": "关于3月份安全生产大检查情况的通报", "page_anchor": "page_1"},
                values=[
                    SourceValue(
                        canonical_key="text",
                        raw_label="text",
                        value="经检查发现，各作业队在施工过程中存在安全生产隐患和不安全行为。检查基本情况：现场每日按要求开展班前教育。",
                    )
                ],
            ),
            SourceRecord(
                record_id="ev-findings",
                document_id="doc-1",
                source_path="/input/source.doc",
                evidence_id="ev-findings",
                locator={"section_title": "二、发现的隐患问题、负责人及落实整改管理人员", "page_anchor": "page_1"},
                values=[
                    SourceValue(
                        canonical_key="text",
                        raw_label="text",
                        value="（一）龚文升劳务队\n3. 发现的隐患问题：\n（1）二工区围挡未及时封闭；\n三、整改要求\n（一）重新设置倒地的围挡；",
                    )
                ],
            ),
        ]
    )
    template_model = TemplateModel(
        template_id="template-risk-evidence",
        template_path="/templates/risk.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=[],
    )

    payload = build_render_plan(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "outputs" / "risk.docx"),
    )

    plan = render_plan_from_dict(payload)

    assert plan.record_plans[0].record_id == "ev-intro"
