from __future__ import annotations

import json
from pathlib import Path

import pytest

from doctransai.agentic_mapping.mapper import (
    DOCTRANSAI_AGENTIC_MAX_INLINE_PAGE_IMAGES_ENV,
    DOCTRANSAI_AGENTIC_PROVIDER_MAX_INPUT_CHARS_ENV,
    AgentDecision,
    DEFAULT_AGENTIC_PROVIDER_MAX_INPUT_CHARS,
    map_slots_with_agent,
)
from doctransai.llm.client import DoctransaiLLMInputTooLargeError


def test_map_slots_with_agent_sends_evidence_package_to_keyword_client() -> None:
    calls: list[dict[str, str]] = []

    def fake_client(*, system_prompt: str, user_prompt: str) -> str:
        calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": "slot-project",
                        "decision": "text_fill",
                        "value": "智慧园区改造",
                        "source_refs": ["record/project-name"],
                        "target_ref": {"format_key": "docx", "target_kind": "placeholder", "paragraph_index": 2},
                        "confidence": 0.93,
                        "reason": "source structured record directly supports this fill",
                    }
                ]
            },
            ensure_ascii=False,
        )

    evidence_package = {
        "source_structured": {"records": [{"object_id": "record/project-name", "value": "智慧园区改造"}]},
        "source_page_images": [{"page_index": 0, "image_ref": "/pages/source-1.png"}],
        "template_structured": {"slots": [{"slot_id": "slot-project", "raw_name": "项目名称"}]},
        "template_page_images": [{"page_index": 0, "image_ref": "/pages/template-1.png"}],
    }
    decisions = map_slots_with_agent(evidence_package, decision_client=fake_client)

    assert len(calls) == 1
    assert "source structured content" in calls[0]["system_prompt"]
    assert "source page render images" in calls[0]["system_prompt"]
    assert "template structured content" in calls[0]["system_prompt"]
    assert "template page render images" in calls[0]["system_prompt"]
    assert "Do not concatenate multiple source rows" in calls[0]["system_prompt"]
    assert "source-consistent" in calls[0]["system_prompt"]
    assert "Optimize for evidence-faithful fills" in calls[0]["system_prompt"]
    assert "Different field names are allowed" in calls[0]["system_prompt"]
    assert "related but non-equivalent field" in calls[0]["system_prompt"]
    assert "Preserve source text literally" in calls[0]["system_prompt"]
    assert "Do not correct typos" in calls[0]["system_prompt"]
    assert "Positive examples" in calls[0]["system_prompt"]
    assert "Negative examples" in calls[0]["system_prompt"]
    assert "Do not synthesize a document number" in calls[0]["system_prompt"]
    assert "Do not fill a person-name target from a related but different role" in calls[0]["system_prompt"]
    assert "Do not infer a full date from a quarter, month, or relative deadline" in calls[0]["system_prompt"]
    assert "Do not classify hazards into abstract categories" in calls[0]["system_prompt"]
    assert "Fill a differently named field only when the source label and surrounding text make it the same business concept" in calls[0]["system_prompt"]
    assert "task.source_selection" in calls[0]["system_prompt"]
    assert "preferred_source_refs" in calls[0]["system_prompt"]
    assert "actually delivered or skipped" in calls[0]["system_prompt"]
    assert "template.targets" in calls[0]["system_prompt"]
    assert "single authoritative task list" in calls[0]["system_prompt"]
    assert "return exactly one decision" in calls[0]["system_prompt"]
    assert "visual_target" in calls[0]["system_prompt"]
    assert "visual_text_anchor" in calls[0]["system_prompt"]
    assert "DOCX and XLSX template targets" in calls[0]["system_prompt"]
    assert "PDF template targets are out of scope" in calls[0]["system_prompt"]
    assert "Stage 1" not in calls[0]["system_prompt"]
    assert "Stage 2" not in calls[0]["system_prompt"]
    assert "template.visual_targets" not in calls[0]["system_prompt"]
    assert "visual_scan" in calls[0]["system_prompt"]
    assert "must always include a top-level `visual_scan`" in calls[0]["system_prompt"]
    assert "compact request records" in calls[0]["system_prompt"]
    assert "Use the compact record `ref`" in calls[0]["system_prompt"]
    assert "INPUT_JSON:" in calls[0]["user_prompt"]
    payload = json.loads(calls[0]["user_prompt"].split("INPUT_JSON:", 1)[1])
    sent_package = payload["evidence_package"]
    assert sent_package["source_structured"] == evidence_package["source_structured"]
    assert sent_package["source_page_images"] == evidence_package["source_page_images"]
    assert sent_package["template_structured"] == evidence_package["template_structured"]
    assert sent_package["template_page_images"] == evidence_package["template_page_images"]
    assert "agent_input" in sent_package
    assert "visual_scan" not in sent_package

    assert decisions == [
        AgentDecision(
            slot_id="slot-project",
            decision_type="text_fill",
            value="智慧园区改造",
            asset_ref=None,
            source_refs=["record/project-name"],
            target_ref={"format_key": "docx", "target_kind": "placeholder", "paragraph_index": 2},
            confidence=0.93,
            reason="source structured record directly supports this fill",
        )
    ]


