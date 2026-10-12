from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProvenanceRef:
    source_kind: str
    document_id: str | None = None
    evidence_id: str | None = None
    asset_id: str | None = None
    object_id: str | None = None
    locator: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None


@dataclass(slots=True)
class SourceDocument:
    document_id: str
    source_path: str
    doc_type: str | None = None
    document_title: str | None = None
    source_checksum: str | None = None
    parser_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SourceValue:
    canonical_key: str
    value: str
    raw_label: str | None = None
    value_type: str = "text"
    confidence_base: float = 0.0
    provenance: list[ProvenanceRef] = field(default_factory=list)


@dataclass(slots=True)
class SourceImageAsset:
    asset_id: str
    document_id: str | None = None
    source_path: str | None = None
    source_ref: str | None = None
    asset_path: str | None = None
    asset_source: str | None = None
    page_anchor: str | None = None
    bbox: Any | None = None
    block_id: str | None = None
    order_index: int | None = None
    sheet_name: str | None = None
    cell_anchor: str | None = None
    row_index: int | None = None
    column_index: int | None = None
    related_evidence_ids: list[str] = field(default_factory=list)
    nearby_text_before: list[str] = field(default_factory=list)
    nearby_text_after: list[str] = field(default_factory=list)
    nearby_evidence_ids: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SourceRecord:
    record_id: str
    document_id: str
    source_path: str
    values: list[SourceValue] = field(default_factory=list)
    evidence_id: str | None = None
    cell_range_id: str | None = None
    table_id: str | None = None
    locator: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SourceModel:
    documents: list[SourceDocument] = field(default_factory=list)
    records: list[SourceRecord] = field(default_factory=list)
    image_assets: list[SourceImageAsset] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @property
    def documents_by_id(self) -> dict[str, SourceDocument]:
        return {document.document_id: document for document in self.documents}
