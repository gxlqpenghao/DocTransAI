from __future__ import annotations

from doctransai.mapping.review_policy import select_review_text_fills
from doctransai.models.render_plan import OutputRef, RenderPlan, TargetRef, TemplateRef, TextFill


def test_select_review_text_fills_keeps_stable_exact_fills_out_of_agent_batch() -> None:
    target = TargetRef(format_key="docx", target_kind="paragraph", paragraph_index=0)
    plan = RenderPlan(
        plan_id="plan-1",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/template.docx", format_key="docx"),
        output=OutputRef(output_path="/out.docx", output_format="docx"),
        text_fills=[
            TextFill(slot_id="slot-exact", target=target, value="A", confidence=0.99, transform="项目名称->项目名称"),
            TextFill(slot_id="slot-overlap", target=target, value="A2", confidence=0.9, transform="联系电话->手机号"),
            TextFill(slot_id="slot-risk", target=target, value="B", confidence=0.78, transform="phone_typed_row_match"),
            TextFill(slot_id="slot-repeat@0", target=target, value="C", confidence=0.72, transform="repeat_region_nearby"),
            TextFill(slot_id="slot-agent", target=target, value="D", confidence=0.91, transform="agent_generated_value"),
        ],
    )

    assert [fill.slot_id for fill in select_review_text_fills(plan)] == ["slot-overlap", "slot-risk"]
