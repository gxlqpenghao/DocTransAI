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
from doctransai.reports import build_conversion_report, build_full_agent_context_summary
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
                transform="隐患描述->隐患描述",
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


def test_build_conversion_report_returns_structured_dict_and_markdown() -> None:
    plan = _build_plan()
    render_result = RenderResult(
        output_path="/outputs/result.docx",
        applied_text_slots=["slot-desc"],
        diagnostics=[
            RenderDiagnostic(
                severity="error",
                code="missing_asset",
                message="Asset missing for slot-photo",
                slot_id="slot-photo",
                asset_id="asset-1",
                source_ref="final_images/photo-1.jpg",
            )
        ],
    )
    output_check = OutputCheckResult(
        issues=[
            OutputIssue(
                code="unapplied_image_placement",
                severity="error",
                message="Image placement was not applied for slot slot-photo",
                slot_id="slot-photo",
                asset_id="asset-1",
            )
        ]
    )

    payload, markdown = build_conversion_report(plan, render_result, output_check)

    assert payload["plan_id"] == "plan-1"
    assert payload["status"]["render_successful"] is False
    assert payload["status"]["render_clean"] is False
    assert payload["status"]["review_required"] is True
    assert payload["status"]["blocking_issue"] is True
    assert payload["status"]["output_clean"] is False
    assert payload["fills"][0]["slot_id"] == "slot-desc"
    assert payload["fills"][0]["applied"] is True
    assert payload["fills"][0]["transform"] == "隐患描述->隐患描述"
    assert payload["fills"][0]["decision_kind"] == "rule_candidate"
    assert payload["image_placements"][0]["slot_id"] == "slot-photo"
    assert payload["image_placements"][0]["applied"] is False
    assert payload["unresolved"][0]["slot_id"] == "slot-owner"
    assert [(item["stage"], item["code"]) for item in payload["diagnostics"]] == [
        ("plan", "missing_field"),
        ("render", "missing_asset"),
        ("output_check", "unapplied_image_placement"),
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
    assert "slot-desc" in markdown
    assert "transform=隐患描述->隐患描述" in markdown
    assert "decision_kind=rule_candidate" in markdown
    assert "## Image Placements" in markdown
    assert "slot-photo" in markdown
    assert "## Unresolved" in markdown
    assert "slot-owner" in markdown
    assert "## Diagnostics" in markdown
    assert "missing_asset" in markdown
    assert "## Source Evidence" in markdown
    assert "ev-1" in markdown
    assert json.loads(json.dumps(payload)) == payload


def test_build_conversion_report_explains_agent_fill_decisions_and_reason() -> None:
    plan = RenderPlan(
        plan_id="plan-agent",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/result.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/result.docx", output_format="docx"),
        text_fills=[
            TextFill(
                slot_id="slot-owner",
                target=TargetRef(format_key="docx", target_kind="paragraph", paragraph_index=0, notes="责任单位负责人"),
                value="杨恩赐",
                confidence=0.84,
                transform="agent_selected_candidate",
            ),
            TextFill(
                slot_id="slot-phone",
                target=TargetRef(format_key="docx", target_kind="paragraph", paragraph_index=1, notes="手机号"),
                value="13900139000",
                confidence=0.91,
                transform="agent_generated_value",
            ),
            TextFill(
                slot_id="slot-unknown",
                target=TargetRef(format_key="docx", target_kind="paragraph", paragraph_index=2, notes="其他"),
                value="人工值",
                confidence=0.5,
                transform="manual_override",
            ),
            TextFill(
                slot_id="slot-exact-rule",
                target=TargetRef(format_key="docx", target_kind="paragraph", paragraph_index=3, notes="项目名称"),
                value="西香TJ3标",
                confidence=0.99,
            ),
        ],
        diagnostics=[
            PlanDiagnostic(
                severity="info",
                code="agent_resolved_slot",
                message="Selected first same-row person candidate.",
                field="责任单位负责人",
            ),
            PlanDiagnostic(
                severity="info",
                code="agent_reviewed_slot",
                message="Agent corrected risky same-row typed match.",
                field="手机号",
            ),
        ],
    )
    render_result = RenderResult(
        output_path="/outputs/result.docx",
        applied_text_slots=["slot-owner", "slot-phone", "slot-unknown", "slot-exact-rule"],
    )
    output_check = OutputCheckResult(issues=[])

    payload, markdown = build_conversion_report(plan, render_result, output_check)

    fills = {fill["slot_id"]: fill for fill in payload["fills"]}
    assert fills["slot-owner"]["decision_kind"] == "agent_selected_candidate"
    assert fills["slot-owner"]["transform"] == "agent_selected_candidate"
    assert fills["slot-owner"]["decision_reason"] == "Selected first same-row person candidate."
    assert fills["slot-phone"]["decision_kind"] == "agent_reviewed"
    assert fills["slot-phone"]["transform"] == "agent_generated_value"
    assert fills["slot-phone"]["decision_reason"] == "Agent corrected risky same-row typed match."
    assert fills["slot-phone"]["traceability_status"] == "low_traceability_generated"
    assert fills["slot-phone"]["review_required"] is True
    assert fills["slot-unknown"]["decision_kind"] == "unknown"
    assert fills["slot-exact-rule"]["decision_kind"] == "rule_candidate"
    assert fills["slot-exact-rule"]["transform"] is None
    assert payload["status"]["review_required"] is True
    assert payload["status"]["blocking_issue"] is False
    assert payload["status"]["low_traceability_generated_count"] == 1

    assert "slot-owner: applied=True" in markdown
    assert "decision_kind=agent_selected_candidate" in markdown
    assert "transform=agent_selected_candidate" in markdown
    assert "reason=Selected first same-row person candidate." in markdown
    assert "slot-phone: applied=True" in markdown
    assert "decision_kind=agent_reviewed" in markdown
    assert "reason=Agent corrected risky same-row typed match." in markdown
    assert "slot-unknown: applied=True" in markdown
    assert "decision_kind=unknown" in markdown
    assert "slot-exact-rule: applied=True" in markdown
    assert "transform=None" in markdown


def test_build_conversion_report_accepts_nested_locator_values() -> None:
    plan = _build_plan()
    plan.image_placements[0].provenance_refs[0].locator["nearby_text_after"] = ["二工区围挡未及时封闭"]
    render_result = RenderResult(output_path="/outputs/result.docx", applied_text_slots=["slot-desc"], applied_image_slots=["slot-photo"])
    output_check = OutputCheckResult(issues=[])

    payload, _ = build_conversion_report(plan, render_result, output_check)

    assert payload["source_evidence"][1]["locator"]["nearby_text_after"] == ["二工区围挡未及时封闭"]


def test_build_conversion_report_surfaces_output_quality_diagnostics() -> None:
    plan = _build_plan()
    render_result = RenderResult(output_path="/outputs/result.docx", applied_text_slots=["slot-desc"], applied_image_slots=["slot-photo"])
    output_check = OutputCheckResult(
        issues=[
            OutputIssue(
                code="unsafe_empty_sentence_skeleton",
                severity="error",
                message="Generated prose contains an empty template sentence skeleton.",
                artifact_name="result.docx",
            )
        ]
    )

    payload, markdown = build_conversion_report(plan, render_result, output_check)

    assert payload["status"]["output_clean"] is False
    assert ("output_check", "unsafe_empty_sentence_skeleton") in [
        (item["stage"], item["code"]) for item in payload["diagnostics"]
    ]
    assert "unsafe_empty_sentence_skeleton" in markdown


def test_build_conversion_report_distinguishes_review_required_from_blocking_errors() -> None:
    plan = RenderPlan(
        plan_id="plan-review",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/result.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/result.docx", output_format="docx"),
        unresolved_slots=[
            UnresolvedSlot(
                slot_id="slot-signature",
                canonical_key="总监理工程师",
                reason_code="missing_value",
                message="源文档没有签字信息，保持空白。",
            )
        ],
    )
    render_result = RenderResult(output_path="/outputs/result.docx")
    output_check = OutputCheckResult(
        issues=[
            OutputIssue(
                code="unresolved_slot",
                severity="warning",
                message="源文档没有签字信息，保持空白。",
                slot_id="slot-signature",
            )
        ]
    )

    payload, markdown = build_conversion_report(plan, render_result, output_check)

    assert payload["status"]["render_successful"] is True
    assert payload["status"]["render_clean"] is True
    assert payload["status"]["review_required"] is True
    assert payload["status"]["blocking_issue"] is False
    assert payload["status"]["output_clean"] is False
    assert payload["status"]["issue_counts"] == {
        "error": 0,
        "warning": 1,
        "info": 0,
    }
    assert "Render Clean: True" in markdown
    assert "Review Required: True" in markdown
    assert "Blocking Issue: False" in markdown


def test_build_conversion_report_surfaces_compact_full_agent_context_summary() -> None:
    plan = _build_plan()
    render_result = RenderResult(output_path="/outputs/result.docx", applied_text_slots=["slot-desc"])
    output_check = OutputCheckResult(issues=[])
    summary = {
        "full_agent_context_schema_version": "doctransai_full_agent_context_v1",
        "full_source_record_count": 18,
        "full_source_image_asset_count": 4,
        "full_source_diagnostic_count": 2,
        "records_truncated": False,
        "diagnostics_truncated": True,
        "source_instance_id": "sheet_row:doc-1:Sheet0:3",
        "repeat_region_cluster_hints_present": True,
        "repeat_region_cluster_hint_count": 2,
        "agent_input_estimated_bytes": 6_500_000,
        "agent_input_limit_bytes": 6_000_000,
        "agent_input_estimated_chars": 270_000,
        "agent_input_char_limit": 260_000,
        "agent_input_request_body_exceeded": True,
        "agent_input_length_exceeded": True,
        "agent_input_within_limit": False,
        "agent_input_preflight_blocked": True,
        "agent_input_packaging": {
            "mode": "compact_slot_packets",
            "full_estimated_bytes": 8_100_000,
            "compact_estimated_bytes": 5_900_000,
            "selected_estimated_bytes": 5_900_000,
            "limit_bytes": 6_000_000,
            "full_estimated_chars": 300_000,
            "compact_estimated_chars": 250_000,
            "selected_estimated_chars": 250_000,
            "char_limit": 260_000,
            "request_body_exceeded": False,
            "input_length_exceeded": False,
            "slot_packets_compacted": True,
            "legacy_fields_removed": ["source_document_view", "source_overview"],
            "phase": "initial",
            "within_limit": True,
            "preflight_blocked": False,
        },
    }

    payload, markdown = build_conversion_report(
        plan,
        render_result,
        output_check,
        full_agent_context_summary=summary,
    )

    assert payload["full_agent_context_summary"] == summary
    assert "full_agent_context" not in payload
    assert "## Agent Context" in markdown
    assert "Schema Version: doctransai_full_agent_context_v1" in markdown
    assert "Full Source Records: 18" in markdown
    assert "Repeat Region Cluster Hints: 2" in markdown
    assert "Agent Input Estimated Bytes: 6500000" in markdown
    assert "Agent Input Estimated Chars: 270000" in markdown
    assert "Agent Input Length Exceeded: True" in markdown
    assert "Agent Input Within Limit: False" in markdown
    assert "Agent Input Packaging Mode: compact_slot_packets" in markdown
    assert "Agent Input Selected Estimated Chars: 250000" in markdown
    assert "Slot Packets Compacted: True" in markdown


def test_build_full_agent_context_summary_preserves_structured_packaging_block() -> None:
    full_agent_context = {
        "schema_version": "doctransai_full_agent_context_v1",
        "full_source_context": {
            "record_count": 3,
            "image_asset_count": 1,
            "diagnostic_count": 0,
        },
        "task_context": {"source_instance_id": "sheet_row:doc:Sheet1:3"},
    }

    summary = build_full_agent_context_summary(
        full_agent_context,
        source_overview={"context_status": {"records_truncated": False, "diagnostics_truncated": False}},
        agent_payload_summary={
            "estimated_request_bytes": 5_900_000,
            "max_request_body_bytes": 6_000_000,
            "estimated_input_chars": 250_000,
            "max_input_chars": 260_000,
            "request_body_exceeded": False,
            "input_length_exceeded": False,
            "within_limit": True,
            "preflight_blocked": False,
            "agent_input_packaging": {
                "mode": "compact_slot_packets",
                "full_estimated_bytes": 8_100_000,
                "compact_estimated_bytes": 5_900_000,
                "selected_estimated_bytes": 5_900_000,
                "limit_bytes": 6_000_000,
                "full_estimated_chars": 300_000,
                "compact_estimated_chars": 250_000,
                "selected_estimated_chars": 250_000,
                "char_limit": 260_000,
                "request_body_exceeded": False,
                "input_length_exceeded": False,
                "slot_packets_compacted": True,
                "legacy_fields_removed": ["source_document_view"],
                "phase": "initial",
                "within_limit": True,
                "preflight_blocked": False,
            },
        },
    )

    assert summary["agent_input_estimated_bytes"] == 5_900_000
    assert summary["agent_input_estimated_chars"] == 250_000
    assert summary["agent_input_length_exceeded"] is False
    assert summary["agent_input_packaging"]["mode"] == "compact_slot_packets"
    assert summary["agent_input_packaging"]["selected_estimated_chars"] == 250_000
    assert summary["agent_input_packaging"]["legacy_fields_removed"] == ["source_document_view"]
