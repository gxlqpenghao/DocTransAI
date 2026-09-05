from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docx import Document
from openpyxl import Workbook

from doctransai.agentic_mapping.assembler import assemble_render_plan_from_decisions
from doctransai.agentic_mapping.decisions import AgentDecision
from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import ImagePlacement, RenderPlan, TextFill, render_plan_to_dict
from doctransai.models.template import SlotAddress, TemplateModel, TemplateSlot


@dataclass(slots=True)
class DecisionFixture:
    slot_id: str
    decision: str
    reason: str
    source_refs: list[object]
    accepted: bool = True
    value: str | None = None
    asset_id: str | None = None
    source_ref: str | None = None
    target_ref: dict[str, object] | None = None


def test_assemble_render_plan_builds_text_image_and_unresolved_entries() -> None:
    template = _template_model()
    decisions = [
        {
            "slot_id": "slot-project",
            "decision": "text_fill",
            "value": "智慧园区改造",
            "confidence": 0.91,
            "target_ref": {
                "format_key": "docx",
                "target_kind": "placeholder",
                "paragraph_index": 3,
            },
            "source_refs": [
                "record/project-name",
                {
                    "source_kind": "record",
                    "document_id": "source-doc",
                    "object_id": "record-1",
                    "locator": {"page_index": 0},
                },
            ],
        },
        DecisionFixture(
            slot_id="slot-photo",
            decision="image_placement",
            asset_id="asset-1",
            source_ref="/tmp/photo.png",
            reason="source image nearby text matches template photo slot",
            source_refs=["asset/asset-1"],
        ),
        {
            "slot_id": "slot-missing",
            "decision": "unresolved",
            "reason_code": "missing_source_evidence",
            "message": "No source fact supports this slot.",
            "candidate_ids": ["cand-1"],
            "source_refs": [],
        },
        {
            "slot_id": "slot-rejected",
            "decision": "text_fill",
            "accepted": False,
            "value": "should not be assembled",
            "source_refs": ["record/rejected"],
        },
    ]

    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=template,
        output_path="/outputs/result.docx",
        decisions=decisions,
    )

    assert isinstance(plan, RenderPlan)
    assert plan.source_bundle_path == "/bundles/source.json"
    assert plan.template.template_id == "template-1"
    assert plan.output.output_format == "docx"
    assert [type(item) for item in plan.text_fills] == [TextFill]
    assert [type(item) for item in plan.image_placements] == [ImagePlacement]
    assert [type(item) for item in plan.unresolved_slots] == [UnresolvedSlot]

    text_fill = plan.text_fills[0]
    assert text_fill.slot_id == "slot-project"
    assert text_fill.value == "智慧园区改造"
    assert text_fill.target.paragraph_index == 3
    assert text_fill.provenance_refs[0].source_kind == "agentic_ref"
    assert text_fill.provenance_refs[0].object_id == "record/project-name"
    assert text_fill.provenance_refs[1].source_kind == "record"

    image_placement = plan.image_placements[0]
    assert image_placement.slot_id == "slot-photo"
    assert image_placement.asset_id == "asset-1"
    assert image_placement.source_ref == "/tmp/photo.png"
    assert image_placement.target.target_kind == "image_placeholder"
    assert image_placement.target.paragraph_index == 8

    unresolved = plan.unresolved_slots[0]
    assert unresolved.slot_id == "slot-missing"
    assert unresolved.canonical_key == "缺失字段"
    assert unresolved.reason_code == "missing_source_evidence"
    assert unresolved.candidate_ids == ["cand-1"]

    payload = render_plan_to_dict(plan)
    assert payload["text_fills"][0]["provenance_refs"][0]["source_kind"] == "agentic_ref"
    assert len(payload["text_fills"]) == 1


