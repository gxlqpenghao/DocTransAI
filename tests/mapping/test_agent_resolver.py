from __future__ import annotations

import json

import pytest

from doctransai.mapping.agent_resolver import (
    AgentCandidatePacket,
    AgentDecision,
    AgentResolutionError,
    AgentResolutionTrace,
    AgentSlotPacket,
    prepare_agent_shared_context,
    prepare_agent_slot_packets,
    resolve_mapping_decisions,
    resolve_mapping_decisions_with_trace,
)
from doctransai.llm import DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV
from doctransai.mapping.visual_candidates import build_visual_content_units_for_primary_record
from doctransai.mapping.prompts import (
    build_mapping_system_prompt,
    build_mapping_user_prompt,
    build_repair_system_prompt,
)
from doctransai.mapping.type_inference import infer_source_value_type
from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.source import ProvenanceRef, SourceImageAsset, SourceModel, SourceRecord, SourceValue
from doctransai.models.template import RepeatRegion, SlotAddress, TemplateModel, TemplateSlot


def _provenance(*, object_id: str, row_index: int, column_index: int) -> ProvenanceRef:
    return ProvenanceRef(
        source_kind="cell_range",
        document_id="doc-xlsx",
        object_id=object_id,
        locator={"sheet_name": "Sheet0", "row_index": row_index, "column_index": column_index},
        source_path="/input/source.xlsx",
    )


def test_resolve_mapping_decisions_accepts_valid_stubbed_json_response() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-phone",
            raw_name="手机号",
            slot_kind="text",
            expected_value_type="phone",
            context={},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="cand-1",
                    candidate_kind="text",
                    value_label="联系电话",
                    value_text="13800138000",
                    value_type="phone",
                    relation="same_record_row",
                    confidence_hint=0.9,
                    locator={"row_index": 3},
                    source_path="/input/source.xlsx",
                )
            ],
        )
    ]

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        assert "slot-phone" in user_prompt
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-phone",
                        "decision": "candidate",
                        "candidate_id": "cand-1",
                        "generated_value": None,
                        "confidence": 0.91,
                        "reason": "same row phone value",
                    }
                ],
            },
            ensure_ascii=False,
        )

    decisions = resolve_mapping_decisions(slot_packets, decision_client=stub_client)

    assert decisions[0].slot_id == "slot-phone"
    assert decisions[0].decision == "candidate"
    assert decisions[0].candidate_id == "cand-1"


def test_resolve_mapping_decisions_preflights_oversized_default_llm_payload(monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "128")
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-summary",
            raw_name="成果简介",
            slot_kind="text",
            expected_value_type="long_text",
            context={},
            candidates=[],
        )
    ]
    shared_context = {
        "full_agent_context": {
            "schema_version": "doctransai_full_agent_context_v1",
            "full_source_context": {"document_view": "长文本" * 1000},
        }
    }

    trace = resolve_mapping_decisions_with_trace(slot_packets, shared_context=shared_context)

    assert trace.payload_preflight["exceeded"] is True
    assert trace.payload_preflight["preflight_blocked"] is True
    assert trace.payload_preflight["estimated_request_bytes"] > trace.payload_preflight["max_request_body_bytes"]
    assert trace.decisions == [
        AgentDecision(
            slot_id="slot-summary",
            decision="unresolved",
            candidate_id=None,
            generated_value=None,
            confidence=0.0,
            reason="agent_input_payload_too_large",
        )
    ]


def test_resolve_mapping_decisions_preflights_oversized_injected_client_payload(monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "128")
    calls = {"count": 0}
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-summary",
            raw_name="成果简介",
            slot_kind="text",
            expected_value_type="long_text",
            context={},
            candidates=[],
        )
    ]
    shared_context = {
        "full_agent_context": {
            "schema_version": "doctransai_full_agent_context_v1",
            "full_source_context": {"document_view": "长文本" * 1000},
        }
    }

    def injected_client(*, system_prompt: str, user_prompt: str) -> str:
        calls["count"] += 1
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [],
            },
            ensure_ascii=False,
        )

    trace = resolve_mapping_decisions_with_trace(
        slot_packets,
        decision_client=injected_client,
        shared_context=shared_context,
    )

    assert calls["count"] == 0
    assert trace.payload_preflight["exceeded"] is True
    assert trace.payload_preflight["preflight_blocked"] is True
    assert trace.decisions == [
        AgentDecision(
            slot_id="slot-summary",
            decision="unresolved",
            candidate_id=None,
            generated_value=None,
            confidence=0.0,
            reason="agent_input_payload_too_large",
        )
    ]


def test_resolve_mapping_decisions_preflights_oversized_input_length(monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "1000000")
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, "500")
    calls = {"count": 0}
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-summary",
            raw_name="成果简介",
            slot_kind="text",
            expected_value_type="long_text",
            context={},
            candidates=[],
        )
    ]
    shared_context = {
        "full_agent_context": {
            "schema_version": "doctransai_full_agent_context_v1",
            "full_source_context": {"document_view": "长文本" * 1000},
        }
    }

    def injected_client(*, system_prompt: str, user_prompt: str) -> str:
        calls["count"] += 1
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [],
            },
            ensure_ascii=False,
        )

    trace = resolve_mapping_decisions_with_trace(
        slot_packets,
        decision_client=injected_client,
        shared_context=shared_context,
    )

    assert calls["count"] == 0
    assert trace.payload_preflight["exceeded"] is True
    assert trace.payload_preflight["request_body_exceeded"] is False
    assert trace.payload_preflight["input_length_exceeded"] is True
    assert trace.payload_preflight["estimated_input_chars"] > trace.payload_preflight["max_input_chars"]
    assert trace.payload_preflight["preflight_blocked"] is True
    assert trace.decisions == [
        AgentDecision(
            slot_id="slot-summary",
            decision="unresolved",
            candidate_id=None,
            generated_value=None,
            confidence=0.0,
            reason="agent_input_payload_too_large",
        )
    ]


def test_resolve_mapping_decisions_preflights_oversized_repair_payload(monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "10500")
    calls = {"count": 0}
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-summary",
            raw_name="成果简介",
            slot_kind="text",
            expected_value_type="long_text",
            context={},
            candidates=[],
        )
    ]

    def injected_client(*, system_prompt: str, user_prompt: str) -> str:
        calls["count"] += 1
        return "invalid response " + ("x" * 10000)

    trace = resolve_mapping_decisions_with_trace(
        slot_packets,
        decision_client=injected_client,
    )

    assert calls["count"] == 1
    assert trace.repaired is True
    assert trace.payload_preflight["preflight_blocked"] is True
    assert trace.payload_preflight["phase"] == "repair"
    assert trace.decisions == [
        AgentDecision(
            slot_id="slot-summary",
            decision="unresolved",
            candidate_id=None,
            generated_value=None,
            confidence=0.0,
            reason="agent_input_payload_too_large",
        )
    ]


