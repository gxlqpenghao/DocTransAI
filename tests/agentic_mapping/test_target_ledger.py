from __future__ import annotations

from doctransai.agentic_mapping.decisions import AgentDecision
from doctransai.agentic_mapping.target_ledger import build_target_ledger
from doctransai.agentic_mapping.validator import ValidationResult
from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import OutputRef, RenderPlan, TemplateRef
from doctransai.renderers.models import RenderResult


def test_target_ledger_marks_conditional_unresolved_as_not_applicable() -> None:
    decision = AgentDecision(
        slot_id="visual-target-other-category",
        decision_type="unresolved",
        reason=(
            "Source evidence supports '智能建造' as the selected field value, not '其他'. "
            "The detail blank for '其他' is only relevant when '其他' is selected as the domain."
        ),
    )
    render_plan = RenderPlan(
        plan_id="plan-1",
        source_bundle_path="/tmp/source.json",
        template=TemplateRef(template_path="/tmp/template.docx", format_key="docx"),
        output=OutputRef(output_path="/tmp/output.docx", output_format="docx"),
        unresolved_slots=[
            UnresolvedSlot(
                slot_id="visual-target-other-category",
                canonical_key="其他（注明）",
                reason_code="agent_unresolved",
                message=decision.reason or "",
            )
        ],
    )

    ledger = build_target_ledger(
        evidence_package={
            "template": {
                "targets": [
                    {
                        "target_id": "visual-target-other-category",
                        "origin": "visual",
                        "label": "其他（注明：__________）",
                        "expected_content_type": "text",
                    }
                ]
            }
        },
        decisions=[decision],
        validation_result=ValidationResult(accepted_decisions=[decision]),
        render_plan=render_plan,
        render_result=RenderResult(output_path="/tmp/output.docx"),
    )

    assert ledger[0]["decision_type"] == "not_applicable"
    assert ledger[0]["decision_status"] == "accepted"
    assert ledger[0]["render_status"] == "not_applicable"