def test_assemble_render_plan_uses_template_slot_address_when_target_ref_is_absent() -> None:
    template = _template_model()

    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=template,
        output_path="/outputs/result.docx",
        decisions=[
            {
                "slot_id": "slot-project",
                "decision": "text_fill",
                "value": "安全检查",
                "source_refs": ["record/project"],
            }
        ],
    )

    assert plan.text_fills[0].target.target_kind == "placeholder"
    assert plan.text_fills[0].target.paragraph_index == 2


def test_assemble_render_plan_keeps_agent_render_intent_fields() -> None:
    template = _template_model()

    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=template,
        output_path="/outputs/result.docx",
        decisions=[
            AgentDecision(
                slot_id="slot-project",
                decision_type="text_fill",
                value="2026-05-14",
                source_refs=["source_value:record-1:0"],
                value_type="date",
                transform="date_only",
            ),
            AgentDecision(
                slot_id="slot-photo",
                decision_type="image_placement",
                asset_ref="asset-1",
                source_ref="/tmp/photo.png",
                source_refs=["image_asset:asset-1"],
                sizing_policy="cover",
                caption="现场照片",
                caption_slot_id="slot-project",
                caption_target={
                    "format_key": "docx",
                    "target_kind": "placeholder",
                    "paragraph_index": 3,
                },
            ),
        ],
    )

    assert plan.text_fills[0].value_type == "date"
    assert plan.text_fills[0].transform == "date_only"
    assert plan.image_placements[0].sizing_policy == "cover"
    assert plan.image_placements[0].caption == "现场照片"
    assert plan.image_placements[0].caption_slot_id == "slot-project"
    assert plan.image_placements[0].caption_target is not None
    assert plan.image_placements[0].caption_target.paragraph_index == 3
    assert plan.text_fills[0].target.notes == "项目名称"


def test_assemble_render_plan_resolves_template_slot_object_target_ref() -> None:
    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=_template_model(),
        output_path="/outputs/result.docx",
        decisions=[
            {
                "slot_id": "slot-project",
                "decision": "text_fill",
                "value": "安全检查",
                "source_refs": ["record/project"],
                "target_ref": {"object_ref": "template_slot:slot-project"},
            }
        ],
    )

    assert plan.text_fills[0].target.target_kind == "placeholder"
    assert plan.text_fills[0].target.paragraph_index == 2
    assert plan.text_fills[0].target.notes == "项目名称"


def test_assemble_render_plan_falls_back_to_slot_address_for_incomplete_target_ref() -> None:
    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=_template_model(),
        output_path="/outputs/result.docx",
        decisions=[
            {
                "slot_id": "slot-project",
                "decision": "text_fill",
                "value": "安全检查",
                "source_refs": ["record/project"],
                "target_ref": {"row": 2, "column": 1},
            }
        ],
    )

    assert plan.text_fills[0].target.target_kind == "placeholder"
    assert plan.text_fills[0].target.paragraph_index == 2


def test_assemble_render_plan_accepts_agent_decision_defaults() -> None:
    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=_template_model(),
        output_path="/outputs/result.docx",
        decisions=[
            AgentDecision(
                slot_id="slot-missing",
                decision_type="unresolved",
                reason="No source evidence.",
            )
        ],
    )

    assert plan.unresolved_slots[0].slot_id == "slot-missing"
    assert plan.unresolved_slots[0].candidate_ids == []
    assert plan.unresolved_slots[0].provenance_refs == []


def test_assemble_render_plan_resolves_docx_visual_text_anchor_to_paragraph(tmp_path: Path) -> None:
    template_path = tmp_path / "visual-anchor-template.docx"
    document = Document()
    document.add_paragraph("接收人（签字）：            接收日期：    年   月   日   时     编号：")
    document.save(template_path)

    template = TemplateModel(
        template_id="template-visual",
        template_path=str(template_path),
        format_key="docx",
        analyzer_key="test",
    )

    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=template,
        output_path="/outputs/result.docx",
        decisions=[
            {
                "slot_id": "visual-target-编号",
                "decision": "text_fill",
                "value": "LQ-2026-001",
                "source_refs": ["record:notice"],
                "visual_target": {
                    "format_key": "docx",
                    "target_kind": "visual_text_anchor",
                    "label_or_nearby_text": "编号",
                    "page_index": 0,
                },
            }
        ],
    )

    assert plan.text_fills[0].target.target_kind == "visual_text_anchor"
    assert plan.text_fills[0].target.paragraph_index == 0
    assert plan.text_fills[0].target.notes == "编号"


