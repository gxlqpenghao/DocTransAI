from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from doctransai.agentic_mapping.template_targets import build_template_targets
from doctransai.models.source import SourceModel
from doctransai.models.template import TemplateModel


SCHEMA_NAME = "agentic_mapping_evidence_package"


def build_evidence_package(
    source_model: SourceModel,
    template_model: TemplateModel,
    *,
    source_page_images: list[str | Path | dict[str, Any]] | None = None,
    template_page_images: list[str | Path | dict[str, Any]] | None = None,
    task_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_images = _normalize_page_images(source_page_images)
    template_images = _normalize_page_images(template_page_images)
    template_structured = _serialize_template_model(template_model)

    package = {
        "schema_name": SCHEMA_NAME,
        "source": {
            "structured": _serialize_source_model(source_model),
            "page_images": source_images,
            "page_image_index": _page_image_index(source_images),
            "input_gaps": _page_image_input_gaps("source", source_images),
        },
        "template": {
            "structured": template_structured,
            "targets": build_template_targets(template_structured),
            "page_images": template_images,
            "page_image_index": _page_image_index(template_images),
            "input_gaps": _page_image_input_gaps("template", template_images),
        },
    }
    if task_context:
        package["task"] = _to_plain_dict(task_context)
    return package


def _serialize_source_model(source_model: SourceModel) -> dict[str, Any]:
    documents = [_to_plain_dict(document) for document in source_model.documents]
    records = [_source_record_to_plain_dict(record) for record in source_model.records]
    image_assets = [_to_plain_dict(asset) for asset in source_model.image_assets]
    diagnostics = [_to_plain_dict(diagnostic) for diagnostic in source_model.diagnostics]

    object_index: dict[str, Any] = {}
    for record in records:
        record_id = record.get("record_id")
        if record_id:
            record_ref = f"record:{record_id}"
            _put_index(
                object_index,
                record_ref,
                _compact_mapping({
                    "object_type": "record",
                    "record_id": record_id,
                    "document_id": record.get("document_id"),
                    "locator": _compact_locator(record.get("locator")),
                    "evidence_id": record.get("evidence_id"),
                    "cell_range_id": record.get("cell_range_id"),
                    "table_id": record.get("table_id"),
                }),
            )
            if record.get("evidence_id"):
                _put_index(
                    object_index,
                    f"evidence:{record['evidence_id']}",
                    _alias_entry("record_alias", record_ref),
                )
            for value_index, value in enumerate(record.get("values", [])):
                if not isinstance(value, dict):
                    continue
                canonical_ref = f"source_value:{record_id}:{value_index}"
                _put_index(object_index, canonical_ref, {"object_type": "source_value"})

    for asset in image_assets:
        asset_id = asset.get("asset_id")
        if asset_id:
            canonical_ref = f"image_asset:{asset_id}"
            _put_index(object_index, canonical_ref, _image_asset_index_entry(asset))
            for alias_key in _image_asset_alias_keys(asset):
                if alias_key != canonical_ref:
                    _put_index(object_index, alias_key, _alias_entry("image_asset_alias", canonical_ref))

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
            entry = {
                "object_type": "template_slot",
                "slot_id": slot_id,
                "raw_name": slot.get("raw_name"),
                "canonical_name": slot.get("canonical_name"),
                "slot_kind": slot.get("slot_kind"),
                "address": slot.get("address"),
            }
            _put_index(object_index, f"template_slot:{slot_id}", entry)
            _put_index(object_index, f"writable_target:{slot_id}", {**entry, "object_type": "writable_target"})

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


def _image_asset_index_entry(asset: dict[str, Any]) -> dict[str, Any]:
    return _compact_mapping({
        "object_type": "image_asset",
        "asset_id": asset.get("asset_id"),
        "source_ref": asset.get("source_ref"),
        "page_anchor": asset.get("page_anchor"),
        "bbox": asset.get("bbox"),
        "block_id": asset.get("block_id"),
        "sheet_name": asset.get("sheet_name"),
        "cell_anchor": asset.get("cell_anchor"),
        "row_index": asset.get("row_index"),
        "column_index": asset.get("column_index"),
        "related_evidence_ids": asset.get("related_evidence_ids"),
    })


def _image_asset_alias_keys(asset: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for value in (asset.get("source_ref"),):
        if not isinstance(value, str) or not value:
            continue
        keys.append(value)
        without_suffix = str(Path(value).with_suffix(""))
        if without_suffix and without_suffix != value:
            keys.append(without_suffix)
    return list(dict.fromkeys(keys))


def _source_record_to_plain_dict(record: Any) -> dict[str, Any]:
    payload = _to_plain_dict(record)
    if not isinstance(payload, dict):
        return {}

    # source_path is preserved once in documents; repeating it on every record
    # and provenance item dominates larger spreadsheet payloads.
    payload.pop("source_path", None)
    for value in payload.get("values", []):
        if not isinstance(value, dict):
            continue
        if value.get("confidence_base") in (None, 0, 0.0):
            value.pop("confidence_base", None)
        for provenance in value.get("provenance", []):
            if isinstance(provenance, dict):
                provenance.pop("source_path", None)
    return payload


def _alias_entry(object_type: str, canonical_ref: str) -> dict[str, Any]:
    return {
        "object_type": object_type,
        "ref": canonical_ref,
    }


def _compact_locator(locator: Any) -> dict[str, Any] | None:
    if not isinstance(locator, dict):
        return None

    allowed_keys = (
        "page",
        "page_index",
        "page_anchor",
        "bbox",
        "block_id",
        "sheet_name",
        "cell_range",
        "cell_range_id",
        "cell_anchor",
        "row_index",
        "column_index",
        "table_id",
        "table_index",
        "section_title",
    )
    compact = {
        key: locator.get(key)
        for key in allowed_keys
        if locator.get(key) not in (None, {}, [])
    }
    return compact or None


def _compact_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, {}, [])
    }


def _put_index(object_index: dict[str, Any], key: str, value: dict[str, Any]) -> None:
    if key not in object_index:
        object_index[key] = value


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


def _page_image_index(page_images: list[dict[str, Any]]) -> dict[str, Any]:
    index: dict[str, Any] = {}
    for image_index, page_image in enumerate(page_images):
        entry = {
            "image_ref": page_image.get("image_ref"),
            "page_index": page_image.get("page_index"),
            "source": page_image.get("source"),
        }
        index[f"page_image:{image_index}"] = entry
        source = page_image.get("source")
        page_index = page_image.get("page_index")
        if isinstance(source, str) and source and isinstance(page_index, int):
            index[f"source_page:{source}:index:{page_index}"] = entry
            index[f"source_page:{source}:page:{page_index + 1}"] = entry
    return index


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
        return {
            key: plain_item
            for key, item in value.items()
            if key != "raw"
            for plain_item in [_to_plain_dict(item)]
            if plain_item not in (None, {}, [])
        }
    if isinstance(value, list):
        return [_to_plain_dict(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain_dict(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
