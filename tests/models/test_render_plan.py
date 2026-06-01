from __future__ import annotations

from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import (
    ImagePlacement,
    OutputRef,
    PlanDiagnostic,
    RenderPlan,
    TargetRef,
    TemplateRef,
    TextFill,
    render_plan_from_dict,
    render_plan_to_dict,
)
from doctransai.models.source import ProvenanceRef


def test_render_plan_round_trip_preserves_provenance() -> None:
    evidence_ref = ProvenanceRef(
        source_kind="evidence",
        document_id="doc-1",
        evidence_id="ev-1",
        object_id="range-1",
        locator={"sheet_name": "Sheet0", "cell_range": "A3:Y3"},
        source_path="/input/source.xlsx",
    )
    asset_ref = ProvenanceRef(
        source_kind="asset",
        document_id="doc-1",
        asset_id="asset-1",
        object_id="asset-1",
        locator={"sheet_name": "Sheet0", "cell_anchor": "K3"},
        source_path="/input/source.xlsx",
    )
    plan = RenderPlan(
        plan_id="plan-1",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(
            template_path="/templates/record.docx",
            format_key="docx",
        ),
        output=OutputRef(
            output_path="/outputs/record.docx",
            output_format="docx",
        ),
        text_fills=[
            TextFill(
                slot_id="slot-desc",
                target=TargetRef(
                    format_key="docx",
                    target_kind="placeholder",
                    table_index=0,
                    row_index=1,
                    column_index=1,
                    cell_paragraph_index=1,
                ),
                value="隐患描述",
                provenance_refs=[evidence_ref],
                confidence=0.92,
            )
        ],
        image_placements=[
            ImagePlacement(
                slot_id="slot-image",
                asset_id="asset-1",
                source_ref="final_images/image1.jpeg",
                target=TargetRef(format_key="docx", target_kind="image_placeholder", table_index=0, row_index=3, column_index=1),
                provenance_refs=[asset_ref],
                sizing_policy="contain",
            )
        ],
        unresolved_slots=[
            UnresolvedSlot(
                slot_id="slot-owner",
                canonical_key="责任单位负责人",
                reason_code="missing_value",
                message="没有找到负责人字段",
                provenance_refs=[],
            )
        ],
        diagnostics=[
            PlanDiagnostic(
                severity="warning",
                code="missing_field",
                message="部分字段未解析",
                field="责任单位负责人",
            )
        ],
        created_at="2026-05-21T10:00:00Z",
    )

    payload = render_plan_to_dict(plan)
    restored = render_plan_from_dict(payload)

    assert restored == plan
    assert render_plan_to_dict(restored) == payload


def test_render_plan_round_trip_preserves_repeat_region_target_fields() -> None:
    plan = RenderPlan(
        plan_id="plan-repeat",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/template.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/result.docx", output_format="docx"),
        text_fills=[
            TextFill(
                slot_id="slot-desc@1",
                target=TargetRef(
                    format_key="docx",
                    target_kind="placeholder",
                    paragraph_index=4,
                    notes="隐患描述",
                    repeat_region_id="region-1",
                    instance_index=1,
                ),
                value="有村民进入施工现场",
            )
        ],
        image_placements=[],
        created_at="2026-05-25T10:00:00Z",
    )

    payload = render_plan_to_dict(plan)
    restored = render_plan_from_dict(payload)

    assert restored.text_fills[0].target.repeat_region_id == "region-1"
    assert restored.text_fills[0].target.instance_index == 1