def test_map_slots_with_agent_preserves_visual_scan_summary() -> None:
    evidence_package = {"template": {"structured": {"slots": []}}}

    decisions = map_slots_with_agent(
        evidence_package,
        decision_client=lambda **_: {
            "visual_scan": {
                "performed": True,
                "extra_fillable_areas": [
                    {
                        "label_or_nearby_text": "编号",
                        "status": "unsupported_by_source",
                        "reason": "source has no document number",
                    }
                ],
                "supported_decisions_added": 0,
                "unsupported_area_count": 1,
            },
            "decisions": [],
        },
    )

    assert decisions == []
    assert evidence_package["visual_scan"] == {
        "performed": True,
        "extra_fillable_areas": [
            {
                "label_or_nearby_text": "编号",
                "status": "unsupported_by_source",
                "reason": "source has no document number",
            }
        ],
        "supported_decisions_added": 0,
        "unsupported_area_count": 1,
    }


def test_map_slots_with_agent_accepts_top_level_decision_list() -> None:
    decisions = map_slots_with_agent(
        {"template_structured": {"slots": []}},
        decision_client=lambda **_: [
            {
                "slot_id": "slot-missing",
                "decision": "unresolved",
                "reason_code": "missing_source_evidence",
                "message": "No source evidence.",
            }
        ],
    )

    assert decisions[0].slot_id == "slot-missing"
    assert decisions[0].decision_type == "unresolved"
    assert decisions[0].reason == "No source evidence."


def test_map_slots_with_agent_accepts_fenced_json_response() -> None:
    decisions = map_slots_with_agent(
        {"template": {"structured": {"slots": []}}},
        decision_client=lambda **_: """```json
{"decisions": [{"slot_id": "slot-missing", "decision": "unresolved", "reason": "No source evidence."}]}
```""",
    )

    assert decisions[0].slot_id == "slot-missing"
    assert decisions[0].decision_type == "unresolved"


def test_map_slots_with_agent_sends_existing_page_images_as_user_parts(tmp_path: Path) -> None:
    page_image = tmp_path / "page.png"
    page_image.write_bytes(b"image-bytes")
    calls: list[dict[str, object]] = []

    def fake_client(**kwargs):
        calls.append(kwargs)
        return [
            {
                "slot_id": "slot-missing",
                "decision": "unresolved",
                "reason": "No source evidence.",
            }
        ]

    map_slots_with_agent(
        {
            "source": {"page_images": [{"image_ref": str(page_image)}]},
            "template": {"page_images": [{"image_ref": "/missing/template-page.png"}]},
        },
        decision_client=fake_client,
    )

    user_parts = calls[0]["user_parts"]
    assert user_parts[0]["type"] == "text"
    assert user_parts[1]["type"] == "image_url"
    assert user_parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert len(user_parts) == 2
    assert calls[0]["user_prompt"].find('"client_accepts_user_parts": true') > 0
    assert calls[0]["user_prompt"].find('"delivered_inline_page_image_count": 1') > 0


