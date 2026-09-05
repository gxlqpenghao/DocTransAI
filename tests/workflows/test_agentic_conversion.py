from __future__ import annotations

import json
from pathlib import Path

import doctransai.workflows.agentic_conversion as workflow_module
from docx import Document

from doctransai.agentic_mapping.decisions import AgentDecision
from doctransai.agentic_mapping.validator import ValidationResult
from doctransai.llm.client import DoctransaiLLMInputTooLargeError
from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import OutputRef, RenderPlan, TargetRef, TemplateRef, TextFill
from doctransai.renderers.models import RenderResult
from doctransai.workflows.agentic_conversion import run_agentic_conversion


def test_run_agentic_conversion_builds_channel_and_renders_docx(tmp_path: Path, monkeypatch) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.add_paragraph("隐患：{隐患描述}")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "source-page-1.png"],
    )

    def fake_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:", 1)[1])
        slots = payload["evidence_package"]["template"]["structured"]["slots"]
        slot_by_name = {slot["raw_name"]: slot["slot_id"] for slot in slots}
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": slot_by_name["项目名称"],
                        "decision": "text_fill",
                        "value": "西香TJ3标",
                        "source_refs": ["source_value:ev_951ab1a48f52:0"],
                        "target_ref": f"template_slot:{slot_by_name['项目名称']}",
                        "confidence": 0.9,
                        "reason": "source structured row contains 项目名称=西香TJ3标",
                    },
                    {
                        "slot_id": slot_by_name["隐患描述"],
                        "decision": "text_fill",
                        "value": "电线杂乱",
                        "source_refs": ["source_value:ev_951ab1a48f52:0"],
                        "target_ref": f"template_slot:{slot_by_name['隐患描述']}",
                        "confidence": 0.9,
                        "reason": "source structured row contains 隐患描述=电线杂乱",
                    },
                ]
            },
            ensure_ascii=False,
        )

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=fake_client,
        template_page_images=[{"image_ref": "/tmp/template-page-1.png", "page_index": 0}],
    )

    rendered = Document(output_path)
    report = json.loads(output_path.with_suffix(".agentic_report.json").read_text(encoding="utf-8"))

    assert rendered.paragraphs[0].text == "项目：西香TJ3标"
    assert rendered.paragraphs[1].text == "隐患：电线杂乱"
    assert result.render_result.applied_text_slots == ["docx-paragraph-0", "docx-paragraph-1"]
    assert report["status"]["render_successful"] is True
    assert report["counts"]["accepted_decisions"] == 2
    assert report["counts"]["rejected_decisions"] == 0
    assert report["counts"]["source_page_images"] >= 1
    assert report["counts"]["template_page_images"] == 1
    assert "agent_input" in report
    assert "sent_page_images" in report["agent_input"]
    assert report["decisions"]["accepted"][0]["value"] == "西香TJ3标"
    assert report["decisions"]["rejected"] == []
    assert report["input_gaps"]["source"] == []
    assert report["input_gaps"]["template"] == []


def test_run_agentic_conversion_marks_missing_agent_decisions_unresolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.add_paragraph("隐患：{隐患描述}")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    def fake_client(*, user_prompt: str, **kwargs) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:", 1)[1])
        slots = payload["evidence_package"]["template"]["structured"]["slots"]
        slot_by_name = {slot["raw_name"]: slot["slot_id"] for slot in slots}
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": slot_by_name["项目名称"],
                        "decision": "text_fill",
                        "value": "西香TJ3标",
                        "source_refs": ["source_value:ev_951ab1a48f52:0"],
                        "target_ref": f"template_slot:{slot_by_name['项目名称']}",
                        "reason": "source structured row contains 项目名称=西香TJ3标",
                    }
                ]
            },
            ensure_ascii=False,
        )

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=fake_client,
        source_page_images=[{"image_ref": "/tmp/source-page-1.png", "page_index": 0}],
        template_page_images=[{"image_ref": "/tmp/template-page-1.png", "page_index": 0}],
    )
    report = json.loads(output_path.with_suffix(".agentic_report.json").read_text(encoding="utf-8"))

    assert [slot.slot_id for slot in result.render_plan.unresolved_slots] == ["docx-paragraph-1"]
    assert result.render_plan.unresolved_slots[0].message == "Agent returned no decision for this template slot."
    assert report["counts"]["unresolved_slots"] == 1
    assert report["unresolved"] == [
        {
            "slot_id": "docx-paragraph-1",
            "reason": "agentic_unresolved",
            "message": "Agent returned no decision for this template slot.",
            "decision_type": "unresolved",
        }
    ]


