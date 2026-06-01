from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from doctransai.models.source import SourceModel
from doctransai.models.template import TemplateModel


SCHEMA_NAME = "agentic_mapping_evidence_package"


def build_evidence_package(
    source_model: SourceModel,
    template_model: TemplateModel,
    *,
    source_page_images: list[str | Path | dict[str, Any]] | None = None,
    template_page_images: list[str | Path | dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_images = _normalize_page_images(source_page_images)
    template_images = _normalize_page_images(template_page_images)

    return {
        "schema_name": SCHEMA_NAME,
        "source": {
            "structured": _serialize_source_model(source_model),
            "page_images": source_images,
            "input_gaps": _page_image_input_gaps("source", source_images),
        },
        "template": {
            "structured": _serialize_template_model(template_model),
            "page_images": template_images,
            "input_gaps": _page_image_input_gaps("template", template_images),
        },
    }


def _serialize_source_model(source_model: SourceModel) -> dict[str, Any]:
    documents = [_to_plain_dict(document) for document in source_model.documents]
    records = [_to_plain_dict(record) for record in source_model.records]
    image_assets = [_to_plain_dict(asset) for asset in source_model.image_assets]
    diagnostics = [_to_plain_dict(diagnostic) for diagnostic in source_model.diagnostics]

    object_index: dict[str, Any] = {}
    for record in records:
        record_id = record.get("record_id")
        if record_id:
            object_index[f"record:{record_id}"] = {
                "object_type": "record",
                "record_id": record_id,
            }
            for value_index, _value in enumerate(record.get("values", [])):
                object_index[f"source_value:{record_id}:{value_index}"] = {
                    "object_type": "source_value",
                    "record_id": record_id,
                    "value_index": value_index,
                }

    for asset in image_assets:
        asset_id = asset.get("asset_id")
        if asset_id:
            object_index[f"image_asset:{asset_id}"] = {
                "object_type": "image_asset",
                "asset_id": asset_id,
            }

    for diagnostic_index, _diagnostic in enumerate(diagnostics):
        object_index[f"diagnostic:{diagnostic_index}"] = {
            "object_type": "diagnostic",
            "diagnostic_index": diagnostic_index,
        }

    return {
        "documents": documents,
        "records": records,
        "image_assets": image_assets,
        "diagnostics": diagnostics,
        "object_index": object_index,
    }


def _serialize_template_model(template_model: TemplateModel) -> dict[str, Any]:
    slots = [_to_plain_dict(slot) for slot in template_model.slots]
    repeat_regions = [_to_plain_dict(region) for region in template_model.repeat_regions]
    header_regions = [_to_plain_dict(region) for region in template_model.header_regions]
    diagnostics = [_to_plain_dict(diagnostic) for diagnostic in template_model.diagnostics]

    object_index: dict[str, Any] = {}
    for slot in slots:
        slot_id = slot.get("slot_id")
        if slot_id:
            object_index[f"template_slot:{slot_id}"] = {
                "object_type": "template_slot",
                "slot_id": slot_id,
            }

    for diagnostic_index, _diagnostic in enumerate(diagnostics):
        object_index[f"diagnostic:{diagnostic_index}"] = {
            "object_type": "diagnostic",
            "diagnostic_index": diagnostic_index,
        }

    return {
        "template_id": template_model.template_id,
        "template_path": template_model.template_path,
        "format_key": template_model.format_key,
        "analyzer_key": template_model.analyzer_key,
        "slots": slots,
        "repeat_regions": repeat_regions,
        "header_regions": header_regions,
        "diagnostics": diagnostics,
        "object_index": object_index,
    }


def _normalize_page_images(
    page_images: list[str | Path | dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for page_image in page_images or []:
        if isinstance(page_image, dict):
            normalized.append(_normalize_page_image_dict(page_image))
        elif isinstance(page_image, (str, Path)):
            normalized.append({"image_ref": str(page_image)})
        else:
            normalized.append({"image_ref": str(page_image)})
    return normalized


def _normalize_page_image_dict(page_image: dict[str, Any]) -> dict[str, Any]:
    image_ref = (
        page_image.get("image_ref")
        or page_image.get("image_path")
        or page_image.get("path")
        or page_image.get("asset_path")
        or page_image.get("source_ref")
    )
    normalized: dict[str, Any] = {"image_ref": str(image_ref) if image_ref is not None else ""}

    if page_image.get("page_index") is not None:
        normalized["page_index"] = page_image["page_index"]
    if page_image.get("source") is not None:
        normalized["source"] = str(page_image["source"])

    return normalized


def _page_image_input_gaps(scope: str, page_images: list[dict[str, Any]]) -> list[dict[str, str]]:
    if page_images:
        return []
    if scope == "source":
        return [
            {
                "code": "missing_source_page_images",
                "message": "Source page render images were not provided.",
            }
        ]
    return [
        {
            "code": "missing_template_page_images",
            "message": "Template page render images were not provided.",
        }
    ]


def _to_plain_dict(value: Any) -> Any:
    if is_dataclass(value):
        return _to_plain_dict(asdict(value))
    if isinstance(value, dict):
        return {key: _to_plain_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain_dict(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain_dict(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
