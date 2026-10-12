from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


JsonObject = dict[str, Any]


@dataclass(slots=True)
class ComponentFile:
    name: str
    path: Path
    count: int
    records: list[JsonObject] = field(default_factory=list)


@dataclass(slots=True)
class SourceCorpus:
    bundle_path: Path
    contract_version: str
    capabilities: dict[str, bool]
    summary: JsonObject
    documents: list[JsonObject]
    parse_errors: list[JsonObject]
    components: dict[str, ComponentFile]
    reports: dict[str, Path]
    raw_manifest: JsonObject
    resource_root: Path | None = None
    artifact_manifest: JsonObject | None = None

    def component(self, name: str) -> ComponentFile:
        try:
            return self.components[name]
        except KeyError as exc:
            raise KeyError(f"Bundle component not found: {name}") from exc

    def component_records(self, name: str) -> list[JsonObject]:
        component = self.components.get(name)
        if component is None:
            return []
        return component.records

    @property
    def evidence_units(self) -> list[JsonObject]:
        return self.component_records("evidence_units")

    @property
    def table_units(self) -> list[JsonObject]:
        return self.component_records("table_units")

    @property
    def section_units(self) -> list[JsonObject]:
        return self.component_records("section_units")

    @property
    def source_manifest(self) -> list[JsonObject]:
        return self.component_records("source_manifest")

    @property
    def sheets(self) -> list[JsonObject]:
        return self.component_records("sheets")

    @property
    def cell_ranges(self) -> list[JsonObject]:
        return self.component_records("cell_ranges")

    @property
    def table_rows(self) -> list[JsonObject]:
        return self.component_records("table_rows")

    @property
    def table_cells(self) -> list[JsonObject]:
        return self.component_records("table_cells")

    @property
    def visual_assets(self) -> list[JsonObject]:
        return self.component_records("visual_asset_inventory")

    @property
    def diagnostics(self) -> list[JsonObject]:
        return self.component_records("diagnostics")