def test_run_agentic_conversion_passes_source_record_selection_to_agent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    def fake_client(*, user_prompt: str, **kwargs) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:", 1)[1])
        assert payload["evidence_package"]["task"]["source_selection"] == {
            "preferred_record_id": "range_1cd5d52e9f25",
            "preferred_source_refs": ["record:range_1cd5d52e9f25"],
        }
        slot = payload["evidence_package"]["template"]["structured"]["slots"][0]
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": slot["slot_id"],
                        "decision": "unresolved",
                        "reason": "No source evidence.",
                    }
                ]
            },
            ensure_ascii=False,
        )

    run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=fake_client,
        source_page_images=[{"image_ref": "/tmp/source-page-1.png", "page_index": 0}],
        template_page_images=[{"image_ref": "/tmp/template-page-1.png", "page_index": 0}],
        source_record_id="range_1cd5d52e9f25",
    )

    report = json.loads(output_path.with_suffix(".agentic_report.json").read_text(encoding="utf-8"))
    assert report["task"]["source_selection"]["preferred_record_id"] == "range_1cd5d52e9f25"


def test_run_agentic_conversion_reports_visual_scan_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    def fake_client(*, user_prompt: str, **kwargs) -> dict[str, object]:
        payload = json.loads(user_prompt.split("INPUT_JSON:", 1)[1])
        slot = payload["evidence_package"]["template"]["structured"]["slots"][0]
        return {
            "visual_scan": {
                "performed": True,
                "extra_fillable_areas": [
                    {
                        "label_or_nearby_text": "编号",
                        "status": "unsupported_by_source",
                    }
                ],
                "supported_decisions_added": 0,
                "unsupported_area_count": 1,
            },
            "decisions": [
                {
                    "slot_id": slot["slot_id"],
                    "decision": "unresolved",
                    "reason": "source has no project name",
                }
            ],
        }

    run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=fake_client,
        source_page_images=[],
        template_page_images=[],
    )
    report = json.loads(output_path.with_suffix(".agentic_report.json").read_text(encoding="utf-8"))

    assert report["visual_scan"] == {
        "performed": True,
        "extra_fillable_areas": [
            {
                "label_or_nearby_text": "编号",
                "status": "unsupported_by_source",
            }
        ],
        "supported_decisions_added": 0,
        "unsupported_area_count": 1,
    }


def test_run_agentic_conversion_feeds_discovered_template_visual_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("编号：")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    def visual_discovery_client(**kwargs) -> dict[str, object]:
        return {
            "visual_targets": [
                {
                    "target_id": "visual-target-编号",
                    "visual_target": {
                        "format_key": "docx",
                        "target_kind": "visual_text_anchor",
                        "label_or_nearby_text": "编号",
                        "page_index": 0,
                    },
                    "label_or_nearby_text": "编号",
                    "expected_content_type": "number",
                }
            ]
        }

    def mapping_client(*, user_prompt: str, **kwargs) -> dict[str, object]:
        payload = json.loads(user_prompt.split("INPUT_JSON:", 1)[1])
        target = payload["evidence_package"]["template"]["targets"][0]
        assert target["target_id"] == "visual-target-编号"
        assert "visual_targets" not in payload["evidence_package"]["template"]
        return {
            "visual_scan": {
                "performed": True,
                "extra_fillable_areas": [],
                "supported_decisions_added": 1,
                "unsupported_area_count": 0,
            },
            "decisions": [
                {
                    "slot_id": target["target_id"],
                    "decision": "text_fill",
                    "value": "西香TJ3标",
                    "source_refs": ["source_value:ev_951ab1a48f52:0"],
                    "visual_target": target["target_ref"],
                    "confidence": 0.9,
                    "reason": "source has a supported identifier-like value",
                }
            ],
        }

    run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=mapping_client,
        visual_discovery_client=visual_discovery_client,
        source_page_images=[],
        template_page_images=[],
    )
    report = json.loads(output_path.with_suffix(".agentic_report.json").read_text(encoding="utf-8"))
    rendered = Document(output_path)

    assert rendered.paragraphs[0].text == "编号：西香TJ3标"
    assert report["template_visual_discovery"]["target_count"] == 1
    assert report["counts"]["text_fills"] == 1


