from __future__ import annotations

import json
from pathlib import Path

import doctransai.workflows.v1_conversion as workflow_module
from docx import Document

from doctransai.llm import DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV
from doctransai.models.render_plan import OutputRef, RenderPlan, RowPlan, TemplateRef
from doctransai.models.source import SourceRecord, SourceValue
from doctransai.models.template import TemplateModel
from doctransai.source_model import AdaptedSourceModel
from doctransai.templates.template_materialization import TemplateMaterializationResult
from doctransai.workflows.v1_conversion import run_v1_conversion


def test_run_v1_conversion_generates_output_and_reports_from_real_bundle(tmp_path: Path) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "outputs" / "result.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.add_paragraph("隐患：{隐患描述}")
    document.add_paragraph("要求：{整改要求}")
    document.add_paragraph("{隐患照片}")
    document.add_paragraph("负责人：{责任单位负责人}")
    document.save(template_path)

    result = run_v1_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        primary_record_id="range_1cd5d52e9f25",
    )

    rendered = Document(output_path)
    conversion_report_path = output_path.with_suffix(".conversion_report.json")
    provenance_report_path = output_path.with_suffix(".provenance_report.md")
    performance_report_path = output_path.with_suffix(".performance_report.json")

    assert result.render_result.output_path == str(output_path)
    assert rendered.paragraphs[0].text == "项目：西香TJ3标"
    assert rendered.paragraphs[1].text == "隐患：电线杂乱"
    assert rendered.paragraphs[2].text == "要求：排列整齐"
    assert len(rendered.inline_shapes) == 1
    assert rendered.paragraphs[4].text == "负责人："

    assert conversion_report_path.exists() is True
    assert provenance_report_path.exists() is True
    assert performance_report_path.exists() is True

    conversion_report = json.loads(conversion_report_path.read_text(encoding="utf-8"))
    assert conversion_report["plan_id"] == result.render_plan.plan_id
    assert conversion_report["status"]["render_successful"] is True
    assert conversion_report["status"]["output_clean"] is False
    assert {item["canonical_key"] for item in conversion_report["unresolved"]} == {"责任单位负责人"}
    assert "full_agent_context" not in conversion_report
    assert conversion_report["full_agent_context_summary"]["full_agent_context_schema_version"] == (
        "doctransai_full_agent_context_v1"
    )
    assert conversion_report["full_agent_context_summary"]["full_source_record_count"] >= 1
    assert conversion_report["full_agent_context_summary"]["full_source_image_asset_count"] >= 1
    assert "full_source_diagnostic_count" in conversion_report["full_agent_context_summary"]
    assert conversion_report["full_agent_context_summary"]["source_instance_id"] is None
    assert "repeat_region_cluster_hint_count" in conversion_report["full_agent_context_summary"]

    provenance_report = provenance_report_path.read_text(encoding="utf-8")
    assert "西香TJ3标" in provenance_report
    assert "final_images/sheet1_image7.jpeg" in provenance_report

    performance_report = json.loads(performance_report_path.read_text(encoding="utf-8"))
    step_names = [step["name"] for step in performance_report["steps"]]
    assert performance_report["scope"] == "doctransai_bundle_to_output"
    assert performance_report["total_elapsed_ms"] >= 0
    assert "read_parsed_document_bundle" in step_names
    assert "build_render_plan" in step_names
    assert "render_output" in step_names
    assert result.performance_report["summary"]["template_slot_count"] == 5
    assert result.performance_report["summary"]["full_agent_context_summary"]["full_source_record_count"] >= 1


def test_agent_context_report_summary_preserves_source_overview_truncation_state() -> None:
    source_model = AdaptedSourceModel(
        records=[
            SourceRecord(
                record_id=f"record-{index}",
                document_id="doc-1",
                source_path="/input/large.docx",
                values=[SourceValue(canonical_key="正文", value="长文本", raw_label="正文")],
            )
            for index in range(300)
        ],
        diagnostics=[
            {"diagnostic_id": f"diag-{index}", "severity": "warning", "message": "warning"}
            for index in range(40)
        ],
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[],
    )
    render_plan = RenderPlan(
        plan_id="plan-1",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/out.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/out.docx", output_format="docx"),
        created_at="2026-05-28T00:00:00",
        record_plans=[RowPlan(record_id="record-0")],
    )

    summary = workflow_module._build_agent_context_report_summary(
        source_model=source_model,
        template_model=template_model,
        render_plan=render_plan,
        source_instance_id=None,
    )

    assert summary["records_truncated"] is True
    assert summary["diagnostics_truncated"] is True