def test_resolve_mapping_decisions_compacts_slot_packets_and_removes_legacy_context(monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "40000")
    captured: dict[str, object] = {}
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-summary",
            raw_name="成果简介",
            slot_kind="text",
            expected_value_type="long_text",
            context={"placement_constraints": {}},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="record-1:0",
                    candidate_kind="text",
                    value_label="成果简介",
                    value_text="完整成果简介" + ("很长" * 1200),
                    value_type="long_text",
                    relation="document_context",
                    confidence_hint=0.7,
                    locator={"page_anchor": "page_1"},
                    source_path="/input/source.pdf",
                    provenance_refs=[
                        {
                            "source_kind": "record",
                            "document_id": "doc-1",
                            "object_id": "record-1",
                            "locator": {"page_anchor": "page_1"},
                            "source_path": "/input/source.pdf",
                        }
                    ],
                    source_object_refs=[
                        {
                            "object_key": "record:record-1",
                            "object_kind": "record",
                            "object_id": "record-1",
                            "collection": "records",
                            "index": 0,
                        }
                    ],
                )
            ],
        )
    ]
    shared_context = {
        "full_agent_context": {
            "schema_version": "doctransai_full_agent_context_v1",
            "full_source_context": {
                "records": [
                    {
                        "record_id": "record-1",
                        "raw": {"large_parser_payload": "duplicate metadata " * 1000},
                        "values": [{"canonical_key": "成果简介", "value": "完整成果简介" + ("很长" * 1200)}],
                    }
                ],
                "image_assets": [],
                "diagnostics": [],
                "document_view": "record-1: 完整成果简介" + ("很长" * 1200),
                "object_index": {
                    "by_object_key": {
                        "record:record-1": {
                            "object_kind": "record",
                            "object_id": "record-1",
                            "collection": "records",
                            "index": 0,
                        }
                    }
                },
            },
            "full_template_context": {"visual_pages": []},
            "navigation_context": {},
            "task_context": {},
        },
        "source_document_view": "legacy duplicate " * 6000,
        "source_overview": {"records": [{"record_id": "record-1"}]},
        "template_overview": {"document_view": "成果简介："},
        "source_instance_overview": {"primary_record_id": "record-1"},
        "source_cluster_plan": {"clusters": []},
    }

    def stub_client(*, system_prompt: str, user_prompt: str, user_parts=None) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1])
        captured.update(payload)
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-summary",
                        "decision": "candidate",
                        "candidate_id": "record-1:0",
                        "generated_value": None,
                        "confidence": 0.84,
                        "reason": "candidate points back to full_source_context object_index",
                    }
                ],
            },
            ensure_ascii=False,
        )

    trace = resolve_mapping_decisions_with_trace(
        slot_packets,
        decision_client=stub_client,
        shared_context=shared_context,
    )

    assert trace.decisions[0].candidate_id == "record-1:0"
    assert captured["agent_input_packaging"]["mode"] == "compact_slot_packets"
    assert captured["agent_input_packaging"]["full_context_compacted"] is True
    assert captured["agent_input_packaging"]["legacy_fields_removed"] == [
        "source_overview",
        "source_document_view",
        "template_overview",
        "source_instance_overview",
        "source_cluster_plan",
    ]
    assert "full_agent_context" in captured
    assert "source_document_view" not in captured
    assert "source_overview" not in captured
    assert "raw" not in captured["full_agent_context"]["full_source_context"]["records"][0]
    candidate = captured["slots"][0]["candidates"][0]
    assert "value_text" not in candidate
    assert candidate["value_preview"].startswith("完整成果简介")
    assert candidate["provenance_refs"][0]["object_id"] == "record-1"
    assert candidate["source_object_refs"][0]["object_key"] == "record:record-1"
    assert trace.payload_preflight["agent_input_packaging"]["mode"] == "compact_slot_packets"
    assert trace.payload_preflight["agent_input_packaging"]["full_estimated_bytes"] > (
        trace.payload_preflight["agent_input_packaging"]["compact_estimated_bytes"]
    )


def test_resolve_mapping_decisions_blocks_when_compact_payload_still_exceeds_limit(monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "128")
    calls = {"count": 0}
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-summary",
            raw_name="成果简介",
            slot_kind="text",
            expected_value_type="long_text",
            context={},
            candidates=[],
        )
    ]
    shared_context = {
        "full_agent_context": {
            "schema_version": "doctransai_full_agent_context_v1",
            "full_source_context": {"document_view": "长文本" * 1000},
            "full_template_context": {"visual_pages": []},
            "navigation_context": {},
            "task_context": {},
        },
        "source_document_view": "长文本" * 1000,
    }

    def injected_client(*, system_prompt: str, user_prompt: str) -> str:
        calls["count"] += 1
        return "{}"

    trace = resolve_mapping_decisions_with_trace(
        slot_packets,
        decision_client=injected_client,
        shared_context=shared_context,
    )

    assert calls["count"] == 0
    assert trace.payload_preflight["preflight_blocked"] is True
    assert trace.payload_preflight["agent_input_packaging"]["mode"] == "preflight_blocked"
    assert trace.payload_preflight["agent_input_packaging"]["slot_packets_compacted"] is True


def test_agent_mapping_prompts_are_loaded_from_policy_markdown() -> None:
    slot_payload = {
        "schema_version": "doctransai_agent_mapping_decision_v1",
        "slots": [],
        "template_overview": {"document_view": "P1: {隐患描述}"},
        "source_overview": {"records": []},
    }

    system_prompt = build_mapping_system_prompt()
    user_prompt = build_mapping_user_prompt(slot_payload)
    repair_prompt = build_repair_system_prompt()

    assert "# Role" in system_prompt
    assert "Template-Slot Mapping Resolver" in system_prompt
    assert "RenderPlan" in system_prompt
    assert "Do not parse raw source files" in system_prompt
    assert "full structured source context" in system_prompt
    assert "navigation context" in system_prompt
    assert "not evidence by itself" in system_prompt
    assert "compact_slot_packets" in system_prompt
    assert "candidate_lookup_keys" in system_prompt
    assert "provenance_refs" in system_prompt
    assert "INPUT_JSON" in user_prompt
    assert "doctransai_agent_mapping_decision_v1" in user_prompt
    assert "JSON repair assistant" in repair_prompt


def test_resolve_mapping_decisions_rejects_unknown_candidate_ids() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-name",
            raw_name="人员姓名",
            slot_kind="text",
            expected_value_type="text",
            context={},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="cand-1",
                    candidate_kind="text",
                    value_label="责任人",
                    value_text="王友振",
                    value_type="person",
                    relation="same_record_row",
                    confidence_hint=0.7,
                    locator={},
                    source_path="/input/source.xlsx",
                )
            ],
        )
    ]

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-name",
                        "decision": "candidate",
                        "candidate_id": "cand-missing",
                        "generated_value": None,
                        "confidence": 0.8,
                        "reason": "bad id",
                    }
                ],
            }
        )

    with pytest.raises(AgentResolutionError) as exc_info:
        resolve_mapping_decisions(slot_packets, decision_client=stub_client)

    assert "cand-missing" in str(exc_info.value)