def test_run_agentic_conversion_backfills_visual_target_ref_from_unified_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("编号：")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    def visual_discovery_client(**kwargs) -> dict[str, object]:
        return {
            "visual_targets": [
                {
                    "target_id": "visual-target-1",
                    "label_or_nearby_text": "编号",
                    "visual_target": {
                        "format_key": "docx",
                        "target_kind": "visual_text_anchor",
                        "label_or_nearby_text": "编号",
                    },
                }
            ]
        }

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=lambda **kwargs: {
            "visual_scan": {"performed": True},
            "decisions": [
                {
                    "slot_id": "visual-target-1",
                    "decision": "text_fill",
                    "value": "西香TJ3标",
                    "source_refs": ["source_value:ev_951ab1a48f52:0"],
                    "reason": "source has a supported identifier-like value",
                }
            ],
        },
        visual_discovery_client=visual_discovery_client,
        source_page_images=[],
        template_page_images=[],
    )

    assert Document(output_path).paragraphs[0].text == "编号：西香TJ3标"
    assert result.render_result.applied_text_slots == ["visual-target-1"]


def test_run_agentic_conversion_marks_missing_discovered_visual_target_unresolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("编号：")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    def visual_discovery_client(**kwargs) -> dict[str, object]:
        return {
            "visual_targets": [
                {
                    "target_id": "visual-target-编号",
                    "visual_target": {
                        "format_key": "docx",
                        "target_kind": "visual_text_anchor",
                        "label_or_nearby_text": "编号",
                    },
                }
            ]
        }

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=lambda **kwargs: {"visual_scan": {"performed": True}, "decisions": []},
        visual_discovery_client=visual_discovery_client,
        source_page_images=[],
        template_page_images=[],
    )

    assert [slot.slot_id for slot in result.render_plan.unresolved_slots] == ["visual-target-编号"]


def test_run_agentic_conversion_repairs_duplicate_conflicting_decisions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("期限：{项目名称}")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=lambda **kwargs: {
            "visual_scan": {"performed": True},
            "decisions": [
                {
                    "slot_id": "docx-paragraph-0",
                    "decision": "text_fill",
                    "value": "3",
                    "source_refs": ["record:ev_951ab1a48f52"],
                    "target_ref": "template_slot:docx-paragraph-0",
                },
                {
                    "slot_id": "docx-paragraph-0",
                    "decision": "text_fill",
                    "value": "2026年5月14日",
                    "source_refs": ["record:ev_951ab1a48f52"],
                    "target_ref": "template_slot:docx-paragraph-0",
                },
            ],
        },
        source_page_images=[],
        template_page_images=[],
    )
    report = json.loads(output_path.with_suffix(".agentic_report.json").read_text(encoding="utf-8"))

    assert result.validation_result.rejected_decisions == []
    assert [slot.slot_id for slot in result.render_plan.unresolved_slots] == ["docx-paragraph-0"]
    assert report["diagnostics"] == [
        {
            "severity": "warning",
            "code": "duplicate_conflicting_decisions",
            "message": (
                "Agent returned conflicting fill decisions for one template target; "
                "converted the target to unresolved."
            ),
            "slot_id": "docx-paragraph-0",
            "decision_count": 2,
        }
    ]