def test_run_v1_conversion_records_doc_template_materialization_metadata(tmp_path: Path, monkeypatch) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    legacy_template_path = tmp_path / "legacy-template.doc"
    output_path = tmp_path / "outputs" / "legacy-result.doc"
    materialized_template_path = tmp_path / "materialized" / "legacy-template.docx"
    legacy_template_path.write_bytes(b"legacy word bytes")

    materialized_template_path.parent.mkdir(parents=True)
    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.save(materialized_template_path)

    def fake_materialize_target_template(template_path, output_path):
        return TemplateMaterializationResult(
            template_path=Path(template_path).resolve(),
            analysis_template_path=materialized_template_path.resolve(),
            output_path=Path(output_path).resolve().with_suffix(".docx"),
            diagnostics=[
                {
                    "severity": "info",
                    "code": "doc_template_converted_to_docx",
                    "message": "converted by test",
                    "field": None,
                }
            ],
            metadata={
                "strategy": "libreoffice_doc_to_docx",
                "requested_template_format": "doc",
                "analysis_template_format": "docx",
                "original_template_path": str(legacy_template_path.resolve()),
                "materialized_template_path": str(materialized_template_path.resolve()),
                "original_output_path": str(output_path.resolve()),
                "materialized_output_path": str(output_path.resolve().with_suffix(".docx")),
            },
        )

    monkeypatch.setattr(workflow_module, "materialize_target_template", fake_materialize_target_template)

    result = run_v1_conversion(
        bundle_path=bundle_path,
        template_path=legacy_template_path,
        output_path=output_path,
        primary_record_id="range_1cd5d52e9f25",
    )

    conversion_report = json.loads(output_path.with_suffix(".conversion_report.json").read_text(encoding="utf-8"))
    performance_report = json.loads(output_path.with_suffix(".performance_report.json").read_text(encoding="utf-8"))
    materialization_step = next(step for step in performance_report["steps"] if step["name"] == "materialize_template")

    assert result.render_result.output_path == str(output_path.with_suffix(".docx").resolve())
    assert result.render_plan.template.template_path == str(materialized_template_path.resolve())
    assert conversion_report["output"]["output_path"] == str(output_path.with_suffix(".docx").resolve())
    assert any(item["code"] == "doc_template_converted_to_docx" for item in conversion_report["diagnostics"])
    assert materialization_step["metadata"]["strategy"] == "libreoffice_doc_to_docx"
    assert performance_report["summary"]["template_materialization"]["materialized_template_path"] == str(
        materialized_template_path.resolve()
    )


def test_run_v1_conversion_uses_agent_orchestrator_when_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "100000000")
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, "10000000")
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "outputs" / "agent-result.docx"

    document = Document()
    document.add_paragraph("未知：{完全不存在字段}")
    document.save(template_path)

    called = {"agent": False}
    original = workflow_module.build_render_plan_with_agent

    def wrapped_agent_builder(**kwargs):
        called["agent"] = True
        return original(**kwargs)

    monkeypatch.setattr(workflow_module, "build_render_plan_with_agent", wrapped_agent_builder)

    def stub_decision_client(*, system_prompt, user_prompt):
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": slot["slot_id"],
                        "decision": "unresolved",
                        "candidate_id": None,
                        "generated_value": None,
                        "confidence": 0.0,
                        "reason": "No safe candidate.",
                    }
                    for slot in payload["slots"]
                ],
            },
            ensure_ascii=False,
        )

    result = run_v1_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        primary_record_id="range_1cd5d52e9f25",
        use_mapping_agent=True,
        decision_client=stub_decision_client,
    )

    assert called["agent"] is True
    assert result.render_result.output_path == str(output_path)
    summary = result.conversion_report["full_agent_context_summary"]
    assert summary["agent_input_estimated_bytes"] is not None
    assert summary["agent_input_limit_bytes"] is not None
    assert summary["agent_input_within_limit"] is True
    assert summary["agent_input_preflight_blocked"] is False
    assert summary["agent_input_packaging"]["mode"] == "full"
    assert summary["agent_input_packaging"]["slot_packets_compacted"] is False


