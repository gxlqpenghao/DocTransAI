from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from doctransai.data_layer.models import JsonObject, SourceCorpus
from doctransai.models.source import (
    ProvenanceRef,
    SourceDocument,
    SourceImageAsset,
    SourceModel,
    SourceRecord,
    SourceValue,
)


class SourceModelAdaptationError(ValueError):
    pass


@dataclass(slots=True)
class AdaptedSourceModel(SourceModel):
    evidence_records: list[SourceRecord] = field(default_factory=list)
    table_records: list[SourceRecord] = field(default_factory=list)
    cell_range_records: list[SourceRecord] = field(default_factory=list)
    table_row_records: list[SourceRecord] = field(default_factory=list)
    table_cell_records: list[SourceRecord] = field(default_factory=list)
    xlsx_row_records: list[SourceRecord] = field(default_factory=list)
    sheet_records: list[SourceRecord] = field(default_factory=list)

    @property
    def evidence_by_id(self) -> dict[str, SourceRecord]:
        return {record.evidence_id: record for record in self.evidence_records if record.evidence_id is not None}

    @property
    def tables_by_id(self) -> dict[str, SourceRecord]:
        return {record.table_id: record for record in self.table_records if record.table_id is not None}

    @property
    def cell_ranges_by_id(self) -> dict[str, SourceRecord]:
        return {
            record.cell_range_id: record
            for record in self.cell_range_records
            if record.cell_range_id is not None
        }

    @property
    def sheets_by_id(self) -> dict[str, SourceRecord]:
        return {record.record_id: record for record in self.sheet_records}

    @property
    def image_assets_by_id(self) -> dict[str, SourceImageAsset]:
        return {asset.asset_id: asset for asset in self.image_assets}

    @property
    def diagnostics_by_id(self) -> dict[str, JsonObject]:
        return {str(record["diagnostic_id"]): record for record in self.diagnostics}


def adapt_source_corpus(corpus: SourceCorpus) -> AdaptedSourceModel:
    document_payloads = _document_payloads(corpus)
    documents = [
        _document_from_record(record, component_name="source_manifest", index=index)
        for index, record in enumerate(document_payloads)
    ]
    documents_by_id = {document.document_id: document for document in documents}

    evidence_records = [
        _evidence_record_from_raw(record, documents_by_id=documents_by_id, index=index)
        for index, record in enumerate(corpus.evidence_units)
    ]
    table_records = [
        _table_record_from_raw(record, documents_by_id=documents_by_id, index=index)
        for index, record in enumerate(corpus.table_units)
    ]
    table_cells_by_row = _table_cells_by_row(corpus.table_cells)
    table_row_records = [
        _table_row_record_from_raw(
            record,
            documents_by_id=documents_by_id,
            table_cells_by_row=table_cells_by_row,
            index=index,
        )
        for index, record in enumerate(corpus.table_rows)
    ]
    table_cell_records = [
        _table_cell_record_from_raw(record, documents_by_id=documents_by_id, index=index)
        for index, record in enumerate(corpus.table_cells)
    ]
    cell_range_records = [
        _cell_range_record_from_raw(record, documents_by_id=documents_by_id, index=index)
        for index, record in enumerate(corpus.cell_ranges)
    ]
    sheet_records = [
        _sheet_record_from_raw(record, documents_by_id=documents_by_id, index=index)
        for index, record in enumerate(corpus.sheets)
    ]
    image_block_context_by_asset_id = _image_block_context_by_asset_id(corpus.component_records("block_inventory"))
    image_assets = [
        _image_asset_from_raw(
            record,
            documents_by_id=documents_by_id,
            bundle_dir=corpus.bundle_path.parent,
            image_block_context_by_asset_id=image_block_context_by_asset_id,
            index=index,
        )
        for index, record in enumerate(corpus.visual_assets)
    ]
    diagnostics = [
        _diagnostic_from_raw(record, index=index)
        for index, record in enumerate(corpus.diagnostics)
    ]

    return AdaptedSourceModel(
        documents=documents,
        records=[*evidence_records, *table_records, *cell_range_records, *table_row_records, *table_cell_records, *sheet_records],
        image_assets=image_assets,
        diagnostics=diagnostics,
        evidence_records=evidence_records,
        table_records=table_records,
        cell_range_records=cell_range_records,
        table_row_records=table_row_records,
        table_cell_records=table_cell_records,
        xlsx_row_records=list(cell_range_records),
        sheet_records=sheet_records,
    )


