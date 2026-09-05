from __future__ import annotations

from doctransai.agentic_mapping.template_targets import build_template_targets


def test_build_template_targets_wraps_structured_slots() -> None:
    targets = build_template_targets(
        {
            "format_key": "docx",
            "slots": [
                {
                    "slot_id": "slot-project",
                    "raw_name": "项目名称",
                    "canonical_name": "project_name",
                    "slot_kind": "text",
                    "repeat_region_id": "region-1",
                    "placement_constraints": {"multi_value_allowed": True},
                    "address": {"format_key": "docx", "address_kind": "placeholder", "paragraph_index": 2},
                }
            ],
        }
    )

    assert targets == [
        {
            "target_id": "slot-project",
            "origin": "structured",
            "label": "项目名称",
            "canonical_name": "project_name",
            "expected_content_type": "text",
            "target_kind": "structured_slot",
            "repeat_region_id": "region-1",
            "placement_constraints": {"multi_value_allowed": True},
            "target_ref": {"object_ref": "template_slot:slot-project"},
            "address": {"format_key": "docx", "address_kind": "placeholder", "paragraph_index": 2},
        }
    ]


def test_build_template_targets_merges_visual_targets_and_deduplicates_covered_slots() -> None:
    targets = build_template_targets(
        {
            "format_key": "docx",
            "slots": [
                {
                    "slot_id": "slot-phone",
                    "raw_name": "手机号",
                    "canonical_name": "phone",
                    "slot_kind": "text",
                    "address": {"format_key": "docx", "address_kind": "table_cell"},
                }
            ],
        },
        visual_targets=[
            {
                "target_id": "visual-target-phone",
                "label_or_nearby_text": "主办人员电话：{手机号}",
                "expected_content_type": "phone",
                "visual_target": {
                    "format_key": "docx",
                    "target_kind": "visual_text_anchor",
                    "label_or_nearby_text": "主办人员电话：{手机号}",
                },
            },
            {
                "target_id": "visual-target-编号",
                "label_or_nearby_text": "编号",
                "expected_content_type": "number",
                "visual_target": {
                    "format_key": "docx",
                    "target_kind": "visual_text_anchor",
                    "label_or_nearby_text": "编号",
                },
            },
        ],
    )

    assert [target["target_id"] for target in targets] == ["slot-phone", "visual-target-编号"]
    assert targets[1] == {
        "target_id": "visual-target-编号",
        "origin": "visual",
        "label": "编号",
        "expected_content_type": "number",
        "target_kind": "visual_text_anchor",
        "target_ref": {
            "format_key": "docx",
            "target_kind": "visual_text_anchor",
            "label_or_nearby_text": "编号",
        },
    }


def test_build_template_targets_deduplicates_visual_target_with_x_marker_structured_label() -> None:
    targets = build_template_targets(
        {
            "format_key": "docx",
            "slots": [
                {
                    "slot_id": "slot-management-date",
                    "raw_name": "X项目安全管理部于X",
                    "canonical_name": "x项目安全管理部于x",
                    "slot_kind": "text",
                    "address": {"format_key": "docx", "address_kind": "implicit_blank"},
                }
            ],
        },
        visual_targets=[
            {
                "target_id": "visual-target-management-date",
                "label_or_nearby_text": "项目安全管理部",
                "expected_content_type": "text",
                "visual_target": {
                    "format_key": "docx",
                    "target_kind": "visual_text_anchor",
                    "label_or_nearby_text": "项目安全管理部",
                },
            },
        ],
    )

    assert [target["target_id"] for target in targets] == ["slot-management-date"]