def test_run_v1_conversion_can_fill_real_unresolved_slot_with_agent_stub(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, "1000000")
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = Path(
        "V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx"
    ).resolve()
    output_path = tmp_path / "outputs" / "agent-filled.docx"

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        decisions = []
        for slot in payload["slots"]:
            if slot["raw_name"] == "责任单位负责人":
                decisions.append(
                    {
                        "slot_id": slot["slot_id"],
                        "decision": "candidate",
                        "candidate_id": slot["candidates"][0]["candidate_id"],
                        "generated_value": None,
                        "confidence": 0.84,
                        "reason": "Selected first same-row person candidate.",
                    }
                )
            else:
                decisions.append(
                    {
                        "slot_id": slot["slot_id"],
                        "decision": "unresolved",
                        "candidate_id": None,
                        "generated_value": None,
                        "confidence": 0.2,
                        "reason": "No safe candidate.",
                    }
                )
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": decisions,
            },
            ensure_ascii=False,
        )

    result = run_v1_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        primary_record_id="range_1cd5d52e9f25",
        use_mapping_agent=True,
        decision_client=stub_client,
    )

    rendered = Document(output_path)
    conversion_report = json.loads(output_path.with_suffix(".conversion_report.json").read_text(encoding="utf-8"))

    assert rendered.tables[0].cell(0, 3).text == "杨恩赐"
    assert any(item["code"] == "agent_resolved_slot" for item in conversion_report["diagnostics"])


def test_run_v1_conversion_marks_agent_generated_values_for_review(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, "1000000")
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "outputs" / "agent-generated.docx"

    document = Document()
    document.add_paragraph("摘要：{成果简介}")
    document.save(template_path)

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": slot["slot_id"],
                        "decision": "generated",
                        "candidate_id": None,
                        "generated_value": "基于全文综合生成的成果简介",
                        "confidence": 0.72,
                        "reason": "The source contains broad context but no exact field.",
                    }
                    for slot in payload["slots"]
                ],
            },
            ensure_ascii=False,
        )

    result = run_v1_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        primary_record_id="range_1cd5d52e9f25",
        use_mapping_agent=True,
        decision_client=stub_client,
    )

    conversion_report = json.loads(output_path.with_suffix(".conversion_report.json").read_text(encoding="utf-8"))
    generated_fill = next(fill for fill in conversion_report["fills"] if fill["slot_id"] == "docx-paragraph-0")

    assert result.render_result.is_successful is True
    assert generated_fill["decision_kind"] == "agent_generated"
    assert generated_fill["traceability_status"] == "low_traceability_generated"
    assert generated_fill["review_required"] is True
    assert conversion_report["status"]["review_required"] is True
    assert conversion_report["status"]["blocking_issue"] is False
    assert conversion_report["status"]["low_traceability_generated_count"] == 1


def test_run_v1_conversion_downgrades_oversized_agent_payload_to_reviewable_unresolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "128")
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "outputs" / "agent-payload-too-large.docx"

    document = Document()
    document.add_paragraph("摘要：{成果简介}")
    document.save(template_path)

    result = run_v1_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        primary_record_id="range_1cd5d52e9f25",
        use_mapping_agent=True,
    )

    conversion_report = json.loads(output_path.with_suffix(".conversion_report.json").read_text(encoding="utf-8"))
    summary = conversion_report["full_agent_context_summary"]

    assert result.render_result.is_successful is True
    assert conversion_report["status"]["review_required"] is True
    assert any(item["code"] == "agent_input_payload_too_large" for item in conversion_report["diagnostics"])
    assert summary["agent_input_estimated_bytes"] > summary["agent_input_limit_bytes"]
    assert summary["agent_input_within_limit"] is False
    assert summary["agent_input_preflight_blocked"] is True
    assert summary["agent_input_packaging"]["mode"] == "preflight_blocked"
    assert summary["agent_input_packaging"]["slot_packets_compacted"] is True