def _document_payloads(corpus: SourceCorpus) -> list[JsonObject]:
    manifest_documents_by_id: dict[str, JsonObject] = {}
    for index, record in enumerate(corpus.documents):
        document_id = _required_string(record, "document_id", "documents", index)
        manifest_documents_by_id[document_id] = dict(record)

    if not corpus.source_manifest:
        return list(manifest_documents_by_id.values())

    payloads: list[JsonObject] = []
    seen_document_ids: set[str] = set()

    for index, record in enumerate(corpus.source_manifest):
        document_id = _required_string(record, "document_id", "source_manifest", index)
        _required_string(record, "source_path", "source_manifest", index)
        merged = dict(manifest_documents_by_id.get(document_id, {}))
        merged.update(record)
        payloads.append(merged)
        seen_document_ids.add(document_id)

    for document_id, record in manifest_documents_by_id.items():
        if document_id not in seen_document_ids:
            payloads.append(dict(record))

    return payloads


def _document_from_record(record: JsonObject, *, component_name: str, index: int) -> SourceDocument:
    parser_name = _optional_string(record.get("parser_name")) or _optional_string(record.get("artifact_parser_name"))
    return SourceDocument(
        document_id=_required_string(record, "document_id", component_name, index),
        source_path=_required_string(record, "source_path", component_name, index),
        doc_type=_optional_string(record.get("doc_type")),
        document_title=_optional_string(record.get("document_title")),
        source_checksum=_optional_string(record.get("source_checksum")),
        parser_name=parser_name,
        raw=dict(record),
    )


def _evidence_record_from_raw(
    record: JsonObject,
    *,
    documents_by_id: dict[str, SourceDocument],
    index: int,
) -> SourceRecord:
    component_name = "evidence_units"
    document = _document_for_record(record, documents_by_id=documents_by_id, component_name=component_name, index=index)
    evidence_id = _required_string(record, "evidence_id", component_name, index)
    locator = _optional_object(record.get("locator"))
    source_path = _optional_string(record.get("source_path")) or document.source_path
    values: list[SourceValue] = []
    text = _optional_string(record.get("text"))
    if text is not None:
        values.append(
            SourceValue(
                canonical_key="text",
                value=text,
                raw_label="text",
                provenance=[
                    _provenance_ref(
                        source_kind="evidence",
                        document_id=document.document_id,
                        source_path=source_path,
                        object_id=evidence_id,
                        locator=locator,
                        evidence_id=evidence_id,
                    )
                ],
            )
        )

    return SourceRecord(
        record_id=evidence_id,
        document_id=document.document_id,
        source_path=source_path,
        values=values,
        evidence_id=evidence_id,
        cell_range_id=_optional_string(locator.get("cell_range_id")),
        table_id=_optional_string(locator.get("table_id")),
        locator=locator,
        raw=dict(record),
    )


def _table_record_from_raw(
    record: JsonObject,
    *,
    documents_by_id: dict[str, SourceDocument],
    index: int,
) -> SourceRecord:
    component_name = "table_units"
    document = _document_for_record(record, documents_by_id=documents_by_id, component_name=component_name, index=index)
    table_id = _required_string(record, "table_id", component_name, index)
    source_path = _optional_string(record.get("source_path")) or document.source_path
    table_json = _optional_object(record.get("table_json"))
    table_text = _optional_string(table_json.get("body_text")) or _table_text_from_cells(table_json.get("cells"))
    locator = {
        "page_anchor": _optional_string(record.get("page_anchor")),
        "section_id": _optional_string(record.get("section_id")),
        "locator_summary": _optional_string(_optional_object(record.get("table_identity")).get("locator_summary")),
    }
    values: list[SourceValue] = []
    if table_text is not None:
        values.append(
            SourceValue(
                canonical_key="table_text",
                value=table_text,
                raw_label="body_text",
                provenance=[
                    _provenance_ref(
                        source_kind="table",
                        document_id=document.document_id,
                        source_path=source_path,
                        object_id=table_id,
                        locator=locator,
                    )
                ],
            )
        )

    return SourceRecord(
        record_id=table_id,
        document_id=document.document_id,
        source_path=source_path,
        values=values,
        table_id=table_id,
        locator=locator,
        raw=dict(record),
    )


