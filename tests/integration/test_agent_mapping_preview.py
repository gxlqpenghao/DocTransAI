from __future__ import annotations

import json
from pathlib import Path

from doctransai.data_layer import read_parsed_document_bundle
from doctransai.source_model import adapt_source_corpus
from doctransai.source_model.instances import build_source_instance_index
from doctransai.workflows.agent_mapping_preview import build_agent_mapping_preview


def test_build_agent_mapping_preview_from_real_bundle_writes_small_person_batch(tmp_path: Path) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = Path(
        "V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx"
    ).resolve()
    output_path = tmp_path / "preview" / "agent_input.json"

    payload = build_agent_mapping_preview(
        bundle_path=bundle_path,
        template_path=template_path,
        primary_record_id="range_1cd5d52e9f25",
        output_path=output_path,
    )

    assert output_path.exists() is True
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload
    assert payload["bundle_path"] == str(bundle_path)
    assert payload["template_path"] == str(template_path)
    assert payload["primary_record_id"] == "range_1cd5d52e9f25"
    assert "template_overview" in payload
    assert "source_overview" in payload
    assert "source_instance_overview" in payload
    assert "source_cluster_plan" in payload
    assert payload["full_agent_context"]["schema_version"] == "doctransai_full_agent_context_v1"
    assert payload["full_agent_context"]["task_context"]["primary_record_id"] == "range_1cd5d52e9f25"
    assert payload["full_agent_context"]["task_context"]["source_instance_id"] is None
    assert payload["full_agent_context"]["navigation_context"]["source_instance_overview"]["primary_record_id"] == "range_1cd5d52e9f25"
    assert payload["source_instance_overview"] == payload["full_agent_context"]["navigation_context"]["source_instance_overview"]
    assert payload["source_cluster_plan"] == payload["full_agent_context"]["navigation_context"]["source_cluster_plan"]
    assert payload["unresolved_slots"] == [
        {
            "slot_id": "docx-table-0-2",
            "canonical_key": "责任单位负责人",
            "reason_code": "ambiguous_match",
            "message": "Multiple candidates remain tied for 责任单位负责人.",
        },
        {
            "slot_id": "docx-table-0-5",
            "canonical_key": "手机号",
            "reason_code": "missing_value",
            "message": "No candidate was found for 手机号.",
        },
        {
            "slot_id": "docx-table-0-6",
            "canonical_key": "人员姓名",
            "reason_code": "ambiguous_match",
            "message": "Multiple candidates remain tied for 人员姓名.",
        },
        {
            "slot_id": "docx-table-0-blank-7",
            "canonical_key": "duration_days_blank_1",
            "reason_code": "missing_value",
            "message": "No candidate was found for duration_days_blank_1.",
        },
    ]
    assert [item["raw_name"] for item in payload["slot_packets"]] == [
        "责任单位负责人",
        "手机号",
        "人员姓名",
        "duration_days_blank_1",
    ]
    assert [item["expected_value_type"] for item in payload["slot_packets"]] == ["person", "phone", "person", "text"]
    packets_by_name = {item["raw_name"]: item for item in payload["slot_packets"]}
    assert [item["value_type"] for item in packets_by_name["责任单位负责人"]["candidates"]] == ["person"] * 21
    assert packets_by_name["手机号"]["candidates"] == []
    assert [item["value_type"] for item in packets_by_name["人员姓名"]["candidates"]] == ["person"] * 21
    assert packets_by_name["duration_days_blank_1"]["candidates"]
    assert packets_by_name["责任单位负责人"]["candidates"][0]["relation"] == "same_record_row"
    assert packets_by_name["责任单位负责人"]["candidates"][0]["locator"]["column_index"] == 17
    assert any(item["relation"] == "document_context" for item in packets_by_name["责任单位负责人"]["candidates"])


def test_build_agent_mapping_preview_can_select_primary_record_by_source_instance_id(tmp_path: Path) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = Path(
        "V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx"
    ).resolve()
    source_instance_id = _source_instance_id_for_record(bundle_path, "range_1cd5d52e9f25")

    payload = build_agent_mapping_preview(
        bundle_path=bundle_path,
        template_path=template_path,
        source_instance_id=source_instance_id,
    )

    assert payload["primary_record_id"] == "range_1cd5d52e9f25"
    assert payload["source_instance_id"] == source_instance_id
    assert payload["full_agent_context"]["task_context"]["source_instance_id"] == source_instance_id
    assert payload["source_overview"]["primary_record_id"] == "range_1cd5d52e9f25"
    assert payload["source_instance_overview"]["primary_record_id"] == "range_1cd5d52e9f25"
    assert payload["source_instance_overview"] == payload["full_agent_context"]["navigation_context"]["source_instance_overview"]
    assert [item["raw_name"] for item in payload["slot_packets"]] == [
        "责任单位负责人",
        "手机号",
        "人员姓名",
        "duration_days_blank_1",
    ]


def _source_instance_id_for_record(bundle_path: Path, record_id: str) -> str:
    source_model = adapt_source_corpus(read_parsed_document_bundle(bundle_path))
    instance = build_source_instance_index(source_model).instance_for_record(record_id)
    assert instance is not None
    return instance.instance_id