def test_run_agentic_conversion_marks_rejected_decisions_unresolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    def fake_client(*, user_prompt: str, **kwargs) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:", 1)[1])
        slot = payload["evidence_package"]["template"]["structured"]["slots"][0]
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": slot["slot_id"],
                        "decision": "text_fill",
                        "value": "不存在的项目",
                        "source_refs": ["source_value:ev_951ab1a48f52:0"],
                        "target_ref": f"template_slot:{slot['slot_id']}",
                        "reason": "agent cited a source value",
                    }
                ]
            },
            ensure_ascii=False,
        )

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=fake_client,
        source_page_images=[],
        template_page_images=[],
    )
    report = json.loads(output_path.with_suffix(".agentic_report.json").read_text(encoding="utf-8"))

    assert result.validation_result.rejected_decisions[0].slot_id == "docx-paragraph-0"
    assert [slot.slot_id for slot in result.render_plan.unresolved_slots] == ["docx-paragraph-0"]
    assert "{项目名称}" not in "\n".join(paragraph.text for paragraph in Document(output_path).paragraphs)
    assert report["counts"]["text_fills"] == 0
    assert report["counts"]["unresolved_slots"] == 1
    assert report["unresolved"] == [
        {
            "slot_id": "docx-paragraph-0",
            "reason": "validation_rejected",
            "message": "text_fill value was not found in any cited source object.",
            "source_refs": ["source_value:ev_951ab1a48f52:0"],
            "decision_type": "text_fill",
            "value_preview": "不存在的项目",
        }
    ]


def test_run_agentic_conversion_fills_docx_header_slot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.sections[0].header.paragraphs[0].text = "编号：{项目名称}"
    document.add_paragraph("正文")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    def fake_client(*, user_prompt: str, **kwargs) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:", 1)[1])
        slot = payload["evidence_package"]["template"]["structured"]["slots"][0]
        assert slot["address"]["address_kind"] == "header_paragraph"
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": slot["slot_id"],
                        "decision": "text_fill",
                        "value": "西香TJ3标",
                        "source_refs": ["source_value:ev_951ab1a48f52:0"],
                        "target_ref": f"template_slot:{slot['slot_id']}",
                    }
                ]
            },
            ensure_ascii=False,
        )

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=fake_client,
        source_page_images=[],
        template_page_images=[],
    )

    rendered = Document(output_path)
    assert rendered.sections[0].header.paragraphs[0].text == "编号：西香TJ3标"
    assert result.audit_report["counts"]["text_fills"] == 1
    assert result.audit_report["render_diagnostics"] == []


def test_run_agentic_conversion_writes_report_for_invalid_agent_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.add_paragraph("隐患：{隐患描述}")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=lambda **kwargs: "not json",
        source_page_images=[],
        template_page_images=[],
    )
    report = json.loads(output_path.with_suffix(".agentic_report.json").read_text(encoding="utf-8"))

    assert output_path.exists()
    assert report["status"]["render_successful"] is True
    assert report["diagnostics"][0]["code"] == "agent_response_invalid"
    assert report["counts"]["accepted_decisions"] == 2
    assert report["counts"]["rejected_decisions"] == 0
    assert report["counts"]["text_fills"] == 0
    assert report["counts"]["unresolved_slots"] == 2
    assert [slot.slot_id for slot in result.render_plan.unresolved_slots] == [
        "docx-paragraph-0",
        "docx-paragraph-1",
    ]


def test_run_agentic_conversion_writes_report_for_agent_input_too_large(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "page-1.png"],
    )

    def oversized_client(**kwargs):
        raise DoctransaiLLMInputTooLargeError(
            estimated_input_chars=300_000,
            max_input_chars=260_000,
        )

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=oversized_client,
        source_page_images=[],
        template_page_images=[],
    )
    report = json.loads(output_path.with_suffix(".agentic_report.json").read_text(encoding="utf-8"))

    assert output_path.exists()
    assert report["diagnostics"][0]["code"] == "agent_input_too_large"
    assert "DoctransaiLLMInputTooLargeError" in report["diagnostics"][0]["message"]
    assert report["counts"]["text_fills"] == 0
    assert report["counts"]["unresolved_slots"] == 1
    assert result.render_plan.unresolved_slots[0].slot_id == "docx-paragraph-0"


def test_agentic_source_page_rendering_supports_legacy_doc_suffix() -> None:
    assert workflow_module._visual_preview_format_key("/tmp/source.doc") == "doc"