def _cell_range_record_from_raw(
    record: JsonObject,
    *,
    documents_by_id: dict[str, SourceDocument],
    index: int,
) -> SourceRecord:
    component_name = "cell_ranges"
    document = _document_for_record(record, documents_by_id=documents_by_id, component_name=component_name, index=index)
    cell_range_id = _required_string(record, "cell_range_id", component_name, index)
    source_path = _optional_string(record.get("source_path")) or document.source_path
    locator = {
        "sheet_id": _optional_string(record.get("sheet_id")),
        "sheet_name": _optional_string(record.get("sheet_name")),
        "cell_range": _optional_string(record.get("range_ref")),
        "row_index": _optional_int(_optional_object(record.get("parser_signals")).get("row_index")),
        "range_type": _optional_string(record.get("range_type")),
    }
    values = _cell_range_values(
        record,
        document_id=document.document_id,
        source_path=source_path,
        cell_range_id=cell_range_id,
        locator=locator,
    )
    return SourceRecord(
        record_id=cell_range_id,
        document_id=document.document_id,
        source_path=source_path,
        values=values,
        cell_range_id=cell_range_id,
        locator=locator,
        raw=dict(record),
    )


def _table_row_record_from_raw(
    record: JsonObject,
    *,
    documents_by_id: dict[str, SourceDocument],
    table_cells_by_row: dict[tuple[str, str, int], list[JsonObject]],
    index: int,
) -> SourceRecord:
    component_name = "table_rows"
    document = _document_for_record(record, documents_by_id=documents_by_id, component_name=component_name, index=index)
    table_row_id = _required_string(record, "table_row_id", component_name, index)
    table_id = _required_string(record, "table_id", component_name, index)
    row_index = _required_int(record, "row_index", component_name, index)
    source_path = _optional_string(record.get("source_path")) or document.source_path
    is_header = bool(record.get("is_header"))
    locator = {
        "page_anchor": _optional_string(record.get("page_anchor")),
        "table_id": table_id,
        "row_index": row_index,
        "table_title": _optional_string(record.get("table_title")),
    }
    values: list[SourceValue] = []

    if not is_header:
        row_text = _optional_string(record.get("row_text"))
        if row_text is not None:
            values.append(
                SourceValue(
                    canonical_key="row_text",
                    value=row_text,
                    raw_label="row_text",
                    provenance=[
                        _provenance_ref(
                            source_kind="table_row",
                            document_id=document.document_id,
                            source_path=source_path,
                            object_id=table_row_id,
                            locator=locator,
                        )
                    ],
                )
            )

        row_cells = table_cells_by_row.get((document.document_id, table_id, row_index), [])
        for cell in row_cells:
            column_index = _required_int(cell, "column_index", "table_cells", index)
            value = _optional_string(cell.get("value"))
            if value is None:
                continue
            header_value = _optional_string(cell.get("header_value")) or f"column_{column_index}"
            table_cell_id = _required_string(cell, "table_cell_id", "table_cells", index)
            values.append(
                SourceValue(
                    canonical_key=header_value,
                    value=value,
                    raw_label=header_value,
                    provenance=[
                        _provenance_ref(
                            source_kind="table_cell",
                            document_id=document.document_id,
                            source_path=source_path,
                            object_id=table_cell_id,
                            locator={**locator, "column_index": column_index},
                        )
                    ],
                )
            )

    return SourceRecord(
        record_id=table_row_id,
        document_id=document.document_id,
        source_path=source_path,
        values=values,
        table_id=table_id,
        locator=locator,
        raw=dict(record),
    )


def _table_cell_record_from_raw(
    record: JsonObject,
    *,
    documents_by_id: dict[str, SourceDocument],
    index: int,
) -> SourceRecord:
    component_name = "table_cells"
    document = _document_for_record(record, documents_by_id=documents_by_id, component_name=component_name, index=index)
    table_cell_id = _required_string(record, "table_cell_id", component_name, index)
    table_id = _required_string(record, "table_id", component_name, index)
    row_index = _required_int(record, "row_index", component_name, index)
    column_index = _required_int(record, "column_index", component_name, index)
    source_path = _optional_string(record.get("source_path")) or document.source_path
    header_value = _optional_string(record.get("header_value")) or f"column_{column_index}"
    value = _optional_string(record.get("value"))
    locator = {
        "page_anchor": _optional_string(record.get("page_anchor")),
        "table_id": table_id,
        "row_index": row_index,
        "column_index": column_index,
        "table_title": _optional_string(record.get("table_title")),
    }
    values: list[SourceValue] = []
    if value is not None:
        values.append(
            SourceValue(
                canonical_key=header_value,
                value=value,
                raw_label=header_value,
                provenance=[
                    _provenance_ref(
                        source_kind="table_cell",
                        document_id=document.document_id,
                        source_path=source_path,
                        object_id=table_cell_id,
                        locator=locator,
                    )
                ],
            )
        )

    return SourceRecord(
        record_id=table_cell_id,
        document_id=document.document_id,
        source_path=source_path,
        values=values,
        table_id=table_id,
        locator=locator,
        raw=dict(record),
    )


