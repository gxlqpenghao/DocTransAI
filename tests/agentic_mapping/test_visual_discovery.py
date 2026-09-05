from __future__ import annotations

from doctransai.agentic_mapping.visual_discovery import discover_template_visual_targets


def test_discover_template_visual_targets_filters_fixed_title_without_fillable_marker() -> None:
    result = discover_template_visual_targets(
        {
            "template": {
                "structured": {"format_key": "xlsx", "slots": []},
                "page_images": [{"image_ref": "/tmp/template-page.png", "page_index": 0}],
            }
        },
        discovery_client=lambda **_: {
            "visual_targets": [
                {
                    "target_id": "visual-target-title",
                    "label_or_nearby_text": "安全检查台账",
                    "expected_content_type": "text",
                    "approx_location": "top-left",
                    "visual_reason": "页面顶部左侧有标题文本'安全检查台账'，为独立文本锚点，无对应结构化slot",
                    "visual_target": {
                        "format_key": "xlsx",
                        "target_kind": "visual_text_anchor",
                        "label_or_nearby_text": "安全检查台账",
                        "page_index": 0,
                    },
                }
            ]
        },
    )

    assert result["target_count"] == 0
    assert result["visual_targets"] == []


def test_discover_template_visual_targets_keeps_anchor_with_explicit_blank() -> None:
    result = discover_template_visual_targets(
        {"template": {"structured": {"format_key": "docx", "slots": []}, "page_images": []}},
        discovery_client=lambda **_: {
            "visual_targets": [
                {
                    "target_id": "visual-target-number",
                    "label_or_nearby_text": "编号",
                    "expected_content_type": "number",
                    "approx_location": "top-right",
                    "visual_reason": "编号后方有明显空白，需要填写编号",
                    "visual_target": {
                        "format_key": "docx",
                        "target_kind": "visual_text_anchor",
                        "label_or_nearby_text": "编号",
                        "page_index": 0,
                    },
                }
            ]
        },
    )

    assert result["target_count"] == 1
    assert result["visual_targets"][0]["target_id"] == "visual-target-number"