def test_resolve_mapping_decisions_accepts_unique_candidate_id_prefix_alias() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-deadline",
            raw_name="整改期限",
            slot_kind="text",
            expected_value_type="datetime",
            context={},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="tblrow-1:5:exact_label",
                    candidate_kind="text",
                    value_label="整改期限",
                    value_text="2022.3.12",
                    value_type="datetime",
                    relation="same_record_row",
                    confidence_hint=0.9,
                    locator={"row_index": 5},
                    source_path="/input/source.docx",
                )
            ],
        )
    ]

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-deadline",
                        "decision": "candidate",
                        "candidate_id": "tblrow-1:5",
                        "generated_value": None,
                        "confidence": 0.85,
                        "reason": "unique prefix",
                    }
                ],
            },
            ensure_ascii=False,
        )

    decisions = resolve_mapping_decisions(slot_packets, decision_client=stub_client)

    assert decisions[0].candidate_id == "tblrow-1:5:exact_label"


def test_resolve_mapping_decisions_accepts_multiple_image_candidate_ids() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-photo",
            raw_name="整改照片",
            slot_kind="image",
            expected_value_type="image",
            context={"placement_constraints": {"multi_value_allowed": True}},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="img-1",
                    candidate_kind="image",
                    value_label="整改照片",
                    value_text="source_ref=images/one.jpg",
                    value_type="image",
                    relation="document_context",
                    confidence_hint=0.7,
                    locator={"source_ref": "images/one.jpg"},
                    source_path="/input/source.docx",
                ),
                AgentCandidatePacket(
                    candidate_id="img-2",
                    candidate_kind="image",
                    value_label="整改照片",
                    value_text="source_ref=images/two.jpg",
                    value_type="image",
                    relation="document_context",
                    confidence_hint=0.7,
                    locator={"source_ref": "images/two.jpg"},
                    source_path="/input/source.docx",
                ),
            ],
        )
    ]

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
                        "confidence": 0.88,
                        "reason": "both images belong to the template media area",
                    }
                ],
            },
            ensure_ascii=False,
        )

    decisions = resolve_mapping_decisions(slot_packets, decision_client=stub_client)

    assert decisions[0].candidate_id == "img-1"
    assert decisions[0].candidate_ids == ["img-1", "img-2"]


def test_prepare_agent_slot_packets_keeps_row_nearby_and_document_context_image_candidates() -> None:
    primary_record = SourceRecord(
        record_id="row-3",
        document_id="doc-xlsx",
        source_path="/input/source.xlsx",
        evidence_id="ev-row-3",
        locator={"sheet_name": "Sheet0", "row_index": 3},
        values=[SourceValue(canonical_key="隐患描述", value="安全带破损", raw_label="隐患描述")],
    )
    other_record = SourceRecord(
        record_id="row-4",
        document_id="doc-xlsx",
        source_path="/input/source.xlsx",
        evidence_id="ev-row-4",
        locator={"sheet_name": "Sheet0", "row_index": 4},
        values=[SourceValue(canonical_key="隐患描述", value="电线杂乱", raw_label="隐患描述")],
    )
    source_model = SourceModel(
        records=[primary_record, other_record],
        image_assets=[
            SourceImageAsset(
                asset_id="img-document",
                document_id="doc-xlsx",
                source_ref="final_images/document.jpg",
                order_index=1,
            ),
            SourceImageAsset(
                asset_id="img-nearby",
                document_id="doc-xlsx",
                source_ref="final_images/nearby.jpg",
                order_index=2,
                nearby_evidence_ids=["ev-row-3"],
            ),
            SourceImageAsset(
                asset_id="img-primary",
                document_id="doc-xlsx",
                source_ref="final_images/primary.jpg",
                order_index=3,
                sheet_name="Sheet0",
                row_index=3,
                column_index=11,
                related_evidence_ids=["ev-row-3"],
            ),
        ],
    )
    slot = TemplateSlot(
        slot_id="slot-photo",
        raw_name="隐患照片",
        canonical_name="隐患照片",
        slot_kind="image",
        address=SlotAddress(format_key="docx", address_kind="table_cell", table_index=0, row_index=0, column_index=0),
    )

    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=primary_record,
        unresolved_slots=[
            UnresolvedSlot(
                slot_id="slot-photo",
                canonical_key="隐患照片",
                reason_code="missing_asset",
                message="No image selected.",
            )
        ],
        template_slots_by_id={"slot-photo": slot},
    )

    assert [candidate.candidate_id for candidate in packets[0].candidates] == [
        "img-primary",
        "img-nearby",
        "img-document",
    ]
    assert [candidate.relation for candidate in packets[0].candidates] == [
        "same_record_row",
        "near_primary_record_context",
        "document_context",
    ]


def test_prepare_agent_slot_packets_keeps_same_label_value_when_record_differs() -> None:
    primary_record = SourceRecord(
        record_id="row-3",
        document_id="doc-xlsx",
        source_path="/input/source.xlsx",
        locator={"sheet_name": "Sheet0", "row_index": 3},
        values=[
            SourceValue(
                canonical_key="项目名称",
                value="西香TJ3标",
                raw_label="项目名称",
                provenance=[_provenance(object_id="row-3", row_index=3, column_index=2)],
            )
        ],
    )
    other_record = SourceRecord(
        record_id="row-4",
        document_id="doc-xlsx",
        source_path="/input/source.xlsx",
        locator={"sheet_name": "Sheet0", "row_index": 4},
        values=[
            SourceValue(
                canonical_key="项目名称",
                value="西香TJ3标",
                raw_label="项目名称",
                provenance=[_provenance(object_id="row-4", row_index=4, column_index=2)],
            )
        ],
    )
    source_model = SourceModel(records=[primary_record, other_record])
    slot = TemplateSlot(
        slot_id="slot-project",
        raw_name="项目名称",
        canonical_name="项目名称",
        slot_kind="text",
        address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
    )

    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=primary_record,
        unresolved_slots=[
            UnresolvedSlot(
                slot_id="slot-project",
                canonical_key="项目名称",
                reason_code="needs_agent_resolution",
                message="Need agent to choose source row.",
            )
        ],
        template_slots_by_id={"slot-project": slot},
    )

    assert [candidate.candidate_id for candidate in packets[0].candidates] == ["row-3:0", "row-4:0"]
    assert [candidate.locator["row_index"] for candidate in packets[0].candidates] == [3, 4]