def test_run_v1_conversion_can_apply_saved_agent_decision_payload(tmp_path: Path) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = Path(
        "V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx"
    ).resolve()
    decision_payload_path = tmp_path / "agent_output.json"
    output_path = tmp_path / "outputs" / "saved-agent-result.docx"

    decision_payload_path.write_text(
        json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "docx-table-0-2",
                        "decision": "candidate",
                        "candidate_id": "range_1cd5d52e9f25:14",
                        "generated_value": None,
                        "confidence": 0.84,
                        "reason": "approved by human review",
                    },
                    {
                        "slot_id": "docx-table-0-6",
                        "decision": "unresolved",
                        "candidate_id": None,
                        "generated_value": None,
                        "confidence": 0.0,
                        "reason": "keep unresolved",
                    },
                ],
            },
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    result = run_v1_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        primary_record_id="range_1cd5d52e9f25",
        decision_payload_path=decision_payload_path,
    )

    rendered = Document(output_path)
    conversion_report = json.loads(output_path.with_suffix(".conversion_report.json").read_text(encoding="utf-8"))

    assert rendered.tables[0].cell(0, 3).text == "杨恩赐"
    assert {item["canonical_key"] for item in conversion_report["unresolved"]} == {"手机号", "人员姓名", "datetime_day_blank_1"}
    assert any(item["code"] == "agent_resolved_slot" for item in conversion_report["diagnostics"])


def test_run_v1_conversion_filters_bundle_by_source_file_path(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)
    bundle_path = bundle_dir / "parsed_document_bundle.json"
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "outputs" / "filtered-result.docx"

    source_a = "/input/a.xlsx"
    source_b = "/input/b.xlsx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.save(template_path)

    (bundle_dir / "source_manifest.jsonl").write_text(
        (
            json.dumps({"document_id": "doc-a", "source_path": source_a, "source_checksum": "checksum-a"}, ensure_ascii=False)
            + "\n"
            + json.dumps({"document_id": "doc-b", "source_path": source_b, "source_checksum": "checksum-b"}, ensure_ascii=False)
            + "\n"
        ),
        encoding="utf-8",
    )
    (bundle_dir / "cell_ranges.jsonl").write_text(
        (
            json.dumps(
                {
                    "contract_version": "data_asset_pack_v0",
                    "cell_range_id": "range-a",
                    "document_id": "doc-a",
                    "source_path": source_a,
                    "sheet_id": "sheet-a",
                    "sheet_name": "Sheet0",
                    "range_ref": "A3:A3",
                        "range_type": "cell_range",
                        "range_text": "项目名称=项目A",
                        "range_json": {"raw_values": ["项目A"]},
                        "parser_signals": {"header_values": ["项目名称"], "non_empty_columns": [1], "row_index": 3},
                        "quality": {"issues": []},
                    },
                    ensure_ascii=False,
                )
            + "\n"
            + json.dumps(
                {
                    "contract_version": "data_asset_pack_v0",
                    "cell_range_id": "range-b",
                    "document_id": "doc-b",
                    "source_path": source_b,
                    "sheet_id": "sheet-b",
                    "sheet_name": "Sheet0",
                    "range_ref": "A3:A3",
                        "range_type": "cell_range",
                        "range_text": "项目名称=项目B",
                        "range_json": {"raw_values": ["项目B"]},
                        "parser_signals": {"header_values": ["项目名称"], "non_empty_columns": [1], "row_index": 3},
                        "quality": {"issues": []},
                    },
                    ensure_ascii=False,
                )
            + "\n"
        ),
        encoding="utf-8",
    )
    bundle_path.write_text(
        json.dumps(
            {
                "bundle_type": "ParsedDocumentBundle",
                "contract_version": "data_asset_pack_v0",
                "database_writes": False,
                "generated_at": "2026-05-21T00:00:00Z",
                "capabilities": {"cell_ranges": True},
                "components": {
                    "source_manifest": {"count": 2, "path": "source_manifest.jsonl"},
                    "cell_ranges": {"count": 2, "path": "cell_ranges.jsonl"},
                },
                "summary": {"document_count": 2, "cell_range_count": 2},
                "reports": {},
                "issue_buckets": {},
                "documents": [
                    {"document_id": "doc-a", "source_path": source_a},
                    {"document_id": "doc-b", "source_path": source_b},
                ],
                "parse_errors": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_v1_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        source_file_path=source_b,
    )

    rendered = Document(output_path)

    assert result.render_plan.record_plans[0].record_id == "range-b"
    assert rendered.paragraphs[0].text == "项目：项目B"
