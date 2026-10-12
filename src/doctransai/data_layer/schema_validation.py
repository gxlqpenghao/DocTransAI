from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


SCHEMA_COMPONENTS: dict[str, str] = {
    "parsed_document_bundle": "parsed_document_bundle.schema.json",
    "block_inventory": "block_inventory.schema.json",
    "cell_ranges": "cell_ranges.schema.json",
    "diagnostics": "diagnostics.schema.json",
    "evidence_units": "evidence_units.schema.json",
    "qa_seed_pack": "qa_seed_pack.schema.json",
    "sheets": "sheets.schema.json",
    "table_cells": "table_cells.schema.json",
    "table_rows": "table_rows.schema.json",
    "visual_asset_inventory": "visual_asset_inventory.schema.json",
}

REPORT_SCHEMAS: dict[str, str] = {
    "data_quality": "data_quality_report.schema.json",
    "data_quality_report": "data_quality_report.schema.json",
}


def schema_root() -> Path:
    return Path(__file__).resolve().parents[3] / "contracts" / "dataproxy" / "data_asset_pack_v0"


def schema_for_component(component_name: str) -> Path | None:
    schema_name = SCHEMA_COMPONENTS.get(component_name)
    if schema_name is None:
        schema_name = REPORT_SCHEMAS.get(component_name)
    if schema_name is None:
        return None

    path = schema_root() / schema_name
    if not path.is_file():
        raise FileNotFoundError(f"Missing DataProxy contract schema: {path}. Run from a complete source checkout.")
    return path


@lru_cache(maxsize=None)
def _validator_for_schema(schema_path: str) -> Draft202012Validator:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_instance(component_name: str, instance: dict[str, Any]) -> None:
    if instance.get("contract_version") == "data_asset_pack":
        schema_path = Path(__file__).parent / "contracts" / f"{component_name}.schema.json"
        if not schema_path.is_file():
            raise FileNotFoundError(f"Missing contract: {component_name}")
    else:
        schema_path = schema_for_component(component_name)
    if schema_path is None:
        return

    validator = _validator_for_schema(str(schema_path))
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        raise errors[0]


def format_validation_error(location: str, error: ValidationError) -> str:
    path = ".".join(str(part) for part in error.path)
    suffix = f" at {path}" if path else ""
    return f"{location}{suffix}: {error.message}"