def test_prepare_agent_slot_packets_uses_value_level_locator_when_available() -> None:
    primary_record = SourceRecord(
        record_id="row-3",
        document_id="doc-xlsx",
        source_path="/input/source.xlsx",
        locator={"sheet_name": "Sheet0", "row_index": 3},
        values=[
            SourceValue(
                canonical_key="项目名称",
                value="西香TJ3标",
                raw_label="项目名称",
                provenance=[_provenance(object_id="cell-r3-c2", row_index=3, column_index=2)],
            ),
            SourceValue(
                canonical_key="项目名称",
                value="西香TJ3标",
                raw_label="项目名称",
                provenance=[_provenance(object_id="cell-r4-c2", row_index=4, column_index=2)],
            ),
        ],
    )
    source_model = SourceModel(records=[primary_record])
    slot = TemplateSlot(
        slot_id="slot-project",
        raw_name="项目名称",
        canonical_name="项目名称",
        slot_kind="text",
        address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
    )

    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=primary_record,
        unresolved_slots=[
            UnresolvedSlot(
                slot_id="slot-project",
                canonical_key="项目名称",
                reason_code="needs_agent_resolution",
                message="Need agent to choose source cell.",
            )
        ],
        template_slots_by_id={"slot-project": slot},
    )

    assert [candidate.candidate_id for candidate in packets[0].candidates] == ["row-3:0", "row-3:1"]
    assert [candidate.locator["row_index"] for candidate in packets[0].candidates] == [3, 4]
    assert [candidate.locator["column_index"] for candidate in packets[0].candidates] == [2, 2]


def test_build_visual_content_units_keeps_document_context_after_row_and_nearby_units() -> None:
    primary_record = SourceRecord(
        record_id="row-3",
        document_id="doc-xlsx",
        source_path="/input/source.xlsx",
        evidence_id="ev-row-3",
        locator={"sheet_name": "Sheet0", "row_index": 3},
        values=[SourceValue(canonical_key="隐患描述", value="安全带破损", raw_label="隐患描述")],
    )
    source_model = SourceModel(
        records=[primary_record],
        image_assets=[
            SourceImageAsset(
                asset_id="img-document",
                document_id="doc-xlsx",
                source_ref="final_images/document.jpg",
                order_index=1,
            ),
            SourceImageAsset(
                asset_id="img-nearby",
                document_id="doc-xlsx",
                source_ref="final_images/nearby.jpg",
                order_index=2,
                nearby_evidence_ids=["ev-row-3"],
            ),
            SourceImageAsset(
                asset_id="img-primary",
                document_id="doc-xlsx",
                source_ref="final_images/primary.jpg",
                order_index=3,
                sheet_name="Sheet0",
                row_index=3,
                column_index=11,
                related_evidence_ids=["ev-row-3"],
            ),
        ],
    )

    units = build_visual_content_units_for_primary_record(
        source_model=source_model,
        primary_record=primary_record,
    )

    assert [unit.asset.asset_id for unit in units] == [
        "img-primary",
        "img-nearby",
        "img-document",
    ]
    assert [unit.relation for unit in units] == [
        "same_record_row",
        "near_primary_record_context",
        "document_context",
    ]


def test_resolve_mapping_decisions_normalizes_legacy_list_response_shape() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-phone",
            raw_name="手机号",
            slot_kind="text",
            expected_value_type="phone",
            context={},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="cand-1",
                    candidate_kind="text",
                    value_label="联系电话",
                    value_text="13800138000",
                    value_type="phone",
                    relation="same_record_row",
                    confidence_hint=0.9,
                    locator={"row_index": 3},
                    source_path="/input/source.xlsx",
                )
            ],
        ),
        AgentSlotPacket(
            slot_id="slot-name",
            raw_name="人员姓名",
            slot_kind="text",
            expected_value_type="person",
            context={},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="cand-2",
                    candidate_kind="text",
                    value_label="整改责任人",
                    value_text="杨恩赐",
                    value_type="person",
                    relation="same_record_row",
                    confidence_hint=0.75,
                    locator={"row_index": 3},
                    source_path="/input/source.xlsx",
                )
            ],
        ),
    ]

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            [
                {"slot_id": "slot-phone", "resolved_candidate_id": "cand-1"},
                {"slot_id": "slot-name", "resolved_candidate_id": "unresolved"},
            ],
            ensure_ascii=False,
        )

    decisions = resolve_mapping_decisions(slot_packets, decision_client=stub_client)

    assert [(item.slot_id, item.decision, item.candidate_id) for item in decisions] == [
        ("slot-phone", "candidate", "cand-1"),
        ("slot-name", "unresolved", None),
    ]


def test_resolve_mapping_decisions_normalizes_resolution_only_list_shape() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-owner",
            raw_name="责任单位负责人",
            slot_kind="text",
            expected_value_type="person",
            context={},
            candidates=[],
        )
    ]

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            [
                {"slot_id": "slot-owner", "resolution": "unresolved"},
            ],
            ensure_ascii=False,
        )

    decisions = resolve_mapping_decisions(slot_packets, decision_client=stub_client)

    assert [(item.slot_id, item.decision, item.candidate_id) for item in decisions] == [
        ("slot-owner", "unresolved", None),
    ]


def test_resolve_mapping_decisions_normalizes_resolutions_object_shape() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-owner",
            raw_name="责任单位负责人",
            slot_kind="text",
            expected_value_type="person",
            context={},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="cand-1",
                    candidate_kind="text",
                    value_label="整改责任人",
                    value_text="杨恩赐",
                    value_type="person",
                    relation="same_record_row",
                    confidence_hint=0.75,
                    locator={"row_index": 3},
                    source_path="/input/source.xlsx",
                )
            ],
        )
    ]

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            {
                "resolutions": [
                    {
                        "slot_id": "slot-owner",
                        "resolved": True,
                        "candidate_id": "cand-1",
                        "value_text": "杨恩赐",
                    }
                ]
            },
            ensure_ascii=False,
        )

    decisions = resolve_mapping_decisions(slot_packets, decision_client=stub_client)

    assert [(item.slot_id, item.decision, item.candidate_id) for item in decisions] == [
        ("slot-owner", "candidate", "cand-1"),
    ]


def test_resolve_mapping_decisions_normalizes_mappings_object_shape() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-owner",
            raw_name="责任单位负责人",
            slot_kind="text",
            expected_value_type="person",
            context={},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="cand-1",
                    candidate_kind="text",
                    value_label="整改责任人",
                    value_text="杨恩赐",
                    value_type="person",
                    relation="same_record_row",
                    confidence_hint=0.75,
                    locator={"row_index": 3},
                    source_path="/input/source.xlsx",
                )
            ],
        )
    ]

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            {
                "mappings": [
                    {
                        "slot_id": "slot-owner",
                        "resolution": "candidate",
                        "candidate_id": "cand-1",
                    }
                ]
            },
            ensure_ascii=False,
        )

    decisions = resolve_mapping_decisions(slot_packets, decision_client=stub_client)

    assert [(item.slot_id, item.decision, item.candidate_id) for item in decisions] == [
        ("slot-owner", "candidate", "cand-1"),
    ]


def test_resolve_mapping_decisions_normalizes_resolved_enum_to_candidate() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-owner",
            raw_name="责任单位负责人",
            slot_kind="text",
            expected_value_type="person",
            context={},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="cand-1",
                    candidate_kind="text",
                    value_label="整改责任人",
                    value_text="杨恩赐",
                    value_type="person",
                    relation="same_record_row",
                    confidence_hint=0.75,
                    locator={"row_index": 3},
                    source_path="/input/source.xlsx",
                )
            ],
        )
    ]

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": "slot-owner",
                        "decision": "resolved",
                        "candidate_id": "cand-1",
                        "reason": "resolved by model",
                    }
                ]
            },
            ensure_ascii=False,
        )

    decisions = resolve_mapping_decisions(slot_packets, decision_client=stub_client)

    assert [(item.slot_id, item.decision, item.candidate_id) for item in decisions] == [
        ("slot-owner", "candidate", "cand-1"),
    ]


