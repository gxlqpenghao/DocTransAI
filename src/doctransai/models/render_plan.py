from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.source import ProvenanceRef


SCHEMA_VERSION = "doctransai_render_plan_v1"


@dataclass(slots=True)
class TemplateRef:
    template_path: str
    format_key: str
    template_id: str | None = None


@dataclass(slots=True)
class OutputRef:
    output_path: str
    output_format: str


@dataclass(slots=True)
class TargetRef:
    format_key: str
    target_kind: str
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
    notes: str | None = None
    repeat_region_id: str | None = None
    instance_index: int | None = None
    allow_same_name_residual_fill: bool = False


@dataclass(slots=True)
class TextFill:
    slot_id: str
    target: TargetRef
    value: str
    provenance_refs: list[ProvenanceRef] = field(default_factory=list)
    value_type: str = "text"
    confidence: float = 1.0
    transform: str | None = None


@dataclass(slots=True)
class ImagePlacement:
    slot_id: str
    asset_id: str
    source_ref: str | None
    target: TargetRef
    provenance_refs: list[ProvenanceRef] = field(default_factory=list)
    sizing_policy: str = "contain"
    caption: str | None = None
    caption_slot_id: str | None = None
    caption_target: TargetRef | None = None


@dataclass(slots=True)
class RowPlan:
    record_id: str
    repeat_region_id: str | None = None
    slot_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlanDiagnostic:
    severity: str
    code: str
    message: str
    field: str | None = None


@dataclass(slots=True)
class RenderPlan:
    plan_id: str
    source_bundle_path: str
    template: TemplateRef
    output: OutputRef
    text_fills: list[TextFill] = field(default_factory=list)
    image_placements: list[ImagePlacement] = field(default_factory=list)
    unresolved_slots: list[UnresolvedSlot] = field(default_factory=list)
    diagnostics: list[PlanDiagnostic] = field(default_factory=list)
    created_at: str = ""
    record_plans: list[RowPlan] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


def render_plan_to_dict(plan: RenderPlan) -> dict[str, Any]:
    return asdict(plan)


def render_plan_from_dict(payload: dict[str, Any]) -> RenderPlan:
    return RenderPlan(
        plan_id=str(payload["plan_id"]),
        source_bundle_path=str(payload["source_bundle_path"]),
        template=_template_ref_from_dict(payload["template"]),
        output=_output_ref_from_dict(payload["output"]),
        text_fills=[_text_fill_from_dict(item) for item in payload.get("text_fills", [])],
        image_placements=[_image_placement_from_dict(item) for item in payload.get("image_placements", [])],
        unresolved_slots=[_unresolved_slot_from_dict(item) for item in payload.get("unresolved_slots", [])],
        diagnostics=[_plan_diagnostic_from_dict(item) for item in payload.get("diagnostics", [])],
        created_at=str(payload.get("created_at", "")),
        record_plans=[_row_plan_from_dict(item) for item in payload.get("record_plans", [])],
        schema_version=str(payload.get("schema_version", SCHEMA_VERSION)),
    )


def _template_ref_from_dict(payload: dict[str, Any]) -> TemplateRef:
    return TemplateRef(
        template_path=str(payload["template_path"]),
        format_key=str(payload["format_key"]),
        template_id=_optional_string(payload.get("template_id")),
    )


def _output_ref_from_dict(payload: dict[str, Any]) -> OutputRef:
    return OutputRef(
        output_path=str(payload["output_path"]),
        output_format=str(payload["output_format"]),
    )


def _target_ref_from_dict(payload: dict[str, Any]) -> TargetRef:
    return TargetRef(
        format_key=str(payload["format_key"]),
        target_kind=str(payload["target_kind"]),
        paragraph_index=_optional_int(payload.get("paragraph_index")),
        cell_paragraph_index=_optional_int(payload.get("cell_paragraph_index")),
        run_index=_optional_int(payload.get("run_index")),
        run_end_index=_optional_int(payload.get("run_end_index")),
        table_index=_optional_int(payload.get("table_index")),
        row_index=_optional_int(payload.get("row_index")),
        column_index=_optional_int(payload.get("column_index")),
        sheet_name=_optional_string(payload.get("sheet_name")),
        cell_ref=_optional_string(payload.get("cell_ref")),
        page_index=_optional_int(payload.get("page_index")),
        form_field_name=_optional_string(payload.get("form_field_name")),
        bbox=_optional_float_list(payload.get("bbox")),
        notes=_optional_string(payload.get("notes")),
        repeat_region_id=_optional_string(payload.get("repeat_region_id")),
        instance_index=_optional_int(payload.get("instance_index")),
        allow_same_name_residual_fill=bool(payload.get("allow_same_name_residual_fill", False)),
    )


def _text_fill_from_dict(payload: dict[str, Any]) -> TextFill:
    return TextFill(
        slot_id=str(payload["slot_id"]),
        target=_target_ref_from_dict(payload["target"]),
        value=str(payload["value"]),
        provenance_refs=[_provenance_ref_from_dict(item) for item in payload.get("provenance_refs", [])],
        value_type=str(payload.get("value_type", "text")),
        confidence=float(payload.get("confidence", 1.0)),
        transform=_optional_string(payload.get("transform")),
    )


def _image_placement_from_dict(payload: dict[str, Any]) -> ImagePlacement:
    return ImagePlacement(
        slot_id=str(payload["slot_id"]),
        asset_id=str(payload["asset_id"]),
        source_ref=_optional_string(payload.get("source_ref")),
        target=_target_ref_from_dict(payload["target"]),
        provenance_refs=[_provenance_ref_from_dict(item) for item in payload.get("provenance_refs", [])],
        sizing_policy=str(payload.get("sizing_policy", "contain")),
        caption=_optional_string(payload.get("caption")),
        caption_slot_id=_optional_string(payload.get("caption_slot_id")),
        caption_target=_target_ref_from_dict(payload["caption_target"]) if isinstance(payload.get("caption_target"), dict) else None,
    )


def _unresolved_slot_from_dict(payload: dict[str, Any]) -> UnresolvedSlot:
    return UnresolvedSlot(
        slot_id=str(payload["slot_id"]),
        canonical_key=str(payload["canonical_key"]),
        reason_code=str(payload["reason_code"]),
        message=str(payload["message"]),
        candidate_ids=[str(item) for item in payload.get("candidate_ids", [])],
        provenance_refs=[_provenance_ref_from_dict(item) for item in payload.get("provenance_refs", [])],
    )


def _plan_diagnostic_from_dict(payload: dict[str, Any]) -> PlanDiagnostic:
    return PlanDiagnostic(
        severity=str(payload["severity"]),
        code=str(payload["code"]),
        message=str(payload["message"]),
        field=_optional_string(payload.get("field")),
    )


def _row_plan_from_dict(payload: dict[str, Any]) -> RowPlan:
    return RowPlan(
        record_id=str(payload["record_id"]),
        repeat_region_id=_optional_string(payload.get("repeat_region_id")),
        slot_ids=[str(item) for item in payload.get("slot_ids", [])],
    )


def _provenance_ref_from_dict(payload: dict[str, Any]) -> ProvenanceRef:
    return ProvenanceRef(
        source_kind=str(payload["source_kind"]),
        document_id=_optional_string(payload.get("document_id")),
        evidence_id=_optional_string(payload.get("evidence_id")),
        asset_id=_optional_string(payload.get("asset_id")),
        object_id=_optional_string(payload.get("object_id")),
        locator=dict(payload.get("locator", {})),
        source_path=_optional_string(payload.get("source_path")),
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    return [float(item) for item in value]
