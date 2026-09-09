from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError

from doctransai.data_layer.models import ComponentFile, JsonObject, SourceCorpus
from doctransai.data_layer.schema_validation import format_validation_error, validate_instance


class BundleValidationError(ValueError):
    pass


DEFAULT_COMPONENT_NAMES = {
    "source_manifest",
    "evidence_units",
    "table_units",
    "section_units",
    "block_inventory",
    "sheets",
    "cell_ranges",
    "table_rows",
    "table_cells",
    "visual_asset_inventory",
    "diagnostics",
}


def read_parsed_document_bundle(
    bundle_path: str | Path,
    *,
    validate: bool = True,
    component_names: set[str] | None = None,
    resource_root: Path | None = None,
) -> SourceCorpus:
    path = Path(bundle_path).expanduser().resolve()
    manifest = _read_json(path)

    if validate:
        _validate("parsed_document_bundle", "parsed_document_bundle", manifest)

    bundle_dir = resource_root.resolve() if resource_root else path.parent
    selected_components = DEFAULT_COMPONENT_NAMES if component_names is None else set(component_names)
    if manifest.get("contract_version") not in {"data_asset_pack", "data_asset_pack_v0"}:
        raise BundleValidationError("Unsupported DataProxy contract")
    components = _read_components(bundle_dir, manifest, validate=validate, component_names=selected_components)
    reports = {
        report_name: _resolve_bundle_path(bundle_dir, report_path)
        for report_name, report_path in manifest.get("reports", {}).items()
    }

    return SourceCorpus(
        bundle_path=path,
        contract_version=str(manifest["contract_version"]),
        capabilities=dict(manifest.get("capabilities", {})),
        summary=dict(manifest.get("summary", {})),
        documents=list(manifest.get("documents", [])),
        parse_errors=list(manifest.get("parse_errors", [])),
        components=components,
        reports=reports,
        raw_manifest=manifest,
        resource_root=resource_root,
    )


def _read_components(
    bundle_dir: Path,
    manifest: dict[str, Any],
    *,
    validate: bool,
    component_names: set[str],
) -> dict[str, ComponentFile]:
    components: dict[str, ComponentFile] = {}

    for component_name, descriptor in manifest.get("components", {}).items():
        if component_name not in component_names:
            continue
        component_path = _resolve_bundle_path(bundle_dir, descriptor["path"])
        records = _read_jsonl(component_path)
        expected_count = int(descriptor["count"])

        if len(records) != expected_count:
            raise BundleValidationError(
                f"{component_name}: expected {expected_count} records, found {len(records)}"
            )

        if validate:
            for index, record in enumerate(records):
                if record.get("contract_version") != manifest["contract_version"]:
                    raise BundleValidationError(f"{component_name}: mixed component contract versions")
                _validate(component_name, f"{component_name}[{index}]", record)

        components[component_name] = ComponentFile(
            name=component_name,
            path=component_path,
            count=expected_count,
            records=records,
        )

    return components


def _read_json(path: Path) -> JsonObject:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BundleValidationError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BundleValidationError(f"Invalid JSON file: {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise BundleValidationError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[JsonObject]:
    records: list[JsonObject] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise BundleValidationError(f"JSONL file not found: {path}") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BundleValidationError(f"Invalid JSONL record: {path}:{line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise BundleValidationError(f"Expected JSON object in JSONL: {path}:{line_number}")
        records.append(record)

    return records


def _resolve_bundle_path(bundle_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (bundle_dir / path).resolve()


def _validate(component_name: str, location: str, record: JsonObject) -> None:
    try:
        validate_instance(component_name, record)
    except ValidationError as exc:
        raise BundleValidationError(format_validation_error(location, exc)) from exc