def test_resolve_mapping_decisions_retries_when_output_is_semantically_invalid() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-owner",
            raw_name="责任单位负责人",
            slot_kind="text",
            expected_value_type="person",
            context={},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="cand-1",
                    candidate_kind="text",
                    value_label="整改责任人",
                    value_text="杨恩赐",
                    value_type="person",
                    relation="same_record_row",
                    confidence_hint=0.75,
                    locator={"row_index": 3},
                    source_path="/input/source.xlsx",
                )
            ],
        )
    ]
    calls: list[str] = []

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        calls.append(user_prompt)
        if len(calls) == 1:
            return json.dumps(
                {
                    "schema_version": "doctransai_agent_mapping_decision_v1",
                    "decisions": [
                        {
                            "slot_id": "slot-owner",
                            "decision": "unresolved",
                            "candidate_id": "cand-1",
                            "generated_value": "杨恩赐",
                            "confidence": 0.75,
                            "reason": "contradictory",
                        }
                    ],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-owner",
                        "decision": "candidate",
                        "candidate_id": "cand-1",
                        "generated_value": None,
                        "confidence": 0.84,
                        "reason": "fixed",
                    }
                ],
            },
            ensure_ascii=False,
        )

    trace = resolve_mapping_decisions_with_trace(slot_packets, decision_client=stub_client)

    assert isinstance(trace, AgentResolutionTrace)
    assert len(calls) == 2
    assert trace.repaired is True
    assert trace.repair_raw_output_text is not None
    assert [(item.slot_id, item.decision, item.candidate_id) for item in trace.decisions] == [
        ("slot-owner", "candidate", "cand-1"),
    ]
    assert "ERRORS:" in calls[1]


def test_resolve_mapping_decisions_accepts_json_fenced_code_block_response() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-owner",
            raw_name="责任单位负责人",
            slot_kind="text",
            expected_value_type="person",
            context={},
            candidates=[
                AgentCandidatePacket(
                    candidate_id="cand-1",
                    candidate_kind="text",
                    value_label="整改责任人",
                    value_text="杨恩赐",
                    value_type="person",
                    relation="same_record_row",
                    confidence_hint=0.75,
                    locator={"row_index": 3},
                    source_path="/input/source.xlsx",
                )
            ],
        )
    ]

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        return """```json
{
  "schema_version": "doctransai_agent_mapping_decision_v1",
  "decisions": [
    {
      "slot_id": "slot-owner",
      "decision": "candidate",
      "candidate_id": "cand-1",
      "generated_value": null,
      "confidence": 0.84,
      "reason": "fenced json"
    }
  ]
}
```"""

    decisions = resolve_mapping_decisions(slot_packets, decision_client=stub_client)

    assert [(item.slot_id, item.decision, item.candidate_id) for item in decisions] == [
        ("slot-owner", "candidate", "cand-1"),
    ]


def test_prepare_agent_slot_packets_filters_candidates_by_expected_type() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="range-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 3},
                values=[
                    SourceValue(canonical_key="项目名称", value="西香TJ3标", raw_label="项目名称"),
                    SourceValue(canonical_key="联系电话", value="13800138000", raw_label="联系电话"),
                    SourceValue(canonical_key="整改责任人", value="杨恩赐", raw_label="整改责任人"),
                    SourceValue(canonical_key="责任单位", value="云南道桥建筑工程有限公司", raw_label="责任单位"),
                ],
            )
        ]
    )
    template_slots_by_id = {
        "slot-phone": TemplateSlot(
            slot_id="slot-phone",
            raw_name="手机号",
            canonical_name="手机号",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        ),
        "slot-owner": TemplateSlot(
            slot_id="slot-owner",
            raw_name="人员姓名",
            canonical_name="人员姓名",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=1),
        ),
    }
    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=source_model.records[0],
        unresolved_slots=[
            UnresolvedSlot(slot_id="slot-phone", canonical_key="手机号", reason_code="missing_value", message="missing"),
            UnresolvedSlot(slot_id="slot-owner", canonical_key="人员姓名", reason_code="ambiguous_match", message="ambiguous"),
        ],
        template_slots_by_id=template_slots_by_id,
    )

    packet_by_slot = {packet.slot_id: packet for packet in packets}

    assert [(candidate.value_label, candidate.value_type) for candidate in packet_by_slot["slot-phone"].candidates] == [
        ("联系电话", "phone"),
    ]
    assert [(candidate.value_label, candidate.value_type) for candidate in packet_by_slot["slot-owner"].candidates] == [
        ("整改责任人", "person"),
    ]


def test_prepare_agent_slot_packets_keeps_typed_document_context_candidates() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="row-primary",
                document_id="doc-1",
                source_path="/input/source.docx",
                locator={"row_index": 2},
                values=[
                    SourceValue(canonical_key="施工单位", value="施工单位：广西路桥", raw_label="施工单位"),
                ],
            ),
            SourceRecord(
                record_id="row-context",
                document_id="doc-1",
                source_path="/input/source.docx",
                locator={"row_index": 3},
                values=[
                    SourceValue(canonical_key="监理单位", value="监理单位：广西恒大", raw_label="监理单位"),
                ],
            ),
        ]
    )
    template_slots_by_id = {
        "slot-org": TemplateSlot(
            slot_id="slot-org",
            raw_name="接收单位",
            canonical_name="接收单位",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        )
    }

    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=source_model.records[0],
        unresolved_slots=[
            UnresolvedSlot(slot_id="slot-org", canonical_key="接收单位", reason_code="ambiguous_match", message="ambiguous"),
        ],
        template_slots_by_id=template_slots_by_id,
    )

    candidates = packets[0].candidates
    assert [candidate.candidate_id for candidate in candidates] == [
        "row-primary:0",
        "row-context:0",
    ]
    assert candidates[1].relation == "document_context"


def test_prepare_agent_slot_packets_keeps_unresolved_slots_without_candidates_for_generation() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.doc",
                locator={"page_anchor": "page_1"},
                values=[
                    SourceValue(
                        canonical_key="text",
                        value="（一）龚文升劳务队\n落实整改管理人员：韦俊铭",
                        raw_label="text",
                    ),
                ],
            )
        ]
    )
    template_slots_by_id = {
        "slot-org": TemplateSlot(
            slot_id="slot-org",
            raw_name="责任单位",
            canonical_name="责任单位",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="table_cell", table_index=0, row_index=0, column_index=0),
        )
    }

    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=source_model.records[0],
        unresolved_slots=[
            UnresolvedSlot(slot_id="slot-org", canonical_key="责任单位", reason_code="missing_value", message="missing"),
        ],
        template_slots_by_id=template_slots_by_id,
    )

    assert len(packets) == 1
    assert packets[0].slot_id == "slot-org"
    assert packets[0].expected_value_type == "organization"
    assert packets[0].candidates == []


