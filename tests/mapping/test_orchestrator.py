from __future__ import annotations

import json
from pathlib import Path

from doctransai.llm import DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV
from doctransai.mapping.agent_resolver import AgentDecision
from doctransai.mapping.orchestrator import build_render_plan_with_agent, build_render_plan_with_decisions
from doctransai.models.render_plan import render_plan_from_dict
from doctransai.models.source import ProvenanceRef, SourceImageAsset, SourceModel, SourceRecord, SourceValue
from doctransai.models.template import RepeatRegion, SlotAddress, TemplateModel, TemplateSlot


def _provenance(*, object_id: str, row_index: int, column_index: int) -> ProvenanceRef:
    return ProvenanceRef(
        source_kind="cell_range",
        document_id="doc-1",
        object_id=object_id,
        locator={"sheet_name": "Sheet0", "row_index": row_index, "column_index": column_index},
        source_path="/input/source.xlsx",
    )


def test_build_render_plan_with_agent_resolves_generic_slot_without_domain_pack(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="range-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                values=[
                    SourceValue(
                        canonical_key="联系电话",
                        value="13800138000",
                        raw_label="联系电话",
                        provenance=[_provenance(object_id="range-3", row_index=3, column_index=8)],
                    )
                ],
                locator={"sheet_name": "Sheet0", "row_index": 3},
            )
        ]
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-phone",
                raw_name="手机号",
                canonical_name="手机号",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        assert "联系电话" in user_prompt
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        candidate_id = payload["slots"][0]["candidates"][0]["candidate_id"]
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-phone",
                        "decision": "candidate",
                        "candidate_id": candidate_id,
                        "generated_value": None,
                        "confidence": 0.87,
                        "reason": "same row contact number",
                    }
                ],
            },
            ensure_ascii=False,
        )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="range-3",
        decision_client=stub_client,
    )

    plan = render_plan_from_dict(payload)

    assert [(fill.slot_id, fill.value) for fill in plan.text_fills] == [("slot-phone", "13800138000")]
    assert plan.unresolved_slots == []


def test_build_render_plan_with_agent_accepts_source_instance_id_without_primary_record_id(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="range-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                values=[
                    SourceValue(
                        canonical_key="项目名称",
                        value="项目A",
                        raw_label="项目名称",
                        provenance=[_provenance(object_id="range-3", row_index=3, column_index=2)],
                    )
                ],
                locator={"sheet_name": "Sheet0", "row_index": 3},
            ),
            SourceRecord(
                record_id="range-4",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                values=[
                    SourceValue(
                        canonical_key="项目名称",
                        value="项目B",
                        raw_label="项目名称",
                        provenance=[_provenance(object_id="range-4", row_index=4, column_index=2)],
                    )
                ],
                locator={"sheet_name": "Sheet0", "row_index": 4},
            ),
        ]
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-project",
                raw_name="项目名称",
                canonical_name="项目名称",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        source_instance_id="sheet_row:doc-1:Sheet0:4",
    )

    plan = render_plan_from_dict(payload)

    assert plan.record_plans[0].record_id == "range-4"
    assert [(fill.slot_id, fill.value) for fill in plan.text_fills] == [("slot-project", "项目B")]


def test_build_render_plan_with_agent_reviews_and_overrides_risky_auto_fill(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="range-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                values=[
                    SourceValue(
                        canonical_key="联系电话",
                        value="13800138000",
                        raw_label="联系电话",
                        provenance=[_provenance(object_id="range-3", row_index=3, column_index=8)],
                    )
                ],
                locator={"sheet_name": "Sheet0", "row_index": 3},
            )
        ]
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-phone",
                raw_name="手机号",
                canonical_name="手机号",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    calls: list[dict] = []

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        calls.append(payload)
        slot_payload = payload["slots"][0]
        assert slot_payload["slot_id"] == "slot-phone"
        assert slot_payload["context"]["resolution_mode"] == "review"
        assert slot_payload["context"]["current_value"] == "13800138000"
        assert slot_payload["context"]["current_confidence"] == 0.78
        assert slot_payload["context"]["current_transform"] == "phone_typed_row_match"
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-phone",
                        "decision": "generated",
                        "candidate_id": None,
                        "generated_value": "13900139000",
                        "confidence": 0.91,
                        "reason": "agent corrected risky same-row typed match",
                    }
                ],
            },
            ensure_ascii=False,
        )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="range-3",
        decision_client=stub_client,
    )

    plan = render_plan_from_dict(payload)

    assert len(calls) == 1
    assert [(fill.slot_id, fill.value, fill.transform) for fill in plan.text_fills] == [
        ("slot-phone", "13900139000", "agent_generated_value")
    ]
    assert plan.unresolved_slots == []


