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
            },
        ]
    )

    assert decisions[0].target_ref == {"object_ref": "template_slot:slot-photo"}
    assert decisions[1].source_refs == []
    assert decisions[1].confidence == 1.0


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