def test_prepare_agent_slot_packets_can_omit_text_candidates_without_dropping_image_candidates() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.pdf",
                values=[
                    SourceValue(canonical_key="项目名称", value="AI-数理双驱动", raw_label="项目名称"),
                ],
            )
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="img-1",
                source_ref="images/figure.png",
                nearby_text_after=["技术路线图"],
            )
        ],
    )
    template_slots_by_id = {
        "slot-name": TemplateSlot(
            slot_id="slot-name",
            raw_name="成果名称",
            canonical_name="成果名称",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="table_cell_blank", table_index=0, row_index=0, column_index=1),
        ),
        "slot-image": TemplateSlot(
            slot_id="slot-image",
            raw_name="成果图片",
            canonical_name="成果图片",
            slot_kind="image",
            address=SlotAddress(format_key="docx", address_kind="table_cell_blank", table_index=0, row_index=1, column_index=1),
        ),
    }

    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=source_model.records[0],
        unresolved_slots=[
            UnresolvedSlot(slot_id="slot-name", canonical_key="成果名称", reason_code="missing_value", message="missing"),
            UnresolvedSlot(slot_id="slot-image", canonical_key="成果图片", reason_code="missing_image", message="missing"),
        ],
        template_slots_by_id=template_slots_by_id,
        include_text_candidates=False,
    )

    packet_by_slot = {packet.slot_id: packet for packet in packets}

    assert packet_by_slot["slot-name"].candidates == []
    assert len(packet_by_slot["slot-image"].candidates) == 1


def test_long_generic_text_is_not_treated_as_datetime_candidate() -> None:
    value = SourceValue(
        canonical_key="text",
        raw_label="text",
        value=(
            "为贯彻落实项目安全生产检查制度，及时发现并消除现场事故隐患，"
            "2022年3月27日，由项目部领导班子带队进行了安全生产大检查。"
        ),
    )

    assert infer_source_value_type(value) == "text"


def test_prepare_agent_slot_packets_does_not_offer_full_document_text_as_direct_candidate() -> None:
    long_text = (
        "广西路桥工程集团有限公司\n"
        "关于开展3月份安全生产大检查情况的通报\n"
        "二、发现的隐患问题、负责人及落实整改管理人员\n"
        "（一）龚文升劳务队\n"
        "3. 发现的隐患问题：\n"
        "（1）二工区围挡未及时封闭；\n"
        "（2）有村民进入施工现场；\n"
        "三、整改要求\n"
        "（一）重新设置倒地的围挡；\n"
        "（二）驱离进入现场的村民；"
    )
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.doc",
                values=[SourceValue(canonical_key="text", value=long_text, raw_label="text")],
            )
        ]
    )
    template_slots_by_id = {
        "slot-desc": TemplateSlot(
            slot_id="slot-desc",
            raw_name="隐患描述",
            canonical_name="隐患描述",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        )
    }

    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=source_model.records[0],
        unresolved_slots=[
            UnresolvedSlot(slot_id="slot-desc", canonical_key="隐患描述", reason_code="missing_value", message="missing"),
        ],
        template_slots_by_id=template_slots_by_id,
    )

    assert len(packets) == 1
    assert packets[0].candidates == []


def test_prepare_agent_slot_packets_keeps_small_candidate_inventory_and_ranks_by_slot_relevance() -> None:
    values = [
        SourceValue(canonical_key=f"字段{index}", value=f"无关值{index}", raw_label=f"字段{index}")
        for index in range(40)
    ]
    values.append(SourceValue(canonical_key="整改要求", value="重新设置倒地的围挡", raw_label="整改要求"))
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="row-1",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"row_index": 3},
                values=values,
            )
        ]
    )
    template_slots_by_id = {
        "slot-requirement": TemplateSlot(
            slot_id="slot-requirement",
            raw_name="整改意见",
            canonical_name="整改要求",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        )
    }

    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=source_model.records[0],
        unresolved_slots=[
            UnresolvedSlot(slot_id="slot-requirement", canonical_key="整改要求", reason_code="missing_value", message="missing"),
        ],
        template_slots_by_id=template_slots_by_id,
    )

    assert len(packets[0].candidates) == 41
    assert packets[0].candidates[0].value_label == "整改要求"


def test_prepare_agent_shared_context_keeps_full_small_record_inventory() -> None:
    source_records = [
        SourceRecord(
            record_id=f"row-{index}",
            document_id="doc-1",
            source_path="/input/source.docx",
            locator={"row_index": index},
            values=[
                SourceValue(
                    canonical_key="检查情况",
                    raw_label="检查情况",
                    value="很长的检查情况" * 80,
                )
            ],
        )
        for index in range(90)
    ]
    source_model = SourceModel(records=source_records)
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[],
    )

    shared_context = prepare_agent_shared_context(
        source_model=source_model,
        primary_record=source_records[-1],
        template_slots_by_id={},
        template_model=template_model,
    )

    source_overview = shared_context["source_overview"]
    included_ids = {record["record_id"] for record in source_overview["records"]}

    assert source_overview["record_count"] == 90
    assert source_overview["records_included_count"] == 90
    assert source_overview["records_truncated"] is False
    assert "row-89" in included_ids
    assert all(len(value["value"]) <= 1200 for record in source_overview["records"] for value in record["values"])
    assert not any(value["truncated"] is True for record in source_overview["records"] for value in record["values"])


def test_prepare_agent_slot_packets_exposes_image_nearby_context() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.doc",
                evidence_id="ev-1",
                locator={"page_anchor": "page_1"},
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
                asset_id="img-intro",
                source_ref="images/intro.jpg",
                source_path="/input/source.doc",
                page_anchor="page_1",
                order_index=8,
                nearby_text_after=["现场便道围挡未见缺失。"],
            ),
            SourceImageAsset(
                asset_id="img-hazard",
                source_ref="images/hazard.jpg",
                source_path="/input/source.doc",
                page_anchor="page_1",
                block_id="blk-image",
                order_index=28,
                nearby_text_before=["附件:"],
                nearby_text_after=["二工区围挡未及时封闭"],
                nearby_evidence_ids=["ev-1"],
            ),
        ],
    )
    template_slots_by_id = {
        "slot-photo": TemplateSlot(
            slot_id="slot-photo",
            raw_name="隐患照片",
            canonical_name="隐患照片",
            slot_kind="image",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        )
    }

    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=source_model.records[0],
        unresolved_slots=[
            UnresolvedSlot(slot_id="slot-photo", canonical_key="隐患照片", reason_code="missing_image", message="missing"),
        ],
        template_slots_by_id=template_slots_by_id,
    )

    candidate_by_id = {candidate.candidate_id: candidate for candidate in packets[0].candidates}
    assert candidate_by_id["img-intro"].relation == "document_context"
    hazard_candidate = candidate_by_id["img-hazard"]

    assert hazard_candidate.relation == "near_primary_record_context"
    assert "二工区围挡未及时封闭" in hazard_candidate.value_text
    assert hazard_candidate.locator["page_anchor"] == "page_1"
    assert hazard_candidate.locator["block_id"] == "blk-image"
    assert hazard_candidate.locator["order_index"] == 28
    assert hazard_candidate.locator["nearby_text_before"] == ["附件:"]
    assert hazard_candidate.locator["nearby_text_after"] == ["二工区围挡未及时封闭"]
    assert hazard_candidate.locator["nearby_evidence_ids"] == ["ev-1"]