def test_build_render_plan_with_agent_warns_on_low_confidence_semantic_risk_candidate(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="range-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                values=[
                    SourceValue(
                        canonical_key="发生日期",
                        value="2026-05-15",
                        raw_label="发生日期",
                        provenance=[_provenance(object_id="range-3", row_index=3, column_index=8)],
                    )
                ],
                locator={"sheet_name": "Sheet0", "row_index": 3},
            )
        ]
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-note",
                raw_name="备注内容",
                canonical_name="备注内容",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        candidate_id = payload["slots"][0]["candidates"][0]["candidate_id"]
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-note",
                        "decision": "candidate",
                        "candidate_id": candidate_id,
                        "generated_value": None,
                        "confidence": 0.75,
                        "reason": "model attempted a weak cross-label match",
                    }
                ],
            },
            ensure_ascii=False,
        )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="range-3",
        decision_client=stub_client,
    )

    plan = render_plan_from_dict(payload)

    assert [(fill.slot_id, fill.value) for fill in plan.text_fills] == [("slot-note", "2026-05-15")]
    assert plan.unresolved_slots == []
    risk_diagnostics = [
        diagnostic for diagnostic in plan.diagnostics if diagnostic.code == "agent_candidate_semantic_risk"
    ]
    assert len(risk_diagnostics) == 1
    assert risk_diagnostics[0].severity == "warning"
    assert risk_diagnostics[0].field == "备注内容"
    assert "model attempted a weak cross-label match" in risk_diagnostics[0].message


def test_build_render_plan_with_agent_fills_low_overlap_candidate_when_reason_is_clear(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="range-4",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                values=[
                    SourceValue(
                        canonical_key="客户名称",
                        value="上海星河科技有限公司",
                        raw_label="客户名称",
                        provenance=[_provenance(object_id="range-4", row_index=4, column_index=2)],
                    )
                ],
                locator={"sheet_name": "Sheet0", "row_index": 4},
            )
        ]
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-party",
                raw_name="甲方单位",
                canonical_name="甲方单位",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        candidate_id = payload["slots"][0]["candidates"][0]["candidate_id"]
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-party",
                        "decision": "candidate",
                        "candidate_id": candidate_id,
                        "generated_value": None,
                        "confidence": 0.74,
                        "reason": "customer name is the contracting party for this template slot",
                    }
                ],
            },
            ensure_ascii=False,
        )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="range-4",
        decision_client=stub_client,
    )

    plan = render_plan_from_dict(payload)

    assert [(fill.slot_id, fill.value, fill.transform) for fill in plan.text_fills] == [
        ("slot-party", "上海星河科技有限公司", "agent_selected_candidate")
    ]
    assert plan.unresolved_slots == []
    assert [
        diagnostic.code
        for diagnostic in plan.diagnostics
        if diagnostic.field == "甲方单位" and diagnostic.severity == "warning"
    ] == ["agent_candidate_semantic_risk"]


