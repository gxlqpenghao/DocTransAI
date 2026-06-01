from __future__ import annotations

from doctransai.mapping.type_inference import infer_slot_value_type, infer_source_value_type
from doctransai.models.source import SourceValue
from doctransai.models.template import SlotAddress, TemplateSlot


def test_infer_slot_value_type_uses_generic_shape_hints() -> None:
    assert infer_slot_value_type(
        TemplateSlot(
            slot_id="slot-phone",
            raw_name="手机号",
            canonical_name="手机号",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        )
    ) == "phone"
    assert infer_slot_value_type(
        TemplateSlot(
            slot_id="slot-date",
            raw_name="检查时间",
            canonical_name="检查时间",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        )
    ) == "datetime"
    assert infer_slot_value_type(
        TemplateSlot(
            slot_id="slot-photo",
            raw_name="现场照片",
            canonical_name="现场照片",
            slot_kind="image",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        )
    ) == "image"
    assert infer_slot_value_type(
        TemplateSlot(
            slot_id="slot-owner",
            raw_name="责任单位负责人",
            canonical_name="责任单位负责人",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        )
    ) == "person"
    assert infer_slot_value_type(
        TemplateSlot(
            slot_id="slot-org",
            raw_name="责任单位",
            canonical_name="责任单位",
            slot_kind="text",
            address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
        )
    ) == "organization"


def test_infer_source_value_type_detects_generic_value_shapes() -> None:
    assert infer_source_value_type(SourceValue(canonical_key="联系电话", value="13800138000")) == "phone"
    assert infer_source_value_type(SourceValue(canonical_key="检查时间", value="2026-05-14 18:46")) == "datetime"
    assert infer_source_value_type(SourceValue(canonical_key="项目名称", value="西香TJ3标")) == "text"
    assert infer_source_value_type(SourceValue(canonical_key="责任单位", value="云南道桥建筑工程有限公司")) == "organization"
    assert infer_source_value_type(SourceValue(canonical_key="整改责任人", value="杨恩赐")) == "person"
