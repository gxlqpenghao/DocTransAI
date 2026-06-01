from __future__ import annotations

from doctransai.mapping.full_agent_context import build_full_agent_context
from doctransai.models.source import (
    ProvenanceRef,
    SourceDocument,
    SourceImageAsset,
    SourceModel,
    SourceRecord,
    SourceValue,
)
from doctransai.models.template import HeaderDrivenRegion, RepeatRegion, SlotAddress, TemplateModel, TemplateSlot


def test_build_full_agent_context_preserves_complete_structured_source_and_template_views() -> None:
    source_model = SourceModel(
        documents=[
            SourceDocument(
                document_id="doc-1",
                source_path="/input/source.docx",
                doc_type="docx",
                document_title="检查通报",
                source_checksum="sha256:source",
                parser_name="dataproxy-fresh",
            )
        ],
        records=[
            SourceRecord(
                record_id="record-1",
                document_id="doc-1",
                source_path="/input/source.docx",
                evidence_id="ev-1",
                locator={"page_anchor": "page_1", "bbox": [1, 2, 3, 4]},
                values=[
                    SourceValue(
                        canonical_key="隐患描述",
                        raw_label="问题",
                        value="围挡未封闭",
                        value_type="text",
                        confidence_base=0.91,
                        provenance=[
                            ProvenanceRef(
                                source_kind="evidence",
                                document_id="doc-1",
                                evidence_id="ev-1",
                                locator={"page_anchor": "page_1"},
                                source_path="/input/source.docx",
                            )
                        ],
                    )
                ],
            ),
            SourceRecord(
                record_id="record-2",
                document_id="doc-1",
                source_path="/input/source.docx",
                evidence_id="ev-2",
                locator={"page_anchor": "page_2"},
                values=[SourceValue(canonical_key="整改要求", raw_label="要求", value="补齐围挡")],
            ),
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="asset-1",
                document_id="doc-1",
                source_path="/input/source.docx",
                source_ref="final_images/image1.jpeg",
                page_anchor="page_1",
                bbox=[10, 20, 80, 120],
                related_evidence_ids=["ev-1"],
                nearby_text_after=["围挡未封闭现场照片"],
            )
        ],
        diagnostics=[{"severity": "warning", "code": "weak_caption", "asset_id": "asset-1"}],
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/output.docx",
        format_key="docx",
        analyzer_key="p1b",
        slots=[
            TemplateSlot(
                slot_id="slot-desc",
                raw_name="隐患描述",
                canonical_name="隐患描述",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="placeholder", paragraph_index=0),
                context_before="安全问题：",
                repeat_region_id="region-1",
                style_ref="style-1",
            ),
            TemplateSlot(
                slot_id="slot-image",
                raw_name="隐患照片",
                canonical_name="隐患照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="image_placeholder", paragraph_index=1),
                placement_constraints={"max_width_px": 320},
            ),
        ],
        repeat_regions=[
            RepeatRegion(
                region_id="region-1",
                format_key="docx",
                region_kind="docx_paragraph_text_region",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
        header_regions=[
            HeaderDrivenRegion(
                region_id="header-1",
                format_key="xlsx",
                sheet_name="Sheet1",
                header_row_index=1,
                column_names=["隐患描述", "整改要求"],
                sample_row_index=2,
            )
        ],
    )

    context = build_full_agent_context(
        source_model=source_model,
        primary_record=source_model.records[0],
        template_model=template_model,
        template_slots_by_id={slot.slot_id: slot for slot in template_model.slots},
        source_document_view="record-1: 围挡未封闭\nrecord-2: 补齐围挡",
        source_instance_overview={"primary_record_id": "record-1"},
        source_cluster_plan={"clusters": [{"cluster_id": "cluster-1"}]},
        task_context={"resolution_mode": "unresolved", "slot_ids": ["slot-desc"]},
    )

    assert context["schema_version"] == "doctransai_full_agent_context_v1"
    assert context["full_source_context"]["record_count"] == 2
    assert [record["record_id"] for record in context["full_source_context"]["records"]] == ["record-1", "record-2"]
    assert context["full_source_context"]["records"][0]["values"][0]["provenance"][0]["evidence_id"] == "ev-1"
    assert context["full_source_context"]["image_assets"][0]["related_evidence_ids"] == ["ev-1"]
    assert context["full_source_context"]["object_index"] == {
        "by_object_key": {
            "record:record-1": {
                "object_kind": "record",
                "object_id": "record-1",
                "collection": "records",
                "index": 0,
            },
            "record:record-2": {
                "object_kind": "record",
                "object_id": "record-2",
                "collection": "records",
                "index": 1,
            },
            "image_asset:asset-1": {
                "object_kind": "image_asset",
                "object_id": "asset-1",
                "collection": "image_assets",
                "index": 0,
            },
        }
    }
    assert context["full_source_context"]["diagnostics"][0]["code"] == "weak_caption"
    assert context["full_template_context"]["slot_count"] == 2
    assert context["full_template_context"]["slots"][1]["placement_constraints"] == {"max_width_px": 320}
    assert context["full_template_context"]["repeat_regions"][0]["region_id"] == "region-1"
    assert context["navigation_context"]["source_instance_overview"] == {"primary_record_id": "record-1"}
    assert context["navigation_context"]["source_cluster_plan"] == {"clusters": [{"cluster_id": "cluster-1"}]}
    assert context["navigation_context"]["authority"] == "navigation_only_not_evidence"
    assert context["task_context"] == {"resolution_mode": "unresolved", "slot_ids": ["slot-desc"]}


def test_build_full_agent_context_adds_repeat_region_cluster_hints_to_task_context() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="row-1",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 1},
                values=[SourceValue(canonical_key="问题", value="围挡缺失")],
            )
        ]
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/output.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[],
    )

    context = build_full_agent_context(
        source_model=source_model,
        primary_record=source_model.records[0],
        template_model=template_model,
        template_slots_by_id={},
        source_document_view="row-1: 围挡缺失",
        source_instance_overview=None,
        source_cluster_plan={
            "repeat_regions": [
                {
                    "region_id": "region-1",
                    "candidate_cluster_ids": ["cluster-1"],
                    "coverage_by_cluster_id": {
                        "cluster-1": {
                            "instance_count": 2,
                            "record_count": 2,
                            "asset_count": 1,
                        }
                    },
                }
            ]
        },
        task_context={"primary_record_id": "row-1"},
    )

    assert context["task_context"]["repeat_region_cluster_hints"] == [
        {
            "region_id": "region-1",
            "candidate_cluster_ids": ["cluster-1"],
            "coverage_by_cluster_id": {
                "cluster-1": {
                    "instance_count": 2,
                    "record_count": 2,
                    "asset_count": 1,
                }
            },
        }
    ]
