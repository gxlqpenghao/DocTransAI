from __future__ import annotations

from doctransai.agentic_mapping.decision_repair import repair_duplicate_decisions
from doctransai.agentic_mapping.decisions import AgentDecision


def test_repair_duplicate_decisions_collapses_equivalent_fill_decisions() -> None:
    decisions, diagnostics = repair_duplicate_decisions(
        [
            AgentDecision(
                slot_id="target-project",
                decision_type="text_fill",
                value="西香TJ3标",
                source_refs=["record:project"],
                target_ref="template_slot:target-project",
                reason="first",
            ),
            AgentDecision(
                slot_id="target-project",
                decision_type="text_fill",
                value="西香TJ3标",
                source_refs=["record:project"],
                target_ref="template_slot:target-project",
                reason="duplicate",
            ),
        ]
    )

    assert [decision.slot_id for decision in decisions] == ["target-project"]
    assert decisions[0].decision_type == "text_fill"
    assert decisions[0].value == "西香TJ3标"
    assert diagnostics == [
        {
            "severity": "warning",
            "code": "duplicate_decisions_collapsed",
            "message": "Collapsed equivalent duplicate decisions for one template target.",
            "slot_id": "target-project",
            "decision_count": 2,
        }
    ]


def test_repair_duplicate_decisions_replaces_conflicting_fills_with_unresolved() -> None:
    decisions, diagnostics = repair_duplicate_decisions(
        [
            AgentDecision(
                slot_id="target-date",
                decision_type="text_fill",
                value="3",
                source_refs=["record:notice"],
                reason="payment day count",
            ),
            AgentDecision(
                slot_id="target-date",
                decision_type="text_fill",
                value="2022年3月27日",
                source_refs=["record:notice"],
                reason="document date",
            ),
        ]
    )

    assert decisions == [
        AgentDecision(
            slot_id="target-date",
            decision_type="unresolved",
            source_refs=["record:notice"],
            reason="Agent returned conflicting fill decisions for this template target.",
            reason_code="duplicate_conflicting_decisions",
        )
    ]
    assert diagnostics == [
        {
            "severity": "warning",
            "code": "duplicate_conflicting_decisions",
            "message": "Agent returned conflicting fill decisions for one template target; converted the target to unresolved.",
            "slot_id": "target-date",
            "decision_count": 2,
        }
    ]


def test_repair_duplicate_decisions_converts_empty_text_fill_to_unresolved() -> None:
    decisions, diagnostics = repair_duplicate_decisions(
        [
            AgentDecision(
                slot_id="target-review-time",
                decision_type="text_fill",
                value="",
                source_refs=["record:row-1"],
                reason="Source record has no value for 复查时间.",
            )
        ]
    )

    assert decisions == [
        AgentDecision(
            slot_id="target-review-time",
            decision_type="unresolved",
            source_refs=["record:row-1"],
            reason="Source record has no value for 复查时间.",
            reason_code="empty_text_fill",
        )
    ]
    assert diagnostics == [
        {
            "severity": "warning",
            "code": "empty_text_fill_converted_to_unresolved",
            "message": "Agent returned an empty text_fill; converted the target to unresolved.",
            "slot_id": "target-review-time",
        }
    ]