def _sheet_record_from_raw(
    record: JsonObject,
    *,
    documents_by_id: dict[str, SourceDocument],
    index: int,
) -> SourceRecord:
    component_name = "sheets"
    document = _document_for_record(record, documents_by_id=documents_by_id, component_name=component_name, index=index)
    sheet_id = _required_string(record, "sheet_id", component_name, index)
    source_path = _optional_string(record.get("source_path")) or document.source_path
    locator = {
        "sheet_id": sheet_id,
        "sheet_name": _optional_string(record.get("sheet_name")),
        "sheet_index": _optional_int(record.get("sheet_index")),
    }
    values: list[SourceValue] = []
    sheet_summary = _optional_string(record.get("sheet_summary"))
    if sheet_summary is not None:
        values.append(
            SourceValue(
                canonical_key="sheet_summary",
                value=sheet_summary,
                raw_label="sheet_summary",
                provenance=[
                    _provenance_ref(
                        source_kind="sheet",
                        document_id=document.document_id,
                        source_path=source_path,
                        object_id=sheet_id,
                        locator=locator,
                    )
                ],
            )
        )

    return SourceRecord(
        record_id=sheet_id,
        document_id=document.document_id,
        source_path=source_path,
        values=values,
        locator=locator,
        raw=dict(record),
    )


def _image_asset_from_raw(
    record: JsonObject,
    *,
    documents_by_id: dict[str, SourceDocument],
    bundle_dir: Path,
    image_block_context_by_asset_id: dict[str, JsonObject],
    index: int,
) -> SourceImageAsset:
    component_name = "visual_asset_inventory"
    document = _document_for_record(record, documents_by_id=documents_by_id, component_name=component_name, index=index)
    asset_id = _required_string(record, "asset_id", component_name, index)
    source_ref = _optional_string(record.get("source_ref"))
    source_checksum = _optional_string(record.get("source_checksum")) or document.source_checksum
    block_context = image_block_context_by_asset_id.get(asset_id, {})
    nearby_text_before = _text_context_list(record.get("nearby_text_before")) or _string_list(block_context.get("nearby_text_before"))
    nearby_text_after = _text_context_list(record.get("nearby_text_after")) or _string_list(block_context.get("nearby_text_after"))
    nearby_evidence_ids = _dedupe_strings(
        [
            *_string_list(block_context.get("nearby_evidence_ids")),
            *_string_list(record.get("related_evidence_ids")),
        ]
    )
    return SourceImageAsset(
        asset_id=asset_id,
        document_id=document.document_id,
        source_path=_optional_string(record.get("source_path")) or document.source_path,
        source_ref=source_ref,
        asset_path=_resolve_asset_path(
            bundle_dir=bundle_dir,
            raw_asset_path=_optional_string(record.get("asset_path")),
            source_ref=source_ref,
            source_checksum=source_checksum,
        ),
        asset_source=_optional_string(record.get("asset_source")),
        page_anchor=_optional_string(record.get("page_anchor")) or _optional_string(block_context.get("page_anchor")),
        bbox=record.get("bbox") if record.get("bbox") is not None else block_context.get("bbox"),
        block_id=_optional_string(block_context.get("block_id")),
        order_index=_optional_int(block_context.get("order_index")),
        sheet_name=_optional_string(record.get("sheet_name")),
        cell_anchor=_optional_string(record.get("cell_anchor")),
        row_index=_optional_int(record.get("row_index")),
        column_index=_optional_int(record.get("column_index")),
        related_evidence_ids=_string_list(record.get("related_evidence_ids")),
        nearby_text_before=nearby_text_before,
        nearby_text_after=nearby_text_after,
        nearby_evidence_ids=nearby_evidence_ids,
        raw=dict(record),
    )


