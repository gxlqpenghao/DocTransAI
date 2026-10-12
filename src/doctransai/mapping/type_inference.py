from __future__ import annotations

import re

from doctransai.models.source import SourceValue
from doctransai.models.template import TemplateSlot


_PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s]{6,}\d)")
_DATE_RE = re.compile(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}")
_CJK_NAME_RE = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
_ORG_HINT_RE = re.compile(r"(公司|单位|项目部|分公司|集团|工程|建设|管理处)")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_./]{2,}$")
_PERSON_LABEL_HINTS = ("负责人", "责任人", "复查人", "检查人", "人员", "姓名", "联系人", "经办人", "owner", "reviewer", "inspector", "contact")
_ORG_LABEL_HINTS = ("单位", "公司", "部门", "组织", "organization", "org", "company")
_PHONE_LABEL_HINTS = ("手机", "电话", "tel", "mobile", "contact")
_DATETIME_LABEL_HINTS = ("时间", "日期", "期限", "date", "time", "deadline")
_IDENTIFIER_LABEL_HINTS = ("编号", "序号", "id", "code", "ticket", "单号")
_GENERIC_TEXT_KEYS = {"text", "table_text", "range_text", "sheet_summary", "body_text"}


def infer_slot_value_type(slot: TemplateSlot) -> str:
    if slot.slot_kind == "image":
        return "image"
    name = f"{slot.raw_name} {slot.canonical_name}".casefold()
    if any(token in name for token in _PHONE_LABEL_HINTS):
        return "phone"
    if any(token in name for token in _DATETIME_LABEL_HINTS):
        return "datetime"
    if any(token in name for token in _PERSON_LABEL_HINTS):
        return "person"
    if any(token in name for token in _ORG_LABEL_HINTS):
        return "organization"
    if any(token in name for token in _IDENTIFIER_LABEL_HINTS):
        return "identifier"
    return "text"


def infer_source_value_type(value: SourceValue) -> str:
    text = value.value.strip()
    label = f"{value.raw_label or ''} {value.canonical_key}".casefold()
    has_datetime_label = any(token in label for token in _DATETIME_LABEL_HINTS)
    if value.canonical_key in _GENERIC_TEXT_KEYS and len(text) > 50 and not has_datetime_label:
        return "text"
    if _PHONE_RE.fullmatch(text):
        return "phone"
    if _DATE_RE.search(text):
        return "datetime"
    has_org_label = any(token in label for token in _ORG_LABEL_HINTS)
    if _ORG_HINT_RE.search(text) or (has_org_label and not text.isdigit() and not _IDENTIFIER_RE.fullmatch(text)):
        return "organization"
    if _CJK_NAME_RE.fullmatch(text) and any(token in label for token in _PERSON_LABEL_HINTS):
        return "person"
    if any(token in label for token in _IDENTIFIER_LABEL_HINTS) and (_IDENTIFIER_RE.fullmatch(text) or text.isdigit()):
        return "identifier"
    return "text"
