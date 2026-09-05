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
                    "image_asset:img-1": {
                        "object_kind": "image_asset",
                        "asset_id": "img-1",
                        "source_ref": "final_images/image1.jpeg",
                        "asset_path": "/tmp/final_images/image1.jpeg",
                    },
                    "image_asset:img-2": {
                        "object_kind": "image_asset",
                        "asset_id": "img-2",
                        "source_ref": "final_images/image2.jpeg",
                    },
                },
                "records": [
                    {
                        "record_id": "record-1",
                        "values": [
                            {
                                "value": "桥梁检测项目",
                                "provenance": [
                                    {
                                        "locator": {
                                            "column_index": 1,
                                        }
                                    }
                                ],
                            },
                        ],
                    }
                ],
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


def test_validate_agent_decisions_resolves_source_index_alias_refs() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["evidence:record-1"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["object_index"]["evidence:record-1"] = {
        "object_type": "record_alias",
        "ref": "record:record-1",
    }

    result = validate_agent_decisions([decision], package)

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


def test_validate_agent_decisions_rejects_duplicate_slot_decisions() -> None:
    first = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["source_value:record-1:0"],
        target_ref="template_slot:slot-project",
    )
    second = AgentDecision(
        slot_id="slot-project",
        decision_type="unresolved",
        reason="No source evidence.",
    )

    result = validate_agent_decisions([first, second], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [first, second]
    assert [diagnostic["code"] for diagnostic in result.diagnostics].count("duplicate_slot_decision") == 2


def test_validate_agent_decisions_rejects_empty_text_fill() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="",
        source_refs=["source_value:record-1:0"],
        target_ref="template_slot:slot-project",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"missing_text_value"}


def test_validate_agent_decisions_rejects_text_value_not_supported_by_source_ref() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="不存在的项目",
        source_refs=["source_value:record-1:0"],
        target_ref="template_slot:slot-project",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"text_value_not_supported_by_source_ref"}


def test_validate_agent_decisions_rejects_text_fill_when_reason_says_source_does_not_support_it() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["source_value:record-1:0"],
        target_ref="template_slot:slot-project",
        reason="The source does not contain this field; it is not equivalent.",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"decision_reason_contradicts_fill"}


def test_validate_agent_decisions_does_not_treat_template_limitation_as_source_contradiction() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["source_value:record-1:0"],
        target_ref="template_slot:slot-project",
        reason="The template does not support multiple rows, so this value is selected for the single form.",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_rejects_label_only_text_value() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="记录人：",
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"].append({"value": "记录人："})

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"label_only_text_value"}


def test_validate_agent_decisions_accepts_missing_target_ref_when_slot_id_is_known() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["source_value:record-1:0"],
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_accepts_raw_slot_id_as_target_ref() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["source_value:record-1:0"],
        target_ref="slot-project",
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_accepts_visual_text_anchor_target_for_new_visual_slot() -> None:
    decision = AgentDecision(
        slot_id="visual-target-编号",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["source_value:record-1:0"],
        target_ref={
            "format_key": "docx",
            "target_kind": "visual_text_anchor",
            "label_or_nearby_text": "编号",
            "page_index": 0,
        },
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_accepts_visual_target_object_ref_from_template_targets() -> None:
    decision = AgentDecision(
        slot_id="visual-target-检查部门",
        decision_type="text_fill",
        value="安全管理部",
        source_refs=["record:record-1"],
        target_ref={"object_ref": "visual-target-检查部门"},
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"][0]["value"] = "安全管理部组织检查。"
    package["template"]["targets"] = [
        {
            "target_id": "visual-target-检查部门",
            "origin": "visual",
            "label": "检查部门",
            "expected_content_type": "text",
            "target_kind": "visual_text_anchor",
            "target_ref": {
                "format_key": "docx",
                "target_kind": "visual_text_anchor",
                "label_or_nearby_text": "检查部门",
            },
        }
    ]

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_accepts_text_from_record_locator() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"][0]["value"] = "项目概况"
    package["source"]["structured"]["records"][0]["locator"] = {
        "section_title": "桥梁检测项目",
    }

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_accepts_spreadsheet_column_source_value_ref() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="桥梁检测项目",
        source_refs=["source_value:record-1:4"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"] = [
        {
            "value": "其他值",
            "provenance": [{"locator": {"column_index": 1}}],
        },
        {
            "value": "桥梁检测项目",
            "provenance": [{"locator": {"column_index": 5}}],
        },
    ]

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_accepts_one_based_spreadsheet_locator_column_ref() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="2026-05-14 18:46",
        source_refs=["source_value:record-1:14"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"] = [
        {
            "value": "王群策",
            "provenance": [{"locator": {"column_index": 17}}],
        },
        {
            "value": "2026-05-14 18:46",
            "provenance": [{"locator": {"column_index": 14}}],
        },
    ]

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_accepts_year_month_separator_format_difference() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="2021-10",
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"][0]["value"] = (
        "应用起始时间为2021年10月，项目应用持续推进。"
    )

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_accepts_list_marker_format_difference() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="乙炔瓶气带破损；劳务队驻地未设置吸烟区",
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"][0]["value"] = (
        "（1）乙炔瓶气带破损；\n（2）劳务队驻地未设置吸烟区；"
    )

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_accepts_composed_list_text_from_same_record() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="乙炔瓶气带破损；劳务队驻地未设置吸烟区",
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"][0]["value"] = (
        "检查发现的问题包括：一是乙炔瓶气带破损，需要立即更换；"
        "二是现场材料堆放杂乱；三是劳务队驻地未设置吸烟区，应补充标识。"
    )

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_accepts_composed_list_text_with_one_character_extraction_gap() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="更换破损气带；宿舍区禁止使用热得快；应按规范要求使用绝缘胶带绑扎",
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"][0]["value"] = (
        "整改要求：（一）更换破损气带；"
        "（二）宿舍区禁止使用得快；"
        "（三）应按规范要求使用绝缘胶带绑扎。"
    )

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_rejects_composed_category_labels_not_in_source() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="设备安全、消防安全、用电安全",
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"][0]["value"] = (
        "检查发现乙炔瓶气带破损、劳务队驻地未设置吸烟区、配电箱无巡查记录。"
    )

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"text_value_not_supported_by_source_ref"}