def _diagnostic_from_raw(record: JsonObject, *, index: int) -> JsonObject:
    _required_string(record, "diagnostic_id", "diagnostics", index)
    return dict(record)


def _document_for_record(
    record: JsonObject,
    *,
    documents_by_id: dict[str, SourceDocument],
    component_name: str,
    index: int,
) -> SourceDocument:
    document_id = _required_string(record, "document_id", component_name, index)
    try:
        return documents_by_id[document_id]
    except KeyError as exc:
        raise SourceModelAdaptationError(
            f"{component_name}[{index}] references unknown document_id: {document_id}"
        ) from exc


def _cell_range_values(
    record: JsonObject,
    *,
    document_id: str,
    source_path: str,
    cell_range_id: str,
    locator: JsonObject,
) -> list[SourceValue]:
    parser_signals = _optional_object(record.get("parser_signals"))
    range_json = _optional_object(record.get("range_json"))
    headers = _string_list(parser_signals.get("header_values"))
    raw_values = _string_list(range_json.get("raw_values"), preserve_empty=True)
    non_empty_columns = set(_int_list(parser_signals.get("non_empty_columns")))
    column_count = max(len(headers), len(raw_values))
    values: list[SourceValue] = []

    for column_index in range(column_count):
        header = headers[column_index] if column_index < len(headers) and headers[column_index] else f"column_{column_index + 1}"
        raw_value = raw_values[column_index] if column_index < len(raw_values) else ""
        if not raw_value and non_empty_columns and (column_index + 1) not in non_empty_columns:
            continue
        if not raw_value and not non_empty_columns:
            continue
        values.append(
            SourceValue(
                canonical_key=header,
                value=raw_value,
                raw_label=header,
                provenance=[
                    _provenance_ref(
                        source_kind="cell_range",
                        document_id=document_id,
                        source_path=source_path,
                        object_id=cell_range_id,
                        locator={**locator, "column_index": column_index + 1},
                    )
                ],
            )
        )

    if values:
        return values

    range_text = _optional_string(record.get("range_text"))
    if range_text is None:
        return []

    return [
        SourceValue(
            canonical_key="range_text",
            value=range_text,
            raw_label="range_text",
            provenance=[
                _provenance_ref(
                    source_kind="cell_range",
                    document_id=document_id,
                    source_path=source_path,
                    object_id=cell_range_id,
                    locator=locator,
                )
            ],
        )
    ]


def _provenance_ref(
    *,
    source_kind: str,
    document_id: str,
    source_path: str,
    object_id: str,
    locator: JsonObject,
    evidence_id: str | None = None,
) -> ProvenanceRef:
    return ProvenanceRef(
        source_kind=source_kind,
        document_id=document_id,
        evidence_id=evidence_id,
        object_id=object_id,
        locator=dict(locator),
        source_path=source_path,
    )


def _resolve_asset_path(
    *,
    bundle_dir: Path,
    raw_asset_path: str | None,
    source_ref: str | None,
    source_checksum: str | None,
) -> str | None:
    if raw_asset_path is not None:
        return raw_asset_path
    if source_ref is None:
        return None

    ref_path = Path(source_ref).expanduser()
    if ref_path.is_absolute():
        return str(ref_path.resolve())

    parsed_checksum_candidate = bundle_dir / "parsed" / source_checksum / source_ref if source_checksum else None
    checksum_candidate = bundle_dir / source_checksum / source_ref if source_checksum else None
    bundle_candidate = bundle_dir / source_ref

    if parsed_checksum_candidate is not None and parsed_checksum_candidate.exists():
        return str(parsed_checksum_candidate.resolve())
    if checksum_candidate is not None and checksum_candidate.exists():
        return str(checksum_candidate.resolve())
    if bundle_candidate.exists():
        return str(bundle_candidate.resolve())
    if parsed_checksum_candidate is not None:
        return str(parsed_checksum_candidate)
    if checksum_candidate is not None:
        return str(checksum_candidate)
    return str(bundle_candidate)


