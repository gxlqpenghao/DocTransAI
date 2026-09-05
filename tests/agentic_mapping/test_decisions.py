from __future__ import annotations

import pytest

from doctransai.agentic_mapping.decisions import AgentDecision, parse_agent_decisions


def test_parse_agent_decisions_accepts_wrapper_payload() -> None:
    decisions = parse_agent_decisions(
        {
            "decisions": [
                {
                    "slot_id": "slot-project",
                    "decision_type": "text_fill",
                    "value": "桥梁检测项目",
                    "source_refs": ["source_value:record-1:0"],
                    "target_ref": "template_slot:slot-project",
                    "confidence": 0.82,
                    "reason": "Source value directly matches the template slot.",
                }
            ]
        }
    )

    assert decisions == [
        AgentDecision(
            slot_id="slot-project",
            decision_type="text_fill",
            value="桥梁检测项目",
            source_refs=["source_value:record-1:0"],
            target_ref="template_slot:slot-project",
            confidence=0.82,
            reason="Source value directly matches the template slot.",
        )
    ]


def test_parse_agent_decisions_accepts_list_payload_and_target_ref_dict() -> None:
    decisions = parse_agent_decisions(
        [
            {
                "slot_id": "slot-photo",
                "decision_type": "image_placement",
                "asset_ref": "img-1",
                "source_refs": ["image_asset:img-1"],
                "target_ref": {"object_ref": "template_slot:slot-photo"},
            },
            {
                "slot_id": "slot-missing",
                "decision_type": "unresolved",
                "reason": "No source evidence exists.",
                "reason_code": "missing_source_evidence",
                "candidate_ids": ["candidate-1"],
            },
        ]
    )

    assert decisions[0].target_ref == {"object_ref": "template_slot:slot-photo"}
    assert decisions[1].source_refs == []
    assert decisions[1].confidence == 1.0
    assert decisions[1].reason_code == "missing_source_evidence"
    assert decisions[1].candidate_ids == ["candidate-1"]


def test_parse_agent_decisions_keeps_image_source_ref_separate_from_evidence_refs() -> None:
    decisions = parse_agent_decisions(
        [
            {
                "slot_id": "slot-photo",
                "decision_type": "image_placement",
                "asset_id": "img-1",
                "source_ref": "final_images/image1.jpeg",
                "source_refs": ["image_asset:img-1"],
                "target_ref": "template_slot:slot-photo",
            }
        ]
    )

    assert decisions[0].asset_ref == "img-1"
    assert decisions[0].source_ref == "final_images/image1.jpeg"
    assert decisions[0].source_refs == ["image_asset:img-1"]


def test_parse_agent_decisions_preserves_render_intent_fields() -> None:
    decisions = parse_agent_decisions(
        [
            {
                "slot_id": "slot-project",
                "decision": "text_fill",
                "value": "2026-05-14",
                "value_type": "date",
                "transform": "date_only",
                "source_refs": ["source_value:record-1:0"],
                "target_ref": "template_slot:slot-project",
            },
            {
                "slot_id": "slot-photo",
                "decision": "image_placement",
                "asset_id": "img-1",
                "source_ref": "final_images/image1.jpeg",
                "source_refs": ["image_asset:img-1"],
                "target_ref": "template_slot:slot-photo",
                "sizing_policy": "cover",
                "caption": "现场照片",
                "caption_slot_id": "slot-caption",
                "caption_target": {
                    "format_key": "docx",
                    "target_kind": "placeholder",
                    "paragraph_index": 3,
                },
            },
        ]
    )

    assert decisions[0].value_type == "date"
    assert decisions[0].transform == "date_only"
    assert decisions[1].sizing_policy == "cover"
    assert decisions[1].caption == "现场照片"
    assert decisions[1].caption_slot_id == "slot-caption"
    assert decisions[1].caption_target == {
        "format_key": "docx",
        "target_kind": "placeholder",
        "paragraph_index": 3,
    }


def test_parse_agent_decisions_accepts_list_value_for_repeatable_text() -> None:
    decisions = parse_agent_decisions(
        [
            {
                "slot_id": "slot-desc",
                "decision": "text_fill",
                "value": ["二工区围挡未及时封闭", "有村民进入施工现场"],
                "source_refs": ["record:ev-1"],
                "target_ref": "template_slot:slot-desc",
            }
        ]
    )

    assert decisions[0].value == "二工区围挡未及时封闭\n有村民进入施工现场"