def test_audit_report_includes_compact_unresolved_summary() -> None:
    unresolved_decision = AgentDecision(
        slot_id="slot-source-missing",
        decision_type="unresolved",
        source_refs=["record:source-1"],
        reason="source has no supported completion date",
    )
    rejected_decision = AgentDecision(
        slot_id="slot-rejected",
        decision_type="text_fill",
        value="unsupported value",
        source_refs=["source_value:missing:0"],
        reason="agent cited a source value",
    )
    validation_result = ValidationResult(
        accepted_decisions=[unresolved_decision],
        rejected_decisions=[rejected_decision],
        diagnostics=[
            {
                "severity": "error",
                "code": "source_ref_not_found",
                "message": "Source ref 'source_value:missing:0' does not exist.",
                "slot_id": "slot-rejected",
            }
        ],
    )
    render_plan = RenderPlan(
        plan_id="agentic:test",
        source_bundle_path="/tmp/source-bundle.json",
        template=TemplateRef(template_path="/tmp/template.docx", format_key="docx"),
        output=OutputRef(output_path="/tmp/output.docx", output_format="docx"),
        unresolved_slots=[
            UnresolvedSlot(
                slot_id="slot-source-missing",
                canonical_key="completion_date",
                reason_code="agentic_unresolved",
                message="source has no supported completion date",
                candidate_ids=["candidate-1"],
            )
        ],
    )
    evidence_package = {
        "source": {
            "structured": {"records": [], "image_assets": []},
            "page_images": [],
            "input_gaps": [],
        },
        "template": {
            "structured": {
                "slots": [
                    {"slot_id": "slot-source-missing"},
                    {"slot_id": "slot-agent-missed"},
                    {"slot_id": "slot-rejected"},
                ]
            },
            "page_images": [],
            "input_gaps": [],
        },
    }

    report = workflow_module._build_audit_report(
        evidence_package=evidence_package,
        decisions=[unresolved_decision, rejected_decision],
        validation_result=validation_result,
        render_plan=render_plan,
        render_result=RenderResult(output_path="/tmp/output.docx"),
    )

    assert report["unresolved"] == [
        {
            "slot_id": "slot-source-missing",
            "reason": "agentic_unresolved",
            "message": "source has no supported completion date",
            "candidate_ids": ["candidate-1"],
            "source_refs": ["record:source-1"],
            "decision_type": "unresolved",
        },
        {
            "slot_id": "slot-agent-missed",
            "reason": "agent_unidentified",
            "message": "Agent returned no decision for this template slot.",
        },
        {
            "slot_id": "slot-rejected",
            "reason": "validation_rejected",
            "message": "Source ref 'source_value:missing:0' does not exist.",
            "source_refs": ["source_value:missing:0"],
            "decision_type": "text_fill",
            "value_preview": "unsupported value",
        },
    ]
    assert "evidence_package" not in report
    assert report["decisions"]["accepted"][0]["reason"] == "source has no supported completion date"
    assert report["decisions"]["rejected"][0]["value"] == "unsupported value"