def test_build_render_plan_with_decisions_rechecks_cross_row_table_context_mismatch(tmp_path: Path) -> None:
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
                        raw_label="项目名称",
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
                        raw_label="table_text",
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
    template_model = TemplateModel(
        template_id="template-cross-row",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
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

    payload = build_render_plan_with_decisions(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="tblrow-3",
        decisions=[
            AgentDecision(
                slot_id="slot-desc",
                decision="candidate",
                candidate_id="tblrow-4:0",
                generated_value=None,
                confidence=0.88,
                reason="model selected a candidate from another table row",
            )
        ],
    )

    plan = render_plan_from_dict(payload)

    assert [fill.slot_id for fill in plan.text_fills] == []
    assert [(slot.slot_id, slot.reason_code) for slot in plan.unresolved_slots] == [
        ("slot-desc", "cross_slot_source_instance_mismatch")
    ]
    assert plan.unresolved_slots[0].provenance_refs[0].locator["row_index"] == 4
    assert any(diagnostic.code == "cross_slot_source_instance_mismatch" for diagnostic in plan.diagnostics)
    assert not [
        diagnostic
        for diagnostic in plan.diagnostics
        if diagnostic.field == "隐患描述" and diagnostic.code in {"agent_resolved_slot", "agent_reviewed_slot"}
    ]


def test_consistency_rejection_keeps_agent_diagnostic_for_other_slot_with_same_label(tmp_path: Path) -> None:
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
                        canonical_key="联系电话",
                        value="13800138000",
                        raw_label="联系电话",
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
                        canonical_key="联系电话",
                        value="13900139000",
                        raw_label="联系电话",
                        provenance=[
                            ProvenanceRef(
                                source_kind="table_cell",
                                document_id="doc-1",
                                object_id="tbl-1-r4-c1",
                                locator={"page_anchor": "page_1", "table_id": "tbl-1", "row_index": 4, "column_index": 1},
                                source_path="/input/source.docx",
                            )
                        ],
                    )
                ],
            ),
        ]
    )
    template_model = TemplateModel(
        template_id="template-duplicate-labels",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-phone-ok",
                raw_name="手机号",
                canonical_name="手机号",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            ),
            TemplateSlot(
                slot_id="slot-phone-bad",
                raw_name="手机号",
                canonical_name="手机号",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=1),
            ),
        ],
    )

    payload = build_render_plan_with_decisions(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="tblrow-3",
        decisions=[
            AgentDecision(
                slot_id="slot-phone-ok",
                decision="candidate",
                candidate_id="tblrow-3:0",
                generated_value=None,
                confidence=0.9,
                reason="primary row phone is valid",
            ),
            AgentDecision(
                slot_id="slot-phone-bad",
                decision="candidate",
                candidate_id="tblrow-4:0",
                generated_value=None,
                confidence=0.9,
                reason="cross row phone should be rejected",
            ),
        ],
    )

    plan = render_plan_from_dict(payload)

    assert [(fill.slot_id, fill.value) for fill in plan.text_fills] == [("slot-phone-ok", "13800138000")]
    assert [(slot.slot_id, slot.reason_code) for slot in plan.unresolved_slots] == [
        ("slot-phone-bad", "cross_slot_source_instance_mismatch")
    ]
    assert [
        diagnostic.message
        for diagnostic in plan.diagnostics
        if diagnostic.code == "agent_reviewed_slot" and diagnostic.field == "手机号"
    ] == ["primary row phone is valid"]


def test_build_render_plan_with_agent_reports_truncated_agent_context(tmp_path: Path) -> None:
    records = [
        SourceRecord(
            record_id=f"record-{index}",
            document_id="doc-1",
            source_path="/input/large.pdf",
            values=[SourceValue(canonical_key="text", value=("长文本" * 500) if index == 0 else f"片段 {index}", raw_label="text")],
        )
        for index in range(270)
    ]
    source_model = SourceModel(records=records)
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-summary",
                raw_name="成果简介",
                canonical_name="成果简介",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        assert payload["source_overview"]["context_status"]["records_truncated"] is True
        assert payload["source_document_view"]
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-summary",
                        "decision": "generated",
                        "candidate_id": None,
                        "generated_value": "源文档摘要",
                        "confidence": 0.65,
                        "reason": "summarized from visible source context",
                    }
                ],
            },
            ensure_ascii=False,
        )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="record-0",
        decision_client=stub_client,
    )

    plan = render_plan_from_dict(payload)

    assert any(diagnostic.code == "agent_context_truncated" for diagnostic in plan.diagnostics)