def test_assemble_render_plan_resolves_xlsx_visual_text_anchor_to_adjacent_blank_cell(tmp_path: Path) -> None:
    template_path = tmp_path / "visual-anchor-template.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    worksheet["A1"] = "编号"
    worksheet["B1"] = None
    workbook.save(template_path)

    template = TemplateModel(
        template_id="template-visual-xlsx",
        template_path=str(template_path),
        format_key="xlsx",
        analyzer_key="test",
    )

    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=template,
        output_path="/outputs/result.xlsx",
        decisions=[
            {
                "slot_id": "visual-target-编号",
                "decision": "text_fill",
                "value": "LQ-2026-001",
                "source_refs": ["record:notice"],
                "visual_target": {
                    "format_key": "xlsx",
                    "target_kind": "visual_text_anchor",
                    "label_or_nearby_text": "编号",
                    "page_index": 0,
                },
            }
        ],
    )

    assert plan.text_fills[0].target.format_key == "xlsx"
    assert plan.text_fills[0].target.target_kind == "cell"
    assert plan.text_fills[0].target.sheet_name == "Sheet1"
    assert plan.text_fills[0].target.cell_ref == "B1"
    assert plan.text_fills[0].target.notes == "编号"


def test_assemble_render_plan_recovers_repeat_suffix_target_from_existing_slot() -> None:
    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=_template_model(),
        output_path="/outputs/result.docx",
        decisions=[
            {
                "slot_id": "slot-photo-repeat-1",
                "decision": "image_placement",
                "asset_id": "asset-2",
                "source_ref": "/tmp/photo2.png",
                "source_refs": ["image_asset:asset-2"],
            }
        ],
    )

    assert plan.image_placements[0].slot_id == "slot-photo-repeat-1"
    assert plan.image_placements[0].target.target_kind == "image_placeholder"
    assert plan.image_placements[0].target.paragraph_index == 8
    assert plan.image_placements[0].target.notes == "现场照片"