def test_parse_agent_decisions_accepts_visual_target_alias() -> None:
    decisions = parse_agent_decisions(
        {
            "decisions": [
                {
                    "slot_id": "visual-target-编号",
                    "decision": "text_fill",
                    "value": "LQ-2026-001",
                    "source_refs": ["record:notice"],
                    "visual_target": {
                        "format_key": "docx",
                        "target_kind": "visual_text_anchor",
                        "label_or_nearby_text": "编号",
                        "page_index": 0,
                    },
                    "reason": "The template page shows a visible blank after 编号.",
                }
            ]
        }
    )

    assert decisions[0].target_ref == {
        "format_key": "docx",
        "target_kind": "visual_text_anchor",
        "label_or_nearby_text": "编号",
        "page_index": 0,
    }


def test_parse_agent_decisions_accepts_common_textual_confidence_labels() -> None:
    decisions = parse_agent_decisions(
        [
            {
                "slot_id": "visual-target-编号",
                "decision": "text_fill",
                "value": "LQ-2026-001",
                "source_refs": ["source_value:notice-record:0"],
                "target_ref": "template_slot:slot-id",
                "confidence": "high",
            }
        ]
    )

    assert decisions[0].confidence == 0.9


def test_parse_agent_decisions_recovers_visual_target_from_visual_slot_id() -> None:
    decisions = parse_agent_decisions(
        [
            {
                "slot_id": "visual-target-编号",
                "decision": "text_fill",
                "value": "LQ-2026-001",
                "source_refs": ["source_value:notice-record:0"],
                "target_ref": None,
                "confidence": 0.95,
            }
        ]
    )

    assert decisions[0].target_ref == {
        "format_key": "docx",
        "target_kind": "visual_text_anchor",
        "label_or_nearby_text": "编号",
    }


def test_parse_agent_decisions_keeps_legacy_text_source_ref_as_evidence_ref() -> None:
    decisions = parse_agent_decisions(
        [
            {
                "slot_id": "slot-project",
                "decision_type": "text_fill",
                "value": "桥梁检测项目",
                "source_ref": "source_value:record-1:0",
                "target_ref": "template_slot:slot-project",
            }
        ]
    )

    assert decisions[0].source_ref == "source_value:record-1:0"
    assert decisions[0].source_refs == ["source_value:record-1:0"]


def test_parse_agent_decisions_normalizes_structured_source_refs() -> None:
    decisions = parse_agent_decisions(
        [
            {
                "slot_id": "slot-project",
                "decision": "text_fill",
                "value": "桥梁检测项目",
                "source_refs": [
                    {"object_ref": "source_value:record-1:0"},
                    {"object_type": "record", "object_id": "record-1"},
                    {"asset_id": "asset-1"},
                ],
                "target_ref": "template_slot:slot-project",
            }
        ]
    )

    assert decisions[0].source_refs == [
        "source_value:record-1:0",
        "record:record-1",
        "image_asset:asset-1",
    ]


def test_parse_agent_decisions_keeps_unrecognized_source_ref_for_validation() -> None:
    decisions = parse_agent_decisions(
        [
            {
                "slot_id": "slot-project",
                "decision": "text_fill",
                "value": "桥梁检测项目",
                "source_refs": [{"label": "项目名称"}],
                "target_ref": "template_slot:slot-project",
            }
        ]
    )

    assert decisions[0].source_refs == ['unresolved_source_ref:{"label": "项目名称"}']


def test_parse_agent_decisions_rejects_unknown_decision_type() -> None:
    with pytest.raises(ValueError, match="decision_type"):
        parse_agent_decisions(
            [
                {
                    "slot_id": "slot-project",
                    "decision_type": "maybe_fill",
                    "value": "桥梁检测项目",
                }
            ]
        )


def test_agent_decision_source_refs_are_not_shared() -> None:
    first = AgentDecision(slot_id="slot-a", decision_type="unresolved", reason="Missing.")
    second = AgentDecision(slot_id="slot-b", decision_type="unresolved", reason="Missing.")

    first.source_refs.append("record:record-1")

    assert second.source_refs == []
