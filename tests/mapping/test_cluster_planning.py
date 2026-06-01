from __future__ import annotations

from doctransai.mapping.cluster_planner import build_source_cluster_plan
from doctransai.models.source import SourceImageAsset, SourceModel, SourceRecord, SourceValue
from doctransai.models.template import RepeatRegion, SlotAddress, TemplateModel, TemplateSlot


def test_build_source_cluster_plan_summarizes_repeat_region_candidate_instances() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="row-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 3},
                values=[SourceValue(canonical_key="隐患描述", value="围挡缺失")],
            ),
            SourceRecord(
                record_id="row-4",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 4},
                values=[SourceValue(canonical_key="隐患描述", value="临边防护缺失")],
            ),
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="img-row-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                sheet_name="Sheet0",
                row_index=3,
                source_ref="final_images/row3.jpg",
            ),
            SourceImageAsset(
                asset_id="img-row-4",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                sheet_name="Sheet0",
                row_index=4,
                source_ref="final_images/row4.jpg",
            ),
        ],
    )
    template_model = TemplateModel(
        template_id="template-repeat",
        template_path="/templates/repeat.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="隐患照片",
                canonical_name="隐患照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
                repeat_region_id="region-1",
            ),
            TemplateSlot(
                slot_id="slot-desc",
                raw_name="隐患描述",
                canonical_name="隐患描述",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=1),
                repeat_region_id="region-1",
            ),
        ],
        repeat_regions=[
            RepeatRegion(
                region_id="region-1",
                format_key="docx",
                region_kind="docx_paragraph_media_region",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    cluster_plan = build_source_cluster_plan(source_model=source_model, template_model=template_model)

    assert len(cluster_plan.clusters) == 1
    cluster = cluster_plan.clusters[0]
    assert cluster.cluster_kind == "sheet"
    assert cluster.record_count == 2
    assert cluster.asset_count == 2
    assert [instance.record_ids for instance in cluster.instances] == [["row-3"], ["row-4"]]
    assert [instance.asset_ids for instance in cluster.instances] == [["img-row-3"], ["img-row-4"]]
    assert len(cluster_plan.repeat_region_plans) == 1
    region_plan = cluster_plan.repeat_region_plans[0]
    assert region_plan.region_id == "region-1"
    assert region_plan.slot_ids == ["slot-photo", "slot-desc"]
    assert region_plan.candidate_cluster_ids == [cluster.cluster_id]
    assert region_plan.instance_count_by_cluster_id == {cluster.cluster_id: 2}


def test_build_source_cluster_plan_keeps_document_records_available_without_repeat_regions() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.pdf",
                locator={"page_anchor": "page_1"},
                values=[SourceValue(canonical_key="text", value="正文片段")],
            )
        ]
    )
    template_model = TemplateModel(
        template_id="template-form",
        template_path="/templates/form.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[],
    )

    cluster_plan = build_source_cluster_plan(source_model=source_model, template_model=template_model)

    assert len(cluster_plan.clusters) == 1
    assert cluster_plan.clusters[0].cluster_kind == "document"
    assert cluster_plan.clusters[0].instances[0].instance_kind == "record"
    assert cluster_plan.repeat_region_plans == []


def test_build_source_cluster_plan_considers_text_only_row_clusters_for_repeat_regions() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="row-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 3},
                values=[SourceValue(canonical_key="问题", value="问题A")],
            ),
            SourceRecord(
                record_id="row-4",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 4},
                values=[SourceValue(canonical_key="问题", value="问题B")],
            ),
        ]
    )
    template_model = TemplateModel(
        template_id="template-repeat",
        template_path="/templates/repeat.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-problem",
                raw_name="问题",
                canonical_name="问题",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
                repeat_region_id="region-1",
            )
        ],
        repeat_regions=[
            RepeatRegion(
                region_id="region-1",
                format_key="docx",
                region_kind="docx_paragraph_text_region",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    cluster_plan = build_source_cluster_plan(source_model=source_model, template_model=template_model)

    assert len(cluster_plan.clusters) == 1
    assert cluster_plan.repeat_region_plans[0].candidate_cluster_ids == [cluster_plan.clusters[0].cluster_id]
    assert cluster_plan.repeat_region_plans[0].instance_count_by_cluster_id == {
        cluster_plan.clusters[0].cluster_id: 2
    }


def test_build_source_cluster_plan_orders_instances_by_row_and_reports_candidate_coverage() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="sheet-b-row-7",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "SheetB", "row_index": 7},
                values=[SourceValue(canonical_key="问题", value="B7")],
            ),
            SourceRecord(
                record_id="sheet-a-row-5",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "SheetA", "row_index": 5},
                values=[SourceValue(canonical_key="问题", value="A5")],
            ),
            SourceRecord(
                record_id="sheet-a-row-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "SheetA", "row_index": 3},
                values=[SourceValue(canonical_key="问题", value="A3")],
            ),
            SourceRecord(
                record_id="sheet-b-row-4",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "SheetB", "row_index": 4},
                values=[SourceValue(canonical_key="问题", value="B4")],
            ),
            SourceRecord(
                record_id="sheet-b-row-2",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "SheetB", "row_index": 2},
                values=[SourceValue(canonical_key="问题", value="B2")],
            ),
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="img-a5",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                sheet_name="SheetA",
                row_index=5,
                source_ref="final_images/a5.jpg",
            ),
            SourceImageAsset(
                asset_id="img-b2",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                sheet_name="SheetB",
                row_index=2,
                source_ref="final_images/b2.jpg",
            ),
            SourceImageAsset(
                asset_id="img-b4",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                sheet_name="SheetB",
                row_index=4,
                source_ref="final_images/b4.jpg",
            ),
        ],
    )
    template_model = TemplateModel(
        template_id="template-repeat",
        template_path="/templates/repeat.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-problem",
                raw_name="问题",
                canonical_name="问题",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
                repeat_region_id="region-1",
            )
        ],
        repeat_regions=[
            RepeatRegion(
                region_id="region-1",
                format_key="docx",
                region_kind="docx_paragraph_text_region",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    cluster_plan = build_source_cluster_plan(source_model=source_model, template_model=template_model)
    clusters_by_container = {cluster.instances[0].instance_id.split(":")[-2]: cluster for cluster in cluster_plan.clusters}

    assert [instance.row_index for instance in clusters_by_container["SheetA"].instances] == [3, 5]
    assert [instance.record_ids for instance in clusters_by_container["SheetA"].instances] == [["sheet-a-row-3"], ["sheet-a-row-5"]]
    assert [instance.row_index for instance in clusters_by_container["SheetB"].instances] == [2, 4, 7]
    assert [instance.asset_ids for instance in clusters_by_container["SheetB"].instances] == [["img-b2"], ["img-b4"], []]

    region_plan = cluster_plan.repeat_region_plans[0]
    assert region_plan.candidate_cluster_ids == [
        clusters_by_container["SheetB"].cluster_id,
        clusters_by_container["SheetA"].cluster_id,
    ]
    assert region_plan.coverage_by_cluster_id == {
        clusters_by_container["SheetB"].cluster_id: {
            "instance_count": 3,
            "record_count": 3,
            "asset_count": 2,
        },
        clusters_by_container["SheetA"].cluster_id: {
            "instance_count": 2,
            "record_count": 2,
            "asset_count": 1,
        },
    }
