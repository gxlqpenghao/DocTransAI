from __future__ import annotations

from dataclasses import dataclass

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
    assert unresolved.canonical_key == "missing"
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
