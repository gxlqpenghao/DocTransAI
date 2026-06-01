from __future__ import annotations

from doctransai.agentic_mapping.decisions import AgentDecision
from doctransai.agentic_mapping.validator import ValidationResult, validate_agent_decisions


def _evidence_package() -> dict:
    return {
        "source": {
            "structured": {
                "object_index": {
                    "record:record-1": {"object_kind": "record", "record_id": "record-1"},
                    "source_value:record-1:0": {
                        "object_kind": "source_value",
                        "record_id": "record-1",
                        "value_index": 0,
                    },
                    "image_asset:img-1": {"object_kind": "image_asset", "asset_id": "img-1"},
                }
            }
        },
        "template": {
            "structured": {
                "object_index": {
                    "template_slot:slot-project": {
                        "object_kind": "template_slot",
                        "slot_id": "slot-project",
                    },
                    "template_slot:slot-photo": {
                        "object_kind": "template_slot",
                        "slot_id": "slot-photo",
                    },
                    "target:summary-table:project": {
                        "object_kind": "target_ref",
                        "target_id": "summary-table:project",
                    },
                }
            }
        },
    }


def test_validate_agent_decisions_accepts_text_fill_with_existing_refs() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["source_value:record-1:0"],
        target_ref="template_slot:slot-project",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert isinstance(result, ValidationResult)
    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_rejects_fill_without_source_refs() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        target_ref="template_slot:slot-project",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert result.diagnostics[0]["code"] == "missing_source_refs"
    assert result.diagnostics[0]["slot_id"] == "slot-project"


def test_validate_agent_decisions_rejects_unknown_source_ref() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["source_value:record-missing:0"],
        target_ref="template_slot:slot-project",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"source_ref_not_found"}


def test_validate_agent_decisions_accepts_image_placement_with_existing_asset() -> None:
    decision = AgentDecision(
        slot_id="slot-photo",
        decision_type="image_placement",
        asset_ref="img-1",
        source_refs=["image_asset:img-1"],
        target_ref={"object_ref": "template_slot:slot-photo"},
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []


def test_validate_agent_decisions_rejects_image_placement_with_missing_asset() -> None:
    decision = AgentDecision(
        slot_id="slot-photo",
        decision_type="image_placement",
        asset_ref="img-missing",
        source_refs=["image_asset:img-1"],
        target_ref="template_slot:slot-photo",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"image_asset_not_found"}


def test_validate_agent_decisions_rejects_unknown_target_ref() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-missing",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"target_ref_not_found"}


def test_validate_agent_decisions_accepts_unresolved_with_reason() -> None:
    decision = AgentDecision(
        slot_id="slot-missing",
        decision_type="unresolved",
        reason="No source evidence exists.",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_rejects_unresolved_without_reason() -> None:
    decision = AgentDecision(slot_id="slot-missing", decision_type="unresolved")

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert result.diagnostics[0]["code"] == "missing_reason"