def test_build_render_plan_with_agent_downgrades_oversized_payload_without_llm_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "128")
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="record-0",
                document_id="doc-1",
                source_path="/input/large.pdf",
                values=[SourceValue(canonical_key="text", value="长文本" * 1000, raw_label="text")],
            )
        ]
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-summary",
                raw_name="成果简介",
                canonical_name="成果简介",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="record-0",
    )

    plan = render_plan_from_dict(payload)

    assert [(slot.slot_id, slot.reason_code) for slot in plan.unresolved_slots] == [
        ("slot-summary", "missing_value")
    ]
    assert any(diagnostic.code == "agent_input_payload_too_large" for diagnostic in plan.diagnostics)


def test_build_render_plan_with_agent_omits_duplicated_text_candidates_for_medium_wide_context(tmp_path: Path) -> None:
    records = [
        SourceRecord(
            record_id=f"record-{index}",
            document_id="doc-1",
            source_path="/input/long-report.docx",
            values=[
                SourceValue(
                    canonical_key="检查内容",
                    value=f"第 {index} 条检查记录包含现场问题、整改建议和责任说明。",
                    raw_label="检查内容",
                )
            ],
        )
        for index in range(24)
    ]
    source_model = SourceModel(records=records)
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id=f"slot-{index}",
                raw_name=f"字段{index}",
                canonical_name=f"字段{index}",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=index),
            )
            for index in range(43)
        ],
    )

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        assert payload["source_overview"]["context_status"]["record_count"] == 24
        assert payload["source_document_view"]
        assert payload["slots"]
        assert all(not slot["candidates"] for slot in payload["slots"])
        assert all(
            slot["context"]["text_candidate_material"]
            == "omitted_per_slot_to_avoid_duplicate_payload_use_shared_source_overview"
            for slot in payload["slots"]
        )
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": f"slot-{index}",
                        "decision": "unresolved",
                        "candidate_id": None,
                        "generated_value": None,
                        "confidence": 0.0,
                        "reason": "not enough source support",
                    }
                    for index in range(43)
                ],
            },
            ensure_ascii=False,
        )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="record-0",
        decision_client=stub_client,
    )

    plan = render_plan_from_dict(payload)
    assert len(plan.unresolved_slots) == 43


def test_build_render_plan_with_agent_keeps_image_source_ref_separate_from_context(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.doc",
                evidence_id="ev-1",
                values=[
                    SourceValue(
                        canonical_key="text",
                        value="发现的隐患问题：二工区围挡未及时封闭",
                        raw_label="text",
                    )
                ],
            )
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="img-hazard",
                source_ref="images/hazard.jpg",
                page_anchor="page_1",
                nearby_text_after=["二工区围挡未及时封闭"],
                nearby_evidence_ids=["ev-1"],
            )
        ],
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="隐患照片",
                canonical_name="隐患照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            )
        ],
    )

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        candidate = payload["slots"][0]["candidates"][0]
        assert "二工区围挡未及时封闭" in candidate["value_text"]
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-photo",
                        "decision": "candidate",
                        "candidate_id": candidate["candidate_id"],
                        "generated_value": None,
                        "confidence": 0.82,
                        "reason": "nearby image text matches hazard photo",
                    }
                ],
            },
            ensure_ascii=False,
        )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="ev-1",
        decision_client=stub_client,
    )

    plan = render_plan_from_dict(payload)

    assert len(plan.image_placements) == 1
    assert plan.image_placements[0].source_ref == "images/hazard.jpg"
    assert "二工区围挡未及时封闭" not in plan.image_placements[0].source_ref
    assert plan.unresolved_slots == []