def test_short_date_value_is_still_treated_as_datetime_candidate() -> None:
    value = SourceValue(canonical_key="检查日期", raw_label="检查日期", value="2022年3月27日")

    assert infer_source_value_type(value) == "datetime"


def test_dot_separated_date_value_is_treated_as_datetime_candidate() -> None:
    value = SourceValue(canonical_key="整改期限", raw_label="整改期限", value="2022.3.12")

    assert infer_source_value_type(value) == "datetime"


def test_short_numeric_identifier_label_is_treated_as_identifier() -> None:
    value = SourceValue(canonical_key="序号", raw_label="序号", value="4")

    assert infer_source_value_type(value) == "identifier"


def test_numeric_value_with_organization_like_table_title_is_not_organization() -> None:
    value = SourceValue(
        canonical_key="东城环资公司安全检查销项表",
        raw_label="东城环资公司安全检查销项表",
        value="1",
    )

    assert infer_source_value_type(value) == "text"


def test_resolve_mapping_decisions_allows_generated_value_without_candidates_when_supported_by_context() -> None:
    slot_packets = [
        AgentSlotPacket(
            slot_id="slot-org",
            raw_name="责任单位",
            slot_kind="text",
            expected_value_type="organization",
            context={},
            candidates=[],
        )
    ]
    shared_context = {
        "source_overview": {
            "records": [
                {
                    "record_id": "ev-1",
                    "values": [
                        {
                            "canonical_key": "text",
                            "raw_label": "text",
                            "value": "二、发现的隐患问题、负责人及落实整改管理人员\n（一）龚文升劳务队",
                        }
                    ],
                }
            ]
        }
    }

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        assert "use the shared source overview" in user_prompt
        assert "Do not output full document text" in user_prompt
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-org",
                        "decision": "generated",
                        "candidate_id": None,
                        "generated_value": "龚文升劳务队",
                        "confidence": 0.82,
                        "reason": "extracted from source overview list heading",
                    }
                ],
            },
            ensure_ascii=False,
        )

    decisions = resolve_mapping_decisions(slot_packets, decision_client=stub_client, shared_context=shared_context)

    assert [(item.slot_id, item.decision, item.generated_value) for item in decisions] == [
        ("slot-org", "generated", "龚文升劳务队"),
    ]


def test_prepare_agent_shared_context_embeds_full_template_and_source_context() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="range-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 3},
                values=[
                    SourceValue(canonical_key="项目名称", value="西香TJ3标", raw_label="项目名称"),
                    SourceValue(canonical_key="隐患描述", value="临边防护缺失", raw_label="隐患描述"),
                ],
            ),
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0"},
                values=[
                    SourceValue(canonical_key="text", value="项目名称：西香TJ3标 | 隐患描述：临边防护缺失", raw_label="text"),
                ],
            ),
        ],
        diagnostics=[
            {"diagnostic_id": "diag-1", "code": "table_density_mismatch", "severity": "medium", "source_path": "/input/source.xlsx"}
        ],
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
                context_before="项目：",
            ),
            TemplateSlot(
                slot_id="slot-desc",
                raw_name="隐患描述",
                canonical_name="隐患描述",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=1),
                context_before="隐患：",
            ),
        ],
    )

    shared_context = prepare_agent_shared_context(
        source_model=source_model,
        primary_record=source_model.records[0],
        template_slots_by_id={slot.slot_id: slot for slot in template_model.slots},
        template_model=template_model,
    )

    assert shared_context["template_overview"]["template_path"] == "/templates/out.docx"
    assert len(shared_context["template_overview"]["slots"]) == 2
    assert shared_context["template_overview"]["document_view"]
    assert shared_context["full_agent_context"]["schema_version"] == "doctransai_full_agent_context_v1"
    assert shared_context["full_agent_context"]["full_source_context"]["record_count"] == 2
    assert [record["record_id"] for record in shared_context["full_agent_context"]["full_source_context"]["records"]] == [
        "range-3",
        "ev-1",
    ]
    assert shared_context["full_agent_context"]["full_source_context"]["diagnostics"][0]["code"] == "table_density_mismatch"
    assert shared_context["full_agent_context"]["full_template_context"]["slot_count"] == 2
    assert shared_context["full_agent_context"]["navigation_context"]["authority"] == "navigation_only_not_evidence"
    assert shared_context["full_agent_context"]["navigation_context"]["source_instance_overview"]["primary_record_id"] == "range-3"
    assert shared_context["full_agent_context"]["task_context"]["primary_record_id"] == "range-3"
    assert "source_document_view" in shared_context
    assert shared_context["source_document_view"] == shared_context["full_agent_context"]["full_source_context"]["document_view"]
    assert (
        shared_context["source_instance_overview"]
        == shared_context["full_agent_context"]["navigation_context"]["source_instance_overview"]
    )
    assert (
        shared_context["source_cluster_plan"]
        == shared_context["full_agent_context"]["navigation_context"]["source_cluster_plan"]
    )
    assert "项目名称: 西香TJ3标" in shared_context["source_document_view"]
    assert "隐患描述: 临边防护缺失" in shared_context["source_document_view"]
    assert shared_context["source_overview"]["primary_record_id"] == "range-3"
    assert len(shared_context["source_overview"]["records"]) == 2
    assert shared_context["source_overview"]["context_status"] == {
        "record_count": 2,
        "records_included_count": 2,
        "records_truncated": False,
        "truncated_value_count": 0,
        "diagnostic_count": 1,
        "diagnostics_included_count": 1,
        "diagnostics_truncated": False,
    }
    assert shared_context["source_overview"]["diagnostics"][0]["code"] == "table_density_mismatch"
    assert shared_context["source_instance_overview"]["primary_record_id"] == "range-3"
    assert shared_context["source_instance_overview"]["primary_instance"]["instance_kind"] == "sheet_row"
    assert shared_context["source_instance_overview"]["primary_instance"]["row_index"] == 3
    assert shared_context["source_instance_overview"]["primary_cluster"]["cluster_kind"] == "sheet"
    assert shared_context["source_instance_overview"]["context_status"] == {
        "instance_count": 2,
        "cluster_count": 2,
        "primary_cluster_instance_count": 1,
        "primary_cluster_record_count": 1,
        "primary_cluster_asset_count": 0,
        "constraint_scoped_primary": True,
    }


