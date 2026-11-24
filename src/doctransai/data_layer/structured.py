"""Adapt business records to the existing source-bundle contract.

The structured path is deliberately an adapter, not a second conversion engine.
It creates a small local data-asset bundle with stable evidence and asset refs so
the existing SourceView, tool runtime, renderer and audit code can be reused.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


class StructuredInputError(ValueError):
    """The structured integration payload is invalid or unsafe."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise StructuredInputError(f"{label} must be a nonempty string")
    return value.strip()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _copy_asset(item: dict[str, Any], destination: Path) -> tuple[str, Path]:
    asset_id = _safe_id(item.get("asset_id"), "images[].asset_id")
    source_path = item.get("path")
    data_b64 = item.get("base64")
    if bool(source_path) == bool(data_b64):
        raise StructuredInputError(f"image {asset_id} must provide exactly one of path or base64")
    filename = Path(str(item.get("filename") or f"{asset_id}.bin")).name
    if not filename or filename in {".", ".."} or len(filename) > 180:
        raise StructuredInputError(f"image {asset_id} has an invalid filename")
    target = destination / f"{asset_id}-{filename}"
    if data_b64:
        try:
            raw = base64.b64decode(data_b64, validate=True)
        except Exception as exc:
            raise StructuredInputError(f"image {asset_id} base64 is invalid") from exc
        if not raw or len(raw) > 20 * 1024 * 1024:
            raise StructuredInputError(f"image {asset_id} is empty or exceeds 20 MiB")
        target.write_bytes(raw)
    else:
        source = Path(str(source_path)).expanduser().resolve()
        if not source.is_file():
            raise StructuredInputError(f"image {asset_id} path does not exist")
        if source.stat().st_size > 20 * 1024 * 1024:
            raise StructuredInputError(f"image {asset_id} exceeds 20 MiB")
        shutil.copyfile(source, target)
    return asset_id, target


def materialize_structured_bundle(payload: dict[str, Any], work_dir: Path) -> Path:
    """Write a structured payload as a reusable local source manifest.

    The returned manifest is accepted by ``read_source_input`` and therefore by
    the normal conversion path. ``work_dir`` must be a new task directory.
    """
    if not isinstance(payload, dict):
        raise StructuredInputError("structured input must be an object")
    if work_dir.exists():
        raise StructuredInputError("structured bundle directory already exists")
    document_id = _safe_id(payload.get("document_id", "structured-document"), "document_id")
    source_name = _safe_id(payload.get("source_name", "structured-records.json"), "source_name")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise StructuredInputError("records must be a nonempty array")
    root = work_dir.resolve()
    root.mkdir(parents=True)
    assets_dir = root / "assets"
    assets_dir.mkdir()

    source_path = root / source_name
    normalized_records: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    visual_assets: list[dict[str, Any]] = []
    seen_record_ids: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise StructuredInputError(f"records[{index}] must be an object")
        record_id = _safe_id(record.get("record_id"), f"records[{index}].record_id")
        if record_id in seen_record_ids:
            raise StructuredInputError(f"duplicate record_id: {record_id}")
        seen_record_ids.add(record_id)
        fields = record.get("fields", {})
        if not isinstance(fields, dict):
            raise StructuredInputError(f"records[{index}].fields must be an object")
        normalized = {"record_id": record_id, "fields": fields}
        normalized_records.append(normalized)
        for field_name, value in fields.items():
            if not isinstance(field_name, str) or not field_name.strip():
                raise StructuredInputError(f"records[{index}] contains an invalid field name")
            ref = f"structured:{record_id}:{field_name.strip()}"
            text = "" if value is None else str(value)
            evidence.append({
                "contract_version": "data_asset_pack",
                "evidence_id": ref,
                "document_id": document_id,
                "text": text,
                "source_text": text,
                "locator": {"record_id": record_id, "field_name": field_name.strip()},
                "object_id": ref,
                "page_anchor": f"record:{record_id}",
                "record_id": record_id,
                "field_name": field_name.strip(),
            })
        for image_index, item in enumerate(record.get("images", []) or []):
            if not isinstance(item, dict):
                raise StructuredInputError(f"records[{index}].images[{image_index}] must be an object")
            item = dict(item)
            item.setdefault("asset_id", f"{record_id}-image-{image_index + 1}")
            asset_id, target = _copy_asset(item, assets_dir)
            visual_assets.append({
                "contract_version": "data_asset_pack",
                "asset_id": asset_id,
                "document_id": document_id,
                "asset_type": item.get("asset_type", "image"),
                "source_ref": str(target.relative_to(root)),
                "checksum": _sha256(target),
                "page_anchor": f"record:{record_id}",
                "record_id": record_id,
                "caption": item.get("caption"),
                "nearby_text_before": item.get("caption", ""),
                "nearby_text_after": "",
            })

    source_path.write_text(json.dumps({"document_id": document_id, "records": normalized_records}, ensure_ascii=False, indent=2), encoding="utf-8")
    checksum = _sha256(source_path)
    source_manifest = [{
        "contract_version": "data_asset_pack",
        "document_id": document_id,
        "source_path": source_name,
        "source_checksum": checksum,
        "original_filename": source_name,
        "record_count": len(records),
    }]
    components: dict[str, list[dict[str, Any]]] = {
        "source_manifest": source_manifest,
        "evidence_units": evidence,
        "visual_asset_inventory": visual_assets,
    }
    descriptors: dict[str, dict[str, Any]] = {}
    (root / "components").mkdir()
    for name, rows in components.items():
        path = f"components/{name}.jsonl"
        _write_jsonl(root / path, rows)
        descriptors[name] = {"path": path, "count": len(rows)}
    manifest = {
        "contract_version": "data_asset_pack",
        "capabilities": {"structured_input": True, "source_documents": True, "visual_assets": bool(visual_assets)},
        "summary": {"document_count": 1, "record_count": len(records), "source": "structured_business_records"},
        "documents": [{"document_id": document_id, "source_path": source_name, "source_checksum": checksum}],
        "parse_errors": [],
        "components": descriptors,
        "reports": {},
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path