def test_validate_agent_decisions_accepts_long_generated_text_covered_by_cited_sources() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value=(
            "面向交通强国需求，项目通过AI模型实现地质信息精准感知，"
            "并结合风险量化评估与智能决策形成系统性成果。"
        ),
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
        reason="成果简介需要从 cited source 内容中压缩形成。",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"][0]["value"] = (
        "面向“交通强国”等重大战略需求，本项目以“AI-数理双驱动”为核心，"
        "实现地质信息精准感知、风险量化评估与智能决策，最终形成系统性成果。"
    )

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []


def test_validate_agent_decisions_keeps_short_synthetic_values_strict() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="2021年10月~至今",
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
        reason="Combines earliest start and current status.",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"][0]["value"] = (
        "项目A应用时间为2021年10月~2023年3月，项目B应用时间为2022年1月~至今。"
    )

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"text_value_not_supported_by_source_ref"}


def test_validate_agent_decisions_rejects_long_generated_text_with_unsupported_claims() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value=(
            "项目采用区块链存证、无人机巡检、数字孪生驾驶舱和自动化机器人施工，"
            "实现全过程智能监管与碳排放实时交易。"
        ),
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"][0]["values"][0]["value"] = (
        "本项目开展桥梁检测数据整理，形成检查记录和整改闭环。"
    )

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"text_value_not_supported_by_source_ref"}


def test_validate_agent_decisions_repairs_source_refs_when_value_exists_elsewhere_in_source() -> None:
    decision = AgentDecision(
        slot_id="slot-project",
        decision_type="text_fill",
        value="柳州市柳东新区官塘片曙光大道工程（雒容段）",
        source_refs=["record:record-1"],
        target_ref="template_slot:slot-project",
    )
    package = _evidence_package()
    package["source"]["structured"]["records"] = [
        {
            "record_id": "record-1",
            "values": [{"value": "关于11月份冬季施工专项检查情况的通报"}],
        },
        {
            "record_id": "record-2",
            "values": [{"value": "柳州市柳东新区官塘片曙光大道工程（雒容段）项目经理部"}],
        },
    ]
    package["source"]["structured"]["object_index"]["record:record-2"] = {
        "object_kind": "record",
        "record_id": "record-2",
    }

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []
    assert result.diagnostics == []
    assert decision.source_refs == ["record:record-1", "record:record-2"]


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
        source_ref="final_images/image1.jpeg",
        source_refs=["image_asset:img-1"],
        target_ref={"object_ref": "template_slot:slot-photo"},
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []


def test_validate_agent_decisions_accepts_image_asset_path_from_full_asset_record() -> None:
    decision = AgentDecision(
        slot_id="slot-photo",
        decision_type="image_placement",
        asset_ref="img-1",
        source_ref="/tmp/final_images/image1.jpeg",
        source_refs=["image_asset:img-1"],
        target_ref={"object_ref": "template_slot:slot-photo"},
    )
    package = _evidence_package()
    package["source"]["structured"]["object_index"]["image_asset:img-1"].pop("asset_path")
    package["source"]["structured"]["image_assets"] = [
        {
            "asset_id": "img-1",
            "source_ref": "final_images/image1.jpeg",
            "asset_path": "/tmp/final_images/image1.jpeg",
        }
    ]

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []


def test_validate_agent_decisions_accepts_image_source_ref_alias() -> None:
    decision = AgentDecision(
        slot_id="slot-photo",
        decision_type="image_placement",
        asset_ref="img-1",
        source_ref="final_images/image1.jpeg",
        source_refs=["record:record-1", "images/img-1"],
        target_ref={"object_ref": "template_slot:slot-photo"},
    )
    package = _evidence_package()
    package["source"]["structured"]["object_index"]["images/img-1"] = {
        "object_type": "image_asset_alias",
        "ref": "image_asset:img-1",
    }

    result = validate_agent_decisions([decision], package)

    assert result.accepted_decisions == [decision]
    assert result.rejected_decisions == []


def test_validate_agent_decisions_rejects_image_asset_source_ref_mismatch() -> None:
    decision = AgentDecision(
        slot_id="slot-photo",
        decision_type="image_placement",
        asset_ref="img-2",
        source_ref="final_images/image2.jpeg",
        source_refs=["image_asset:img-1"],
        target_ref={"object_ref": "template_slot:slot-photo"},
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"image_asset_source_ref_mismatch"}


def test_validate_agent_decisions_rejects_image_file_source_ref_mismatch() -> None:
    decision = AgentDecision(
        slot_id="slot-photo",
        decision_type="image_placement",
        asset_ref="img-1",
        source_ref="final_images/wrong.jpeg",
        source_refs=["image_asset:img-1"],
        target_ref={"object_ref": "template_slot:slot-photo"},
    )

    result = validate_agent_decisions([decision], _evidence_package())

    assert result.accepted_decisions == []
    assert result.rejected_decisions == [decision]
    assert {diagnostic["code"] for diagnostic in result.diagnostics} == {"image_source_ref_mismatch"}


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