def _table_text_from_cells(value: object) -> str | None:
    if not isinstance(value, list):
        return None

    row_texts: list[str] = []
    for row in value:
        if not isinstance(row, list):
            continue
        cell_values: list[str] = []
        for cell in row:
            if not isinstance(cell, dict):
                continue
            cell_values.append(_optional_string(cell.get("value")) or "")
        if cell_values:
            row_texts.append(" | ".join(cell_values))

    return "\n".join(row_texts) or None


def _table_cells_by_row(records: list[JsonObject]) -> dict[tuple[str, str, int], list[JsonObject]]:
    grouped: dict[tuple[str, str, int], list[JsonObject]] = {}
    for record in records:
        document_id = _optional_string(record.get("document_id"))
        table_id = _optional_string(record.get("table_id"))
        row_index = _optional_int(record.get("row_index"))
        if document_id is None or table_id is None or row_index is None:
            continue
        grouped.setdefault((document_id, table_id, row_index), []).append(record)
    return grouped


def _image_block_context_by_asset_id(records: list[JsonObject], *, window: int = 1) -> dict[str, JsonObject]:
    records_by_document: dict[str, list[JsonObject]] = {}
    for original_index, record in enumerate(records):
        document_id = _optional_string(record.get("document_id"))
        if document_id is None:
            continue
        indexed_record = dict(record)
        indexed_record["_source_order"] = original_index
        records_by_document.setdefault(document_id, []).append(indexed_record)

    context_by_asset_id: dict[str, JsonObject] = {}
    for document_records in records_by_document.values():
        ordered_records = sorted(
            document_records,
            key=lambda record: (
                _optional_int(record.get("order_index")) is None,
                _optional_int(record.get("order_index")) or 0,
                _optional_int(record.get("_source_order")) or 0,
            ),
        )
        for index, record in enumerate(ordered_records):
            asset_id = _optional_string(record.get("asset_id"))
            if asset_id is None:
                continue
            before_blocks = _nearby_text_blocks(ordered_records, index=index, direction=-1, window=window)
            after_blocks = _nearby_text_blocks(ordered_records, index=index, direction=1, window=window)
            context_by_asset_id[asset_id] = {
                "block_id": _optional_string(record.get("block_id")),
                "order_index": _optional_int(record.get("order_index")),
                "page_anchor": _optional_string(record.get("page_anchor")),
                "bbox": record.get("bbox"),
                "nearby_text_before": [
                    text
                    for block in before_blocks
                    for text in [_optional_string(block.get("source_text"))]
                    if text is not None
                ],
                "nearby_text_after": [
                    text
                    for block in after_blocks
                    for text in [_optional_string(block.get("source_text"))]
                    if text is not None
                ],
                "nearby_evidence_ids": _dedupe_strings(
                    [
                        *_string_list(record.get("evidence_ids")),
                        *[
                            evidence_id
                            for block in [*before_blocks, *after_blocks]
                            for evidence_id in _string_list(block.get("evidence_ids"))
                        ],
                    ]
                ),
            }
    return context_by_asset_id


def _nearby_text_blocks(
    records: list[JsonObject],
    *,
    index: int,
    direction: int,
    window: int,
) -> list[JsonObject]:
    image_record = records[index]
    page_anchor = _optional_string(image_record.get("page_anchor"))
    collected: list[JsonObject] = []
    cursor = index + direction
    while 0 <= cursor < len(records) and len(collected) < window:
        record = records[cursor]
        if _optional_string(record.get("document_id")) != _optional_string(image_record.get("document_id")):
            break
        if page_anchor is not None and _optional_string(record.get("page_anchor")) not in {None, page_anchor}:
            break
        text = _optional_string(record.get("source_text"))
        if text is not None:
            collected.append(record)
        cursor += direction
    if direction < 0:
        collected.reverse()
    return collected


def _text_context_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    return _string_list(value)


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _required_string(record: JsonObject, field_name: str, component_name: str, index: int) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        raise SourceModelAdaptationError(f"{component_name}[{index}] missing required field: {field_name}")
    return value


def _required_int(record: JsonObject, field_name: str, component_name: str, index: int) -> int:
    value = record.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SourceModelAdaptationError(f"{component_name}[{index}] missing required field: {field_name}")
    return value


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _optional_object(value: object) -> JsonObject:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _string_list(value: object, *, preserve_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        return []

    items: list[str] = []
    for item in value:
        if item is None:
            text = ""
        else:
            text = str(item)
        if text or preserve_empty:
            items.append(text)
    return items


def _int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int) and not isinstance(item, bool)]