def test_prepare_agent_shared_context_embeds_source_cluster_plan_for_repeat_regions() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="range-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 3},
                values=[SourceValue(canonical_key="隐患描述", value="围挡缺失", raw_label="隐患描述")],
            ),
            SourceRecord(
                record_id="range-4",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 4},
                values=[SourceValue(canonical_key="隐患描述", value="临边防护缺失", raw_label="隐患描述")],
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
                slot_id="slot-desc",
                raw_name="隐患描述",
                canonical_name="隐患描述",
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

    shared_context = prepare_agent_shared_context(
        source_model=source_model,
        primary_record=source_model.records[0],
        template_slots_by_id={slot.slot_id: slot for slot in template_model.slots},
        template_model=template_model,
    )

    assert "source_cluster_plan" in shared_context
    assert shared_context["source_cluster_plan"]["context_status"] == {
        "cluster_count": 1,
        "repeat_region_count": 1,
    }
    assert shared_context["source_cluster_plan"]["clusters"][0]["record_count"] == 2
    assert shared_context["source_cluster_plan"]["repeat_regions"][0]["region_id"] == "region-1"
    assert shared_context["source_cluster_plan"]["repeat_regions"][0]["instance_count_by_cluster_id"] == {
        shared_context["source_cluster_plan"]["clusters"][0]["cluster_id"]: 2
    }
    assert (
        shared_context["source_cluster_plan"]
        == shared_context["full_agent_context"]["navigation_context"]["source_cluster_plan"]
    )


def test_prepare_agent_shared_context_exposes_record_primary_without_making_it_constraint_scoped() -> None:
    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="ev-1",
                document_id="doc-1",
                source_path="/input/source.pdf",
                evidence_id="ev-1",
                locator={"page_anchor": "page_1"},
                values=[SourceValue(canonical_key="text", value="成果名称：智慧监测平台", raw_label="text")],
            )
        ]
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[],
    )

    shared_context = prepare_agent_shared_context(
        source_model=source_model,
        primary_record=source_model.records[0],
        template_slots_by_id={},
        template_model=template_model,
    )

    assert shared_context["source_overview"]["primary_record_id"] == "ev-1"
    assert shared_context["source_instance_overview"]["primary_record_id"] == "ev-1"
    assert shared_context["source_instance_overview"]["primary_instance"]["instance_kind"] == "record"
    assert shared_context["source_instance_overview"]["primary_cluster"]["cluster_kind"] == "document"
    assert shared_context["source_instance_overview"]["context_status"] == {
        "instance_count": 1,
        "cluster_count": 1,
        "primary_cluster_instance_count": 1,
        "primary_cluster_record_count": 1,
        "primary_cluster_asset_count": 0,
        "constraint_scoped_primary": False,
    }
    assert (
        shared_context["source_instance_overview"]
        == shared_context["full_agent_context"]["navigation_context"]["source_instance_overview"]
    )


def test_prepare_agent_shared_context_exposes_truncation_status() -> None:
    source_records = [
        SourceRecord(
            record_id=f"record-{index}",
            document_id="doc-1",
            source_path="/input/large.pdf",
            locator={"page_anchor": f"page_{index}"},
            values=[
                SourceValue(
                    canonical_key="text",
                    raw_label="text",
                    value=("长文本" * 500) if index == 0 else f"正文片段 {index}",
                )
            ],
        )
        for index in range(270)
    ]
    source_model = SourceModel(records=source_records, diagnostics=[{"diagnostic_id": f"diag-{index}"} for index in range(35)])
    template_model = TemplateModel(
        template_id="template-1",
        template_path="/templates/out.docx",
        format_key="docx",
        analyzer_key="fixture",
        slots=[],
    )

    shared_context = prepare_agent_shared_context(
        source_model=source_model,
        primary_record=source_records[0],
        template_slots_by_id={},
        template_model=template_model,
    )

    status = shared_context["source_overview"]["context_status"]
    assert status["record_count"] == 270
    assert status["records_included_count"] == 256
    assert status["records_truncated"] is True
    assert status["truncated_value_count"] >= 1
    assert status["diagnostic_count"] == 35
    assert status["diagnostics_included_count"] == 30
    assert status["diagnostics_truncated"] is True
    assert "record-0" in shared_context["source_document_view"]
    assert "content_truncated_for_agent_input" in shared_context["source_overview"]["context_diagnostics"][0]["code"]
    assert shared_context["full_agent_context"]["full_source_context"]["record_count"] == 270
    assert shared_context["full_agent_context"]["full_source_context"]["records"][-1]["record_id"] == "record-269"
    assert shared_context["full_agent_context"]["full_source_context"]["records"][0]["values"][0]["value"] == "长文本" * 500
    assert "record-269" in shared_context["full_agent_context"]["full_source_context"]["document_view"]
    assert shared_context["source_document_view"] == shared_context["full_agent_context"]["full_source_context"]["document_view"]


def test_resolve_mapping_decisions_sends_template_visual_pages_when_client_supports_user_parts(tmp_path) -> None:
    template_path = tmp_path / "template.docx"
    from docx import Document

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.save(template_path)

    source_model = SourceModel(
        records=[
            SourceRecord(
                record_id="range-3",
                document_id="doc-1",
                source_path="/input/source.xlsx",
                locator={"sheet_name": "Sheet0", "row_index": 3},
                values=[
                    SourceValue(canonical_key="项目名称", value="西香TJ3标", raw_label="项目名称"),
                ],
            )
        ]
    )
    template_model = TemplateModel(
        template_id="template-1",
        template_path=str(template_path),
        format_key="docx",
        analyzer_key="fixture",
        slots=[
            TemplateSlot(
                slot_id="slot-project",
                raw_name="项目名称",
                canonical_name="项目名称",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            ),
        ],
    )

    packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=source_model.records[0],
        unresolved_slots=[
            UnresolvedSlot(slot_id="slot-project", canonical_key="项目名称", reason_code="ambiguous_match", message="ambiguous"),
        ],
        template_slots_by_id={slot.slot_id: slot for slot in template_model.slots},
    )
    shared_context = prepare_agent_shared_context(
        source_model=source_model,
        primary_record=source_model.records[0],
        template_model=template_model,
        template_slots_by_id={slot.slot_id: slot for slot in template_model.slots},
    )

    captured = {}

    def stub_client(*, system_prompt: str, user_prompt: str, user_parts=None) -> str:
        captured["user_parts"] = user_parts
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": [
                    {
                        "slot_id": "slot-project",
                        "decision": "candidate",
                        "candidate_id": packets[0].candidates[0].candidate_id,
                        "generated_value": None,
                        "confidence": 0.9,
                        "reason": "ok",
                    }
                ],
            },
            ensure_ascii=False,
        )

    decisions = resolve_mapping_decisions(
        packets,
        decision_client=stub_client,
        shared_context=shared_context,
    )

    assert decisions[0].decision == "candidate"
    assert isinstance(captured["user_parts"], list)
    assert captured["user_parts"][0]["type"] == "text"
    assert any(item["type"] == "image_url" for item in captured["user_parts"][1:])