def test_map_slots_with_agent_sends_all_page_images_by_default(tmp_path: Path) -> None:
    image_paths = []
    for index in range(6):
        path = tmp_path / f"page-{index}.png"
        path.write_bytes(f"image-{index}".encode("ascii"))
        image_paths.append(path)
    calls: list[dict[str, object]] = []

    def fake_client(**kwargs):
        calls.append(kwargs)
        return [
            {
                "slot_id": "slot-missing",
                "decision": "unresolved",
                "reason": "No source evidence.",
            }
        ]

    map_slots_with_agent(
        {
            "source": {
                "page_images": [
                    {"image_ref": str(image_paths[0])},
                    {"image_ref": str(image_paths[1])},
                    {"image_ref": str(image_paths[2])},
                ]
            },
            "template": {
                "page_images": [
                    {"image_ref": str(image_paths[3])},
                    {"image_ref": str(image_paths[4])},
                    {"image_ref": str(image_paths[5])},
                ]
            },
        },
        decision_client=fake_client,
    )

    user_parts = calls[0]["user_parts"]
    encoded_urls = [part["image_url"]["url"] for part in user_parts[1:]]
    payload = json.loads(user_parts[0]["text"].split("INPUT_JSON:", 1)[1])
    agent_input = payload["evidence_package"]["agent_input"]

    assert len(encoded_urls) == 6
    assert "aW1hZ2UtMw==" in encoded_urls[0]
    assert "aW1hZ2UtNA==" in encoded_urls[1]
    assert "aW1hZ2UtNQ==" in encoded_urls[2]
    assert "aW1hZ2UtMA==" in encoded_urls[3]
    assert "aW1hZ2UtMQ==" in encoded_urls[4]
    assert "aW1hZ2UtMg==" in encoded_urls[5]
    assert agent_input["inline_page_image_count"] == 6
    assert agent_input["delivered_inline_page_image_count"] == 6
    assert agent_input["skipped_page_image_count"] == 0
    assert [item["side"] for item in agent_input["sent_page_images"]] == [
        "template",
        "template",
        "template",
        "source",
        "source",
        "source",
    ]


def test_map_slots_with_agent_can_limit_page_images_with_explicit_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(DOCTRANSAI_AGENTIC_MAX_INLINE_PAGE_IMAGES_ENV, "2")
    image_paths = []
    for index in range(4):
        path = tmp_path / f"page-{index}.png"
        path.write_bytes(f"image-{index}".encode("ascii"))
        image_paths.append(path)
    calls: list[dict[str, object]] = []

    def fake_client(**kwargs):
        calls.append(kwargs)
        return [
            {
                "slot_id": "slot-missing",
                "decision": "unresolved",
                "reason": "No source evidence.",
            }
        ]

    map_slots_with_agent(
        {
            "source": {
                "page_images": [
                    {"image_ref": str(image_paths[0])},
                    {"image_ref": str(image_paths[1])},
                ]
            },
            "template": {
                "page_images": [
                    {"image_ref": str(image_paths[2])},
                    {"image_ref": str(image_paths[3])},
                ]
            },
        },
        decision_client=fake_client,
    )

    payload = json.loads(calls[0]["user_parts"][0]["text"].split("INPUT_JSON:", 1)[1])
    agent_input = payload["evidence_package"]["agent_input"]

    assert len(calls[0]["user_parts"]) == 3
    assert agent_input["inline_page_image_count"] == 2
    assert agent_input["skipped_page_image_count"] == 2
    assert {item["reason"] for item in agent_input["skipped_page_images"]} == {"inline_page_image_limit"}