def test_audit_report_includes_target_ledger() -> None:
    filled_decision = AgentDecision(
        slot_id="target-filled",
        decision_type="text_fill",
        value="西香TJ3标",
        source_refs=["record:source-1"],
        reason="source supports value",
    )
    unresolved_decision = AgentDecision(
        slot_id="target-unresolved",
        decision_type="unresolved",
        reason="source has no value",
    )
    rejected_decision = AgentDecision(
        slot_id="target-rejected",
        decision_type="text_fill",
        value="unsupported",
        source_refs=["source_value:missing:0"],
        reason="agent cited missing source",
    )
    validation_result = ValidationResult(
        accepted_decisions=[filled_decision, unresolved_decision],
        rejected_decisions=[rejected_decision],
        diagnostics=[
            {
                "severity": "error",
                "code": "source_ref_not_found",
                "message": "Source ref does not exist.",
                "slot_id": "target-rejected",
            }
        ],
    )
    render_plan = RenderPlan(
        plan_id="agentic:test",
        source_bundle_path="/tmp/source-bundle.json",
        template=TemplateRef(template_path="/tmp/template.docx", format_key="docx"),
        output=OutputRef(output_path="/tmp/output.docx", output_format="docx"),
        text_fills=[
                TextFill(
                    slot_id="target-filled",
                    target=TargetRef(format_key="docx", target_kind="placeholder"),
                    value="西香TJ3标",
                )
        ],
        unresolved_slots=[
            UnresolvedSlot(
                slot_id="target-unresolved",
                canonical_key="未填",
                reason_code="agentic_unresolved",
                message="source has no value",
            ),
            UnresolvedSlot(
                slot_id="target-rejected",
                canonical_key="错误字段",
                reason_code="validation_rejected",
                message="Source ref does not exist.",
            )
        ],
    )
    evidence_package = {
        "source": {
            "structured": {"records": [], "image_assets": []},
            "page_images": [],
            "input_gaps": [],
        },
        "template": {
            "structured": {"slots": []},
            "targets": [
                {
                    "target_id": "target-filled",
                    "origin": "structured",
                    "label": "项目名称",
                    "expected_content_type": "text",
                },
                {
                    "target_id": "target-unresolved",
                    "origin": "visual",
                    "label": "编号",
                    "expected_content_type": "number",
                },
                {
                    "target_id": "target-rejected",
                    "origin": "structured",
                    "label": "错误字段",
                    "expected_content_type": "text",
                },
                {
                    "target_id": "target-missing",
                    "origin": "visual",
                    "label": "监督电话",
                    "expected_content_type": "phone",
                },
            ],
            "page_images": [],
            "input_gaps": [],
        },
    }

    report = workflow_module._build_audit_report(
        evidence_package=evidence_package,
        decisions=[filled_decision, unresolved_decision, rejected_decision],
        validation_result=validation_result,
        render_plan=render_plan,
        render_result=RenderResult(
            output_path="/tmp/output.docx",
            applied_text_slots=["target-filled"],
        ),
    )

    assert report["target_ledger"] == [
        {
            "target_id": "target-filled",
            "origin": "structured",
            "label": "项目名称",
            "expected_content_type": "text",
            "decision_type": "text_fill",
            "decision_status": "accepted",
            "render_status": "applied",
            "value_preview": "西香TJ3标",
            "source_refs": ["record:source-1"],
            "reason": "source supports value",
            "diagnostics": [],
        },
        {
            "target_id": "target-unresolved",
            "origin": "visual",
            "label": "编号",
            "expected_content_type": "number",
            "decision_type": "unresolved",
            "decision_status": "accepted",
            "render_status": "unresolved",
            "source_refs": [],
            "reason": "source has no value",
            "diagnostics": [],
        },
        {
            "target_id": "target-rejected",
            "origin": "structured",
            "label": "错误字段",
            "expected_content_type": "text",
            "decision_type": "text_fill",
            "decision_status": "rejected",
            "render_status": "unresolved",
            "value_preview": "unsupported",
            "source_refs": ["source_value:missing:0"],
            "reason": "agent cited missing source",
            "diagnostics": ["source_ref_not_found"],
        },
        {
            "target_id": "target-missing",
            "origin": "visual",
            "label": "监督电话",
            "expected_content_type": "phone",
            "decision_type": "missing",
            "decision_status": "missing",
            "render_status": "missing",
            "source_refs": [],
            "reason": "Agent returned no decision for this template target.",
            "diagnostics": [],
        },
    ]


def test_audit_report_detects_rendered_docx_residual_template_markers(tmp_path: Path) -> None:
    output_path = tmp_path / "output.docx"
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("X")
    paragraph.add_run("{未填字段}")
    document.save(output_path)

    evidence_package = {
        "source": {
            "structured": {"records": [], "image_assets": []},
            "page_images": [],
            "input_gaps": [],
        },
        "template": {
            "structured": {"slots": []},
            "page_images": [],
            "input_gaps": [],
        },
    }
    render_plan = RenderPlan(
        plan_id="agentic:test",
        source_bundle_path="/tmp/source-bundle.json",
        template=TemplateRef(template_path="/tmp/template.docx", format_key="docx"),
        output=OutputRef(output_path=str(output_path), output_format="docx"),
    )

    report = workflow_module._build_audit_report(
        evidence_package=evidence_package,
        decisions=[],
        validation_result=ValidationResult(),
        render_plan=render_plan,
        render_result=RenderResult(output_path=str(output_path)),
    )

    assert report["status"]["has_residual_template_markers"] is True
    assert report["output_audit"]["checked"] is True
    assert report["output_audit"]["residual_marker_counts_by_type"] == {
        "brace_placeholder": 1,
        "x_run_marker": 1,
    }
    assert {marker["text"] for marker in report["output_audit"]["residual_template_markers"]} == {
        "X",
        "{未填字段}",
    }