def test_build_render_plan_with_agent_does_not_preconsume_docx_repeat_media_region(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.docx",
                evidence_id="ev-1",
                values=[SourceValue(canonical_key="text", value="图片说明：现场围挡", raw_label="text")],
            )
        ],
        image_assets=[
            SourceImageAsset(asset_id="img-1", source_ref="images/one.jpg", nearby_text_after=["无关现场"], order_index=1),
            SourceImageAsset(asset_id="img-2", source_ref="images/two.jpg", nearby_text_after=["现场围挡"], nearby_evidence_ids=["ev-1"], order_index=2),
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
                raw_name="现场图片",
                canonical_name="现场图片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
                repeat_region_id="region-1",
            ),
            TemplateSlot(
                slot_id="slot-desc",
                raw_name="图片说明",
                canonical_name="图片说明",
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
    captured_payloads = []

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        captured_payloads.append(payload)
        slot_ids = [slot["slot_id"] for slot in payload["slots"]]
        assert "slot-photo" in slot_ids
        assert all(not slot_id.startswith("slot-photo@") for slot_id in slot_ids)
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-photo",
                        "decision": "candidate",
                        "candidate_id": "img-2",
                        "generated_value": None,
                        "confidence": 0.88,
                        "reason": "nearby text matches the repeat image slot",
                    },
                    {
                        "slot_id": "slot-desc",
                        "decision": "generated",
                        "candidate_id": None,
                        "generated_value": "现场围挡",
                        "confidence": 0.84,
                        "reason": "short source-grounded caption",
                    },
                ],
            },
            ensure_ascii=False,
        )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="ev-1",
        decision_client=stub_client,
    )

    plan = render_plan_from_dict(payload)

    assert captured_payloads
    assert [placement.asset_id for placement in plan.image_placements] == ["img-2"]
    assert plan.image_placements[0].target.repeat_region_id == "region-1"
    assert plan.image_placements[0].target.instance_index == 0
    assert [(fill.slot_id, fill.value, fill.target.repeat_region_id) for fill in plan.text_fills] == [
        ("slot-desc", "现场围挡", "region-1")
    ]


def test_build_render_plan_with_agent_expands_multi_image_decision_for_single_slot(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.docx",
                values=[SourceValue(canonical_key="text", value="蜂窝麻面；涨模错缝", raw_label="text")],
            )
        ],
        image_assets=[
            SourceImageAsset(asset_id="img-1", source_ref="images/one.jpg", nearby_text_after=["蜂窝麻面"], order_index=1),
            SourceImageAsset(asset_id="img-2", source_ref="images/two.jpg", nearby_text_after=["涨模错缝"], order_index=2),
        ],
    )
    template_model = TemplateModel(
        template_id="template-media-cell",
        template_path="/templates/reply.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="整改照片",
                canonical_name="整改照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="table_cell", table_index=0, row_index=0, column_index=0),
                placement_constraints={
                    "multi_value_allowed": True,
                    "media_group_role": "image",
                },
            )
        ],
    )

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        assert payload["slots"][0]["context"]["placement_constraints"]["multi_value_allowed"] is True
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-photo",
                        "decision": "candidate",
                        "candidate_id": "img-1",
                        "candidate_ids": ["img-1", "img-2"],
                        "generated_value": None,
                        "confidence": 0.9,
                        "reason": "template slot is a repeatable media area",
                    }
                ],
            },
            ensure_ascii=False,
        )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="ev-1",
        decision_client=stub_client,
    )

    plan = render_plan_from_dict(payload)

    assert [(placement.slot_id, placement.asset_id) for placement in plan.image_placements] == [
        ("slot-photo@0", "img-1"),
        ("slot-photo@1", "img-2"),
    ]
    assert [placement.caption for placement in plan.image_placements] == [None, None]
    assert plan.unresolved_slots == []
    assert not [
        diagnostic
        for diagnostic in plan.diagnostics
        if diagnostic.field == "整改照片" and diagnostic.code in {"missing_value", "missing_asset"}
    ]


