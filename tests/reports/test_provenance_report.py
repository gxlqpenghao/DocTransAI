from __future__ import annotations

import json

from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import (
    ImagePlacement,
    OutputRef,
    PlanDiagnostic,
    RenderPlan,
    TargetRef,
    TemplateRef,
    TextFill,
)
from doctransai.models.source import ProvenanceRef
from doctransai.renderers import RenderDiagnostic, RenderResult
from doctransai.reports import build_provenance_report
from doctransai.validation import OutputCheckResult, OutputIssue


def _build_plan() -> RenderPlan:
    evidence_ref = ProvenanceRef(
        source_kind="evidence",
        document_id="doc-1",
        evidence_id="ev-1",
        object_id="range-3",
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
    return RenderPlan(
        plan_id="plan-1",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/result.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/result.docx", output_format="docx"),
        text_fills=[
            TextFill(
                slot_id="slot-desc",
                target=TargetRef(format_key="docx", target_kind="placeholder", paragraph_index=1),
                value="右幅作业人员安全带缺少缓冲包",
                provenance_refs=[evidence_ref],
                confidence=0.92,
            )
        ],
        image_placements=[
            ImagePlacement(
                slot_id="slot-photo",
                asset_id="asset-1",
                source_ref="final_images/photo-1.jpg",
                target=TargetRef(format_key="docx", target_kind="image_placeholder", paragraph_index=2),
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
                provenance_refs=[evidence_ref],
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
        created_at="2026-05-21T12:00:00Z",
    )


def test_build_provenance_report_returns_slot_level_evidence_views() -> None:
    plan = _build_plan()
    render_result = RenderResult(
        output_path="/outputs/result.docx",
        applied_text_slots=["slot-desc"],
        applied_image_slots=["slot-photo"],
        diagnostics=[
            RenderDiagnostic(
                severity="warning",
                code="image_downscaled",
                message="Image was resized to fit the target box",
                slot_id="slot-photo",
                asset_id="asset-1",
                source_ref="final_images/photo-1.jpg",
            )
        ],
    )
    output_check = OutputCheckResult(
        issues=[
            OutputIssue(
                code="unresolved_slot",
                severity="warning",
                message="没有找到负责人字段",
                slot_id="slot-owner",
            )
        ]
    )

    payload, markdown = build_provenance_report(plan, render_result, output_check)

    assert payload["plan_id"] == "plan-1"
    assert payload["fills"] == [
        {
            "slot_id": "slot-desc",
            "value": "右幅作业人员安全带缺少缓冲包",
            "value_type": "text",
            "confidence": 0.92,
            "target": {
                "format_key": "docx",
                "target_kind": "placeholder",
                "paragraph_index": 1,
                "cell_paragraph_index": None,
                "table_index": None,
                "row_index": None,
                "column_index": None,
                "sheet_name": None,
                "cell_ref": None,
                "page_index": None,
                "form_field_name": None,
                "bbox": None,
                "run_index": None,
                "run_end_index": None,
                "notes": None,
                "allow_same_name_residual_fill": False,
            },
            "source_evidence": [
                {
                    "source_kind": "evidence",
                    "document_id": "doc-1",
                    "evidence_id": "ev-1",
                    "asset_id": None,
                    "object_id": "range-3",
                    "source_path": "/input/source.xlsx",
                    "locator": {"sheet_name": "Sheet0", "cell_range": "A3:Y3"},
                }
            ],
        }
    ]
    assert payload["image_placements"] == [
        {
            "slot_id": "slot-photo",
            "asset_id": "asset-1",
            "source_ref": "final_images/photo-1.jpg",
            "target": {
                "format_key": "docx",
                "target_kind": "image_placeholder",
                "paragraph_index": 2,
                "cell_paragraph_index": None,
                "table_index": None,
                "row_index": None,
                "column_index": None,
                "sheet_name": None,
                "cell_ref": None,
                "page_index": None,
                "form_field_name": None,
                "bbox": None,
                "run_index": None,
                "run_end_index": None,
                "notes": None,
                "allow_same_name_residual_fill": False,
            },
            "sizing_policy": "contain",
            "caption": None,
            "source_evidence": [
                {
                    "source_kind": "asset",
                    "document_id": "doc-1",
                    "evidence_id": None,
                    "asset_id": "asset-1",
                    "object_id": "asset-1",
                    "source_path": "/input/source.xlsx",
                    "locator": {"sheet_name": "Sheet0", "cell_anchor": "K3"},
                }
            ],
        }
    ]
    assert payload["unresolved"] == [
        {
            "slot_id": "slot-owner",
            "canonical_key": "责任单位负责人",
            "reason_code": "missing_value",
            "message": "没有找到负责人字段",
            "candidate_ids": [],
            "source_evidence": [
                {
                    "source_kind": "evidence",
                    "document_id": "doc-1",
                    "evidence_id": "ev-1",
                    "asset_id": None,
                    "object_id": "range-3",
                    "source_path": "/input/source.xlsx",
                    "locator": {"sheet_name": "Sheet0", "cell_range": "A3:Y3"},
                }
            ],
        }
    ]
    assert [(item["stage"], item["code"]) for item in payload["diagnostics"]] == [
        ("plan", "missing_field"),
        ("render", "image_downscaled"),
        ("output_check", "unresolved_slot"),
    ]
    assert payload["source_evidence"] == [
        {
            "source_kind": "evidence",
            "document_id": "doc-1",
            "evidence_id": "ev-1",
            "asset_id": None,
            "object_id": "range-3",
            "source_path": "/input/source.xlsx",
            "locator": {"sheet_name": "Sheet0", "cell_range": "A3:Y3"},
            "slots": ["slot-desc", "slot-owner"],
        },
        {
            "source_kind": "asset",
            "document_id": "doc-1",
            "evidence_id": None,
            "asset_id": "asset-1",
            "object_id": "asset-1",
            "source_path": "/input/source.xlsx",
            "locator": {"sheet_name": "Sheet0", "cell_anchor": "K3"},
            "slots": ["slot-photo"],
        },
    ]
    assert "## Fills" in markdown
    assert "Sheet0" in markdown
    assert "## Image Placements" in markdown
    assert "final_images/photo-1.jpg" in markdown
    assert "## Unresolved" in markdown
    assert "责任单位负责人" in markdown
    assert "## Diagnostics" in markdown
    assert "image_downscaled" in markdown
    assert "## Source Evidence" in markdown
    assert "slot-owner" in markdown
    assert json.loads(json.dumps(payload)) == payload


def test_build_provenance_report_marks_generated_values_with_low_traceability() -> None:
    plan = RenderPlan(
        plan_id="plan-generated",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/result.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/result.docx", output_format="docx"),
        text_fills=[
            TextFill(
                slot_id="slot-summary",
                target=TargetRef(format_key="docx", target_kind="placeholder", paragraph_index=1),
                value="综合全文生成的成果简介",
                provenance_refs=[
                    ProvenanceRef(
                        source_kind="generated",
                        document_id="doc-1",
                        object_id="record-1",
                        locator={"page_index": 0},
                        source_path="/input/source.pdf",
                    )
                ],
                confidence=0.74,
                transform="agent_generated_value",
            )
        ],
    )
    render_result = RenderResult(output_path="/outputs/result.docx", applied_text_slots=["slot-summary"])
    output_check = OutputCheckResult(issues=[])

    payload, markdown = build_provenance_report(plan, render_result, output_check)

    assert payload["fills"][0]["traceability_status"] == "low_traceability_generated"
    assert payload["fills"][0]["review_required"] is True
    assert "low_traceability_generated" in markdown