def test_map_slots_with_agent_reports_when_client_cannot_receive_user_parts(tmp_path: Path) -> None:
    page_image = tmp_path / "page.png"
    page_image.write_bytes(b"image-bytes")
    calls: list[dict[str, str]] = []

    def fake_client(*, system_prompt: str, user_prompt: str) -> str:
        calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": "slot-missing",
                        "decision": "unresolved",
                        "reason": "No source evidence.",
                    }
                ]
            }
        )

    map_slots_with_agent(
        {"source": {"page_images": [{"image_ref": str(page_image)}]}},
        decision_client=fake_client,
    )

    payload = json.loads(calls[0]["user_prompt"].split("INPUT_JSON:", 1)[1])
    agent_input = payload["evidence_package"]["agent_input"]

    assert agent_input["client_accepts_user_parts"] is False
    assert agent_input["inline_page_image_count"] == 1
    assert agent_input["delivered_inline_page_image_count"] == 0
    assert agent_input["delivery_warning"] == "agent_visual_input_not_supported_by_client"


def test_map_slots_with_agent_sends_compact_request_package_without_duplicate_table_cells() -> None:
    calls: list[dict[str, object]] = []
    evidence_package = {
        "source": {
            "structured": {
                "records": [
                    {
                        "record_id": "tblrow-1",
                        "document_id": "doc-1",
                        "table_id": "table-1",
                        "locator": {"page_anchor": "page_1", "table_id": "table-1", "row_index": 1},
                        "values": [
                            {
                                "canonical_key": "row_text",
                                "value": "项目名称=机场路项目 | 整改责任人=张三",
                                "provenance": [
                                    {
                                        "source_kind": "table_row",
                                        "object_id": "tblrow-1",
                                        "locator": {
                                            "page_anchor": "page_1",
                                            "table_id": "table-1",
                                            "row_index": 1,
                                        },
                                    }
                                ],
                            },
                            {
                                "canonical_key": "项目名称",
                                "value": "机场路项目",
                                "raw_label": "项目名称",
                                "value_type": "text",
                                "provenance": [
                                    {
                                        "source_kind": "table_cell",
                                        "object_id": "tblcell-1",
                                        "locator": {
                                            "page_anchor": "page_1",
                                            "table_id": "table-1",
                                            "row_index": 1,
                                            "column_index": 1,
                                        },
                                    }
                                ],
                            },
                            {
                                "canonical_key": "整改责任人",
                                "value": "张三",
                                "raw_label": "整改责任人",
                                "value_type": "text",
                                "provenance": [
                                    {
                                        "source_kind": "table_cell",
                                        "object_id": "tblcell-2",
                                        "locator": {
                                            "page_anchor": "page_1",
                                            "table_id": "table-1",
                                            "row_index": 1,
                                            "column_index": 2,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "record_id": "tblcell-1",
                        "document_id": "doc-1",
                        "table_id": "table-1",
                        "locator": {
                            "page_anchor": "page_1",
                            "table_id": "table-1",
                            "row_index": 1,
                            "column_index": 1,
                        },
                        "values": [{"canonical_key": "项目名称", "value": "机场路项目"}],
                    },
                ],
                "image_assets": [{"asset_id": "img-1", "source_ref": "/tmp/photo.png"}],
                "object_index": {
                    "record:tblrow-1": {"object_type": "record"},
                    "record:tblcell-1": {"object_type": "record"},
                    "image_asset:img-1": {"object_type": "image_asset"},
                },
            },
            "page_images": [{"image_ref": "/tmp/source-page.png", "page_index": 0}],
            "page_image_index": {"page:0": {"image_ref": "/tmp/source-page.png"}},
        },
        "template": {
            "structured": {
                "slots": [{"slot_id": "slot-project", "raw_name": "项目名称"}],
                "object_index": {"template_slot:slot-project": {"object_type": "template_slot"}},
            },
            "targets": [{"target_id": "slot-project", "label": "项目名称"}],
            "page_images": [{"image_ref": "/tmp/template-page.png", "page_index": 0}],
            "page_image_index": {"page:0": {"image_ref": "/tmp/template-page.png"}},
        },
    }

    def fake_client(**kwargs):
        calls.append(kwargs)
        return {
            "visual_scan": {"performed": True, "extra_fillable_areas": []},
            "decisions": [
                {
                    "slot_id": "slot-project",
                    "decision": "unresolved",
                    "reason": "No source evidence.",
                }
            ],
        }

    map_slots_with_agent(evidence_package, decision_client=fake_client)

    sent_package = json.loads(calls[0]["user_prompt"].split("INPUT_JSON:", 1)[1])["evidence_package"]
    sent_source = sent_package["source"]
    sent_records = sent_source["structured"]["records"]

    assert "object_index" in evidence_package["source"]["structured"]
    assert "page_image_index" in evidence_package["source"]
    assert any(record["record_id"] == "tblcell-1" for record in evidence_package["source"]["structured"]["records"])
    assert "object_index" not in sent_source["structured"]
    assert "object_index" not in sent_package["template"]["structured"]
    assert "page_image_index" not in sent_source
    assert "page_image_index" not in sent_package["template"]
    assert sent_records == [
        {
            "ref": "record:tblrow-1",
            "loc": "page_anchor=page_1, table_id=table-1, row_index=1",
            "text": "项目名称=机场路项目 | 整改责任人=张三",
        }
    ]
    assert sent_package["agent_input"]["packaging"]["mode"] == "compact_request_package"
    assert sent_package["agent_input"]["packaging"]["removed_duplicate_table_cell_records"] == 1


def test_map_slots_with_agent_does_not_count_multimodal_image_bytes_as_text_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(DOCTRANSAI_AGENTIC_PROVIDER_MAX_INPUT_CHARS_ENV, "12000")
    page_image = tmp_path / "page.png"
    page_image.write_bytes(b"x" * 6000)
    calls: list[dict[str, object]] = []

    def fake_client(**kwargs):
        calls.append(kwargs)
        return [
            {
                "slot_id": "slot-missing",
                "decision": "unresolved",
                "reason": "No source evidence.",
            }
        ]

    map_slots_with_agent(
        {
            "source": {"page_images": [{"image_ref": str(page_image), "page_index": 0}]},
            "template": {"structured": {"slots": [{"slot_id": "slot-missing"}]}},
        },
        decision_client=fake_client,
    )

    payload = json.loads(calls[0]["user_parts"][0]["text"].split("INPUT_JSON:", 1)[1])
    agent_input = payload["evidence_package"]["agent_input"]

    assert len(calls[0]["user_parts"]) == 2
    assert agent_input["inline_page_image_count"] == 1
    assert agent_input["delivered_inline_page_image_count"] == 1
    assert agent_input["skipped_page_image_count"] == 0
    assert agent_input["estimated_input_chars"] <= agent_input["max_input_chars"]
    assert agent_input["preflight_blocked"] is False


def test_agentic_default_provider_input_char_budget_covers_long_document_payload() -> None:
    assert DEFAULT_AGENTIC_PROVIDER_MAX_INPUT_CHARS >= 3_000_000


def test_map_slots_with_agent_blocks_before_client_when_structure_exceeds_provider_budget(
    monkeypatch,
) -> None:
    monkeypatch.setenv(DOCTRANSAI_AGENTIC_PROVIDER_MAX_INPUT_CHARS_ENV, "1000")
    called = {"value": False}

    def fake_client(**kwargs):
        called["value"] = True
        return []

    with pytest.raises(DoctransaiLLMInputTooLargeError) as exc_info:
        map_slots_with_agent(
            {
                "source": {"structured": {"records": [{"text": "x" * 5000}]}},
                "template": {"structured": {"slots": [{"slot_id": "slot-missing"}]}},
            },
            decision_client=fake_client,
        )

    assert called["value"] is False
    assert exc_info.value.estimated_input_chars > exc_info.value.max_input_chars