def test_build_render_plan_with_agent_pairs_multi_images_with_caption_slot(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.docx",
                values=[SourceValue(canonical_key="text", value="蜂窝麻面；涨模错缝", raw_label="text")],
            )
        ],
        image_assets=[
            SourceImageAsset(asset_id="img-1", source_ref="images/one.jpg", nearby_text_before=["蜂窝麻面"], order_index=1),
            SourceImageAsset(asset_id="img-2", source_ref="images/two.jpg", nearby_text_before=["涨模错缝"], order_index=2),
        ],
    )
    template_model = TemplateModel(
        template_id="template-media-cell",
        template_path="/templates/reply.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-photo",
                raw_name="整改照片",
                canonical_name="整改照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="table_cell", table_index=0, row_index=0, column_index=0),
                placement_constraints={
                    "multi_value_allowed": True,
                    "media_group_role": "image",
                    "paired_caption_slot_id": "slot-caption",
                },
            ),
            TemplateSlot(
                slot_id="slot-caption",
                raw_name="整改照片说明",
                canonical_name="整改照片说明",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="table_cell", table_index=0, row_index=0, column_index=0),
                placement_constraints={
                    "multi_value_allowed": True,
                    "media_group_role": "caption",
                    "paired_image_slot_id": "slot-photo",
                },
            ),
        ],
    )

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-photo",
                        "decision": "candidate",
                        "candidate_id": "img-1",
                        "candidate_ids": ["img-1", "img-2"],
                        "generated_value": None,
                        "confidence": 0.9,
                        "reason": "use the two source photos in order",
                    },
                    {
                        "slot_id": "slot-caption",
                        "decision": "generated",
                        "candidate_id": None,
                        "generated_value": "蜂窝麻面\n涨模错缝",
                        "confidence": 0.88,
                        "reason": "one caption per selected image in the same order",
                    },
                ],
            },
            ensure_ascii=False,
        )

    payload = build_render_plan_with_agent(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="ev-1",
        decision_client=stub_client,
    )

    plan = render_plan_from_dict(payload)

    assert [(placement.slot_id, placement.asset_id, placement.caption) for placement in plan.image_placements] == [
        ("slot-photo@0", "img-1", "蜂窝麻面"),
        ("slot-photo@1", "img-2", "涨模错缝"),
    ]
    assert [placement.caption_slot_id for placement in plan.image_placements] == ["slot-caption", "slot-caption"]
    assert all(placement.caption_target is not None for placement in plan.image_placements)
    assert [fill.slot_id for fill in plan.text_fills] == []
    assert plan.unresolved_slots == []


def test_build_render_plan_with_decisions_rejects_reusing_one_image_for_different_roles(tmp_path: Path) -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.docx",
                evidence_id="ev-1",
                values=[SourceValue(canonical_key="text", value="整改后照片已提供，未提供复查照片。", raw_label="text")],
            )
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="img-after",
                source_ref="images/after.jpg",
                nearby_text_before=["整改后照片：围挡已封闭"],
                nearby_evidence_ids=["ev-1"],
            )
        ],
    )
    template_model = TemplateModel(
        template_id="template-record",
        template_path="/templates/record.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-after-photo",
                raw_name="整改照片",
                canonical_name="整改照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="table_cell", table_index=0, row_index=0, column_index=0),
            ),
            TemplateSlot(
                slot_id="slot-review-photo",
                raw_name="复查照片",
                canonical_name="复查照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="table_cell", table_index=0, row_index=1, column_index=0),
            ),
        ],
    )

    from doctransai.mapping.agent_resolver import AgentDecision
    from doctransai.mapping.orchestrator import build_render_plan_with_decisions

    payload = build_render_plan_with_decisions(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(tmp_path / "parsed_document_bundle.json"),
        output_path=str(tmp_path / "out.docx"),
        primary_record_id="ev-1",
        decisions=[
            AgentDecision(
                slot_id="slot-after-photo",
                decision="candidate",
                candidate_id="img-after",
                generated_value=None,
                confidence=0.88,
                reason="source has an after-rectification photo",
            ),
            AgentDecision(
                slot_id="slot-review-photo",
                decision="candidate",
                candidate_id="img-after",
                generated_value=None,
                confidence=0.82,
                reason="model tried to reuse the same image for another role",
            ),
        ],
    )

    plan = render_plan_from_dict(payload)

    assert [(placement.slot_id, placement.asset_id) for placement in plan.image_placements] == [
        ("slot-after-photo", "img-after")
    ]
    assert [(slot.slot_id, slot.reason_code) for slot in plan.unresolved_slots] == [
        ("slot-review-photo", "image_role_conflict")
    ]
