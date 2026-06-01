from __future__ import annotations

import json
from pathlib import Path

from doctransai.llm import DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV
from doctransai.data_layer import read_parsed_document_bundle
from doctransai.source_model import adapt_source_corpus
from doctransai.source_model.instances import build_source_instance_index
from doctransai.workflows.agent_mapping_resolution import run_agent_mapping_resolution


def test_run_agent_mapping_resolution_writes_real_decision_output_with_stub(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "100000000")
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, "10000000")
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = Path(
        "V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx"
    ).resolve()
    output_path = tmp_path / "preview" / "agent_output.json"

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

    payload = run_agent_mapping_resolution(
        bundle_path=bundle_path,
        template_path=template_path,
        primary_record_id="range_1cd5d52e9f25",
        output_path=output_path,
        decision_client=stub_client,
    )

    assert output_path.exists() is True
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload
    assert output_path.with_suffix(".raw_output.txt").exists() is True
    assert output_path.with_suffix(".repair_output.txt").exists() is False
    assert payload["schema_version"] == "doctransai_agent_mapping_decision_v1"
    assert payload["bundle_path"] == str(bundle_path)
    assert payload["template_path"] == str(template_path)
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
    assert [item["raw_name"] for item in payload["slot_packets"]] == [
        "责任单位负责人",
        "手机号",
        "人员姓名",
        "datetime_day_blank_1",
    ]
    assert [(item["slot_id"], item["decision"]) for item in payload["decisions"]] == [
        ("docx-table-0-2", "candidate"),
        ("docx-table-0-5", "unresolved"),
        ("docx-table-0-6", "unresolved"),
        ("docx-table-0-blank-7", "unresolved"),
    ]


def test_run_agent_mapping_resolution_can_select_primary_record_by_source_instance_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "100000000")
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, "10000000")
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = Path(
        "V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx"
    ).resolve()
    source_instance_id = _source_instance_id_for_record(bundle_path, "range_1cd5d52e9f25")

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1].split("\nPREVIOUS_OUTPUT:\n", 1)[0])
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
                        "reason": "tooling selection smoke test",
                    }
                    for slot in payload["slots"]
                ],
            },
            ensure_ascii=False,
        )

    payload = run_agent_mapping_resolution(
        bundle_path=bundle_path,
        template_path=template_path,
        source_instance_id=source_instance_id,
        decision_client=stub_client,
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
        "datetime_day_blank_1",
    ]


def _source_instance_id_for_record(bundle_path: Path, record_id: str) -> str:
    source_model = adapt_source_corpus(read_parsed_document_bundle(bundle_path))
    instance = build_source_instance_index(source_model).instance_for_record(record_id)
    assert instance is not None
    return instance.instance_id


def test_run_agent_mapping_resolution_writes_repair_audit_files_when_retry_happens(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_REQUEST_BYTES_ENV, "100000000")
    monkeypatch.setenv(DOCTRANSAI_LLM_MAX_INPUT_CHARS_ENV, "10000000")
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = Path(
        "V1文档审核集/02_目标模板_Template/03_DOCX处罚通知单/质量安全检查处罚通知单（分公司）.docx"
    ).resolve()
    output_path = tmp_path / "preview" / "agent_output.json"
    calls = {"count": 0}

    def stub_client(*, system_prompt: str, user_prompt: str) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            return json.dumps(
                {
                    "schema_version": "doctransai_agent_mapping_decision_v1",
                    "decisions": [
                        {
                            "slot_id": "docx-table-0-2",
                            "decision": "unresolved",
                            "candidate_id": "range_1cd5d52e9f25:14",
                            "generated_value": "杨恩赐",
                            "confidence": 0.75,
                            "reason": "contradictory",
                        }
                    ],
                },
                ensure_ascii=False,
            )
        payload = json.loads(user_prompt.split("INPUT_JSON:\n", 1)[1].split("\nPREVIOUS_OUTPUT:\n", 1)[0])
        decisions = [
            {
                "slot_id": slot["slot_id"],
                "decision": "unresolved",
                "candidate_id": None,
                "generated_value": None,
                "confidence": 0.0,
                "reason": "no safe candidate",
            }
            for slot in payload["slots"]
        ]
        decisions[0] = {
            "slot_id": "docx-table-0-2",
            "decision": "candidate",
            "candidate_id": "range_1cd5d52e9f25:14",
            "generated_value": None,
            "confidence": 0.84,
            "reason": "fixed",
        }
        return json.dumps(
            {
                "schema_version": "doctransai_agent_mapping_decision_v1",
                "decisions": decisions,
            },
            ensure_ascii=False,
        )

    payload = run_agent_mapping_resolution(
        bundle_path=bundle_path,
        template_path=template_path,
        primary_record_id="range_1cd5d52e9f25",
        output_path=output_path,
        decision_client=stub_client,
    )

    assert calls["count"] == 2
    assert payload["repaired"] is True
    assert output_path.with_suffix(".raw_output.txt").exists() is True
    assert output_path.with_suffix(".repair_output.txt").exists() is True
