from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import Any

from doctransai.models.source import SourceModel, SourceRecord
from doctransai.models.template import TemplateModel, TemplateSlot


FULL_AGENT_CONTEXT_SCHEMA_VERSION = "doctransai_full_agent_context_v1"
NAVIGATION_CONTEXT_AUTHORITY = "navigation_only_not_evidence"


def build_full_agent_context(
    *,
    source_model: SourceModel,
    primary_record: SourceRecord,
    template_model: TemplateModel | None,
    template_slots_by_id: dict[str, TemplateSlot],
    source_document_view: str,
    source_instance_overview: dict[str, Any] | None,
    source_cluster_plan: dict[str, Any] | None,
    task_context: dict[str, Any],
    template_document_view: str | None = None,
    template_visual_pages: list[str] | None = None,
) -> dict[str, Any]:
    task_payload = _to_plain_data(task_context)
    repeat_region_cluster_hints = _repeat_region_cluster_hints(source_cluster_plan)
    if repeat_region_cluster_hints and "repeat_region_cluster_hints" not in task_payload:
        task_payload["repeat_region_cluster_hints"] = repeat_region_cluster_hints
    return {
        "schema_version": FULL_AGENT_CONTEXT_SCHEMA_VERSION,
        "full_source_context": _full_source_context(
            source_model=source_model,
            primary_record=primary_record,
            source_document_view=source_document_view,
        ),
        "full_template_context": _full_template_context(
            template_model=template_model,
            template_slots_by_id=template_slots_by_id,
            template_document_view=template_document_view,
            template_visual_pages=template_visual_pages,
        ),
        "navigation_context": {
            "authority": NAVIGATION_CONTEXT_AUTHORITY,
            "source_instance_overview": _to_plain_data(source_instance_overview),
            "source_cluster_plan": _to_plain_data(source_cluster_plan),
        },
        "task_context": task_payload,
    }


def _full_source_context(
    *,
    source_model: SourceModel,
    primary_record: SourceRecord,
    source_document_view: str,
) -> dict[str, Any]:
    documents = [_to_plain_data(document) for document in source_model.documents]
    records = [_to_plain_data(record) for record in source_model.records]
    image_assets = [_to_plain_data(asset) for asset in source_model.image_assets]
    diagnostics = _to_plain_data(source_model.diagnostics)
    return {
        "documents": documents,
        "records": records,
        "image_assets": image_assets,
        "object_index": _source_object_index(records=records, image_assets=image_assets),
        "diagnostics": diagnostics,
        "document_view": source_document_view,
        "primary_record_id": primary_record.record_id,
        "record_count": len(records),
        "image_asset_count": len(image_assets),
        "diagnostic_count": len(diagnostics),
    }


def _source_object_index(
    *,
    records: list[dict[str, Any]],
    image_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    by_object_key: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        record_id = record.get("record_id")
        if not record_id:
            continue
        object_id = str(record_id)
        by_object_key[f"record:{object_id}"] = {
            "object_kind": "record",
            "object_id": object_id,
            "collection": "records",
            "index": index,
        }
    for index, asset in enumerate(image_assets):
        asset_id = asset.get("asset_id")
        if not asset_id:
            continue
        object_id = str(asset_id)
        by_object_key[f"image_asset:{object_id}"] = {
            "object_kind": "image_asset",
            "object_id": object_id,
            "collection": "image_assets",
            "index": index,
        }
    return {"by_object_key": by_object_key}


def _full_template_context(
    *,
    template_model: TemplateModel | None,
    template_slots_by_id: dict[str, TemplateSlot],
    template_document_view: str | None,
    template_visual_pages: list[str] | None,
) -> dict[str, Any]:
    slots = _template_slots(template_model=template_model, template_slots_by_id=template_slots_by_id)
    visual_pages = list(template_visual_pages or [])
    document_view = template_document_view or ""
    if template_model is None:
        return {
            "template": None,
            "slots": slots,
            "repeat_regions": [],
            "header_regions": [],
            "diagnostics": [],
            "document_view": document_view,
            "visual_pages": visual_pages,
            "slot_count": len(slots),
            "repeat_region_count": 0,
            "header_region_count": 0,
        }

    repeat_regions = [_to_plain_data(region) for region in template_model.repeat_regions]
    header_regions = [_to_plain_data(region) for region in template_model.header_regions]
    diagnostics = [_to_plain_data(diagnostic) for diagnostic in template_model.diagnostics]
    return {
        "template": {
            "template_id": template_model.template_id,
            "template_path": template_model.template_path,
            "format_key": template_model.format_key,
            "analyzer_key": template_model.analyzer_key,
        },
        "slots": slots,
        "repeat_regions": repeat_regions,
        "header_regions": header_regions,
        "diagnostics": diagnostics,
        "document_view": document_view,
        "visual_pages": visual_pages,
        "slot_count": len(slots),
        "repeat_region_count": len(repeat_regions),
        "header_region_count": len(header_regions),
    }


def _template_slots(
    *,
    template_model: TemplateModel | None,
    template_slots_by_id: dict[str, TemplateSlot],
) -> list[dict[str, Any]]:
    if template_model is not None:
        return [_to_plain_data(slot) for slot in template_model.slots]
    return [_to_plain_data(slot) for slot in template_slots_by_id.values()]


def _to_plain_data(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return deepcopy(value)


def _repeat_region_cluster_hints(source_cluster_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(source_cluster_plan, dict):
        return []
    hints: list[dict[str, Any]] = []
    for region in source_cluster_plan.get("repeat_regions") or []:
        if not isinstance(region, dict):
            continue
        candidate_cluster_ids = [str(item) for item in region.get("candidate_cluster_ids") or []]
        if not candidate_cluster_ids:
            continue
        hints.append(
            {
                "region_id": region.get("region_id"),
                "candidate_cluster_ids": candidate_cluster_ids,
                "coverage_by_cluster_id": _to_plain_data(region.get("coverage_by_cluster_id") or {}),
            }
        )
    return hints
