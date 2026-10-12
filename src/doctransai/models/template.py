from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SlotAddress:
    format_key: str
    address_kind: str
    paragraph_index: int | None = None
    cell_paragraph_index: int | None = None
    run_index: int | None = None
    run_end_index: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    column_index: int | None = None
    sheet_name: str | None = None
    cell_ref: str | None = None
    page_index: int | None = None
    form_field_name: str | None = None
    bbox: list[float] | None = None


@dataclass(slots=True)
class TemplateSlot:
    slot_id: str
    raw_name: str
    canonical_name: str
    slot_kind: str
    address: SlotAddress
    required: bool = True
    mode: str = "placeholder"
    context_before: str | None = None
    context_after: str | None = None
    repeat_region_id: str | None = None
    style_ref: str | None = None
    placement_constraints: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RepeatRegion:
    region_id: str
    format_key: str
    region_kind: str
    address: SlotAddress


@dataclass(slots=True)
class HeaderDrivenRegion:
    region_id: str
    format_key: str
    sheet_name: str
    header_row_index: int
    column_names: list[str] = field(default_factory=list)
    sample_row_index: int | None = None


@dataclass(slots=True)
class TemplateDiagnostic:
    severity: str
    code: str
    message: str
    field: str | None = None


@dataclass(slots=True)
class TemplateModel:
    template_id: str
    template_path: str
    format_key: str
    analyzer_key: str
    slots: list[TemplateSlot] = field(default_factory=list)
    repeat_regions: list[RepeatRegion] = field(default_factory=list)
    header_regions: list[HeaderDrivenRegion] = field(default_factory=list)
    diagnostics: list[TemplateDiagnostic] = field(default_factory=list)