def test_assemble_render_plan_expands_repeat_region_multi_value_decisions() -> None:
    template = TemplateModel(
        template_id="template-repeat",
        template_path="/templates/repeat.docx",
        format_key="docx",
        analyzer_key="test",
        slots=[
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="隐患照片",
                canonical_name="hazard_photo",
                slot_kind="image",
                repeat_region_id="region-1",
                placement_constraints={
                    "multi_value_allowed": True,
                    "media_group_role": "image",
                    "paired_caption_slot_id": "slot-desc",
                },
                address=SlotAddress(format_key="docx", address_kind="image_placeholder", paragraph_index=1),
            ),
            TemplateSlot(
                slot_id="slot-desc",
                raw_name="隐患描述",
                canonical_name="hazard_description",
                slot_kind="text",
                repeat_region_id="region-1",
                placement_constraints={
                    "multi_value_allowed": True,
                    "media_group_role": "caption",
                    "paired_image_slot_id": "slot-photo",
                },
                address=SlotAddress(format_key="docx", address_kind="placeholder", paragraph_index=2),
            ),
        ],
    )

    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=template,
        output_path="/outputs/result.docx",
        evidence_package={
            "source": {
                "structured": {
                    "object_index": {
                        "image_asset:img-1": {"object_type": "image_asset", "asset_id": "img-1", "source_ref": "images/one.jpg"},
                        "image_asset:img-2": {"object_type": "image_asset", "asset_id": "img-2", "source_ref": "images/two.jpg"},
                    },
                    "image_assets": [
                        {"asset_id": "img-1", "source_ref": "images/one.jpg", "nearby_text_after": ["二工区围挡未及时封闭"]},
                        {"asset_id": "img-2", "source_ref": "images/two.jpg", "nearby_text_after": ["有村民进入施工现场"]},
                    ],
                }
            }
        },
        decisions=[
            {
                "slot_id": "slot-photo",
                "decision": "image_placement",
                "asset_id": "img-1",
                "source_ref": "images/one.jpg",
                "source_refs": ["image_asset:img-1", "image_asset:img-2"],
                "candidate_ids": ["img-1", "img-2"],
            },
            {
                "slot_id": "slot-desc",
                "decision": "text_fill",
                "value": "二工区围挡未及时封闭\n有村民进入施工现场",
                "source_refs": ["record:ev-1"],
            },
        ],
    )

    assert [(placement.slot_id, placement.asset_id, placement.source_ref, placement.target.instance_index) for placement in plan.image_placements] == [
        ("slot-photo@0", "img-1", "images/one.jpg", 0),
        ("slot-photo@1", "img-2", "images/two.jpg", 1),
    ]
    assert [(fill.slot_id, fill.value, fill.target.instance_index) for fill in plan.text_fills] == [
        ("slot-desc@0", "二工区围挡未及时封闭", 0),
        ("slot-desc@1", "有村民进入施工现场", 1),
    ]


def test_assemble_render_plan_expands_multi_value_images_in_same_table_cell() -> None:
    template = TemplateModel(
        template_id="template-cell-multi-image",
        template_path="/templates/reply.docx",
        format_key="docx",
        analyzer_key="test",
        slots=[
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="隐患照片",
                canonical_name="hazard_photo",
                slot_kind="image",
                placement_constraints={"multi_value_allowed": True},
                address=SlotAddress(
                    format_key="docx",
                    address_kind="table_cell",
                    table_index=0,
                    row_index=0,
                    column_index=2,
                    cell_paragraph_index=0,
                ),
            )
        ],
    )

    plan = assemble_render_plan_from_decisions(
        source_bundle_path="/bundles/source.json",
        template_model=template,
        output_path="/outputs/result.docx",
        evidence_package={
            "source": {
                "structured": {
                    "object_index": {
                        "image_asset:img-1": {"object_type": "image_asset", "asset_id": "img-1", "source_ref": "images/one.jpg"},
                        "image_asset:img-2": {"object_type": "image_asset", "asset_id": "img-2", "source_ref": "images/two.jpg"},
                    }
                }
            }
        },
        decisions=[
            {
                "slot_id": "slot-photo",
                "decision": "image_placement",
                "asset_id": "img-1",
                "source_ref": "images/one.jpg",
                "source_refs": ["image_asset:img-1", "image_asset:img-2"],
                "candidate_ids": ["img-1", "img-2"],
            }
        ],
    )

    assert [(placement.slot_id, placement.asset_id, placement.source_ref, placement.target.instance_index) for placement in plan.image_placements] == [
        ("slot-photo@0", "img-1", "images/one.jpg", None),
        ("slot-photo@1", "img-2", "images/two.jpg", None),
    ]


def _template_model() -> TemplateModel:
    return TemplateModel(
        template_id="template-1",
        template_path="/templates/template.docx",
        format_key="docx",
        analyzer_key="test",
        slots=[
            TemplateSlot(
                slot_id="slot-project",
                raw_name="项目名称",
                canonical_name="project_name",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="placeholder", paragraph_index=2),
            ),
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="现场照片",
                canonical_name="photo",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="image_placeholder", paragraph_index=8),
            ),
            TemplateSlot(
                slot_id="slot-missing",
                raw_name="缺失字段",
                canonical_name="missing",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="placeholder", paragraph_index=12),
            ),
        ],
    )
