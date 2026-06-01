from __future__ import annotations

from pathlib import Path

import pytest

from doctransai.data_layer import ComponentFile, SourceCorpus, read_parsed_document_bundle
from doctransai.models.source import SourceModel
from doctransai.source_model import AdaptedSourceModel, SourceModelAdaptationError, adapt_source_corpus


def _component(name: str, records: list[dict[str, object]]) -> ComponentFile:
    return ComponentFile(
        name=name,
        path=Path(f"/fixtures/{name}.jsonl"),
        count=len(records),
        records=records,
    )


def _build_corpus(
    tmp_path: Path,
    *,
    documents: list[dict[str, object]] | None = None,
    components: dict[str, list[dict[str, object]]] | None = None,
) -> SourceCorpus:
    bundle_path = (tmp_path / "bundle" / "parsed_document_bundle.json").resolve()
    component_records = components or {}
    return SourceCorpus(
        bundle_path=bundle_path,
        contract_version="data_asset_pack_v0",
        capabilities={name: True for name in component_records},
        summary={"document_count": len(documents or [])},
        documents=list(documents or []),
        parse_errors=[],
        components={name: _component(name, records) for name, records in component_records.items()},
        reports={},
        raw_manifest={},
    )


def test_adapts_source_corpus_into_typed_source_model(tmp_path: Path) -> None:
    checksum = "abc123"
    corpus = _build_corpus(
        tmp_path,
        documents=[
            {
                "document_id": "doc-1",
                "source_path": "/input/report.xlsx",
                "parser_name": "excel_native",
                "evidence_count": 1,
            }
        ],
        components={
            "source_manifest": [
                {
                    "document_id": "doc-1",
                    "source_path": "/input/report.xlsx",
                    "source_checksum": checksum,
                    "doc_type": "spreadsheet",
                    "document_title": "安全检查台账",
                }
            ],
            "evidence_units": [
                {
                    "document_id": "doc-1",
                    "evidence_id": "ev-1",
                    "source_path": "/input/report.xlsx",
                    "source_checksum": checksum,
                    "locator": {
                        "sheet_id": "sheet-1",
                        "sheet_name": "Sheet0",
                        "cell_range_id": "range-2",
                        "cell_range": "A3:C3",
                        "table_id": None,
                    },
                    "text": "Sheet=Sheet0 | Range=A3:C3 | 项目名称=项目A | 隐患描述=临边防护缺失",
                    "asset_refs": ["asset-1"],
                    "modality": "table",
                    "object_id": "range-2",
                    "object_type": "cell_range",
                }
            ],
            "table_units": [
                {
                    "document_id": "doc-1",
                    "table_id": "tbl-1",
                    "source_path": "/input/report.xlsx",
                    "page_anchor": None,
                    "section_id": None,
                    "table_identity": {
                        "identity_status": "implicit",
                        "locator_summary": "Sheet0 / table 1",
                    },
                    "table_json": {
                        "body_text": "项目名称 | 隐患描述\n项目A | 临边防护缺失",
                        "cells": [
                            [
                                {"row_index": 1, "column_index": 1, "value": "项目名称"},
                                {"row_index": 1, "column_index": 2, "value": "隐患描述"},
                            ],
                            [
                                {"row_index": 2, "column_index": 1, "value": "项目A"},
                                {"row_index": 2, "column_index": 2, "value": "临边防护缺失"},
                            ],
                        ],
                    },
                }
            ],
            "cell_ranges": [
                {
                    "document_id": "doc-1",
                    "cell_range_id": "range-1",
                    "source_path": "/input/report.xlsx",
                    "sheet_id": "sheet-1",
                    "sheet_name": "Sheet0",
                    "range_ref": "A2:C2",
                    "range_type": "cell_range",
                    "range_text": "Sheet=Sheet0 | Range=A2:C2 | Headers=项目名称 | 隐患描述 | 责任单位",
                    "range_json": {"raw_values": ["项目名称", "隐患描述", "责任单位"]},
                    "parser_signals": {
                        "header_values": ["项目名称", "隐患描述", "责任单位"],
                        "non_empty_columns": [1, 2, 3],
                        "row_index": 2,
                    },
                },
                {
                    "document_id": "doc-1",
                    "cell_range_id": "range-2",
                    "source_path": "/input/report.xlsx",
                    "sheet_id": "sheet-1",
                    "sheet_name": "Sheet0",
                    "range_ref": "A3:C3",
                    "range_type": "cell_range",
                    "range_text": "Sheet=Sheet0 | Range=A3:C3 | 项目名称=项目A | 隐患描述=临边防护缺失 | 责任单位=施工单位A",
                    "range_json": {"raw_values": ["项目A", "临边防护缺失", "施工单位A"]},
                    "parser_signals": {
                        "header_values": ["项目名称", "隐患描述", "责任单位"],
                        "non_empty_columns": [1, 2, 3],
                        "row_index": 3,
                    },
                },
            ],
            "sheets": [
                {
                    "document_id": "doc-1",
                    "sheet_id": "sheet-1",
                    "sheet_index": 0,
                    "sheet_name": "Sheet0",
                    "sheet_summary": "Sheet=Sheet0 | Range=A2:C3 | Headers=[项目名称, 隐患描述, 责任单位]",
                    "parser_signals": {"preview_range": "A2:C3"},
                    "source_path": "/input/report.xlsx",
                }
            ],
            "visual_asset_inventory": [
                {
                    "document_id": "doc-1",
                    "asset_id": "asset-1",
                    "source_path": "/input/report.xlsx",
                    "source_ref": "final_images/asset-1.jpeg",
                    "cell_anchor": "K3",
                    "row_index": 3,
                    "column_index": 11,
                    "sheet_name": "Sheet0",
                    "related_evidence_ids": ["ev-1"],
                }
            ],
            "diagnostics": [
                {
                    "diagnostic_id": "diag-1",
                    "severity": "info",
                    "code": "weak_caption",
                    "message": "Visual asset caption is missing or generic.",
                }
            ],
        },
    )

    model = adapt_source_corpus(corpus)

    assert isinstance(model, SourceModel)
    assert isinstance(model, AdaptedSourceModel)
    assert model.documents_by_id["doc-1"].source_checksum == checksum
    assert model.documents_by_id["doc-1"].raw["parser_name"] == "excel_native"
    assert len(model.records) == 5
    assert list(model.evidence_by_id) == ["ev-1"]
    assert list(model.tables_by_id) == ["tbl-1"]
    assert list(model.cell_ranges_by_id) == ["range-1", "range-2"]
    assert list(model.sheets_by_id) == ["sheet-1"]
    assert list(model.image_assets_by_id) == ["asset-1"]
    assert list(model.diagnostics_by_id) == ["diag-1"]

    row_record = model.cell_ranges_by_id["range-2"]
    row_values = {value.canonical_key: value.value for value in row_record.values}
    assert row_values == {
        "项目名称": "项目A",
        "隐患描述": "临边防护缺失",
        "责任单位": "施工单位A",
    }
    assert row_record.values[0].provenance[0].source_kind == "cell_range"
    assert row_record.values[0].provenance[0].object_id == "range-2"

    table_record = model.tables_by_id["tbl-1"]
    assert table_record.values[0].canonical_key == "table_text"
    assert "项目A" in table_record.values[0].value

    asset = model.image_assets_by_id["asset-1"]
    assert asset.asset_path == str(corpus.bundle_path.parent / "parsed" / checksum / "final_images/asset-1.jpeg")
    assert asset.related_evidence_ids == ["ev-1"]


def test_missing_optional_components_return_empty_collections(tmp_path: Path) -> None:
    corpus = _build_corpus(
        tmp_path,
        documents=[{"document_id": "doc-1", "source_path": "/input/report.docx"}],
        components={
            "source_manifest": [
                {
                    "document_id": "doc-1",
                    "source_path": "/input/report.docx",
                    "doc_type": "document",
                    "document_title": "检查通报",
                    "source_checksum": "doc-checksum",
                }
            ]
        },
    )

    model = adapt_source_corpus(corpus)

    assert model.documents_by_id["doc-1"].document_title == "检查通报"
    assert model.evidence_records == []
    assert model.table_records == []
    assert model.cell_range_records == []
    assert model.xlsx_row_records == []
    assert model.sheet_records == []
    assert model.image_assets == []
    assert model.diagnostics == []
    assert model.records == []


def test_adapts_visual_assets_with_nearby_block_context(tmp_path: Path) -> None:
    corpus = _build_corpus(
        tmp_path,
        documents=[
            {
                "document_id": "doc-1",
                "source_path": "/input/report.doc",
                "parser_name": "mineru",
            }
        ],
        components={
            "source_manifest": [
                {
                    "document_id": "doc-1",
                    "source_path": "/input/report.doc",
                    "source_checksum": "checksum-1",
                    "doc_type": "document",
                    "document_title": "检查通报",
                }
            ],
            "visual_asset_inventory": [
                {
                    "document_id": "doc-1",
                    "asset_id": "img-1",
                    "asset_source": "mineru",
                    "source_path": "/input/report.doc",
                    "source_ref": "images/img-1.jpg",
                    "page_anchor": "page_1",
                    "related_evidence_ids": [],
                }
            ],
            "block_inventory": [
                {
                    "document_id": "doc-1",
                    "block_id": "blk-before",
                    "block_type": "paragraph",
                    "order_index": 1,
                    "page_anchor": "page_1",
                    "source_text": "附件:",
                    "evidence_ids": ["ev-1"],
                },
                {
                    "document_id": "doc-1",
                    "block_id": "blk-image",
                    "block_type": "image",
                    "asset_id": "img-1",
                    "order_index": 2,
                    "page_anchor": "page_1",
                    "source_text": "",
                    "evidence_ids": [],
                },
                {
                    "document_id": "doc-1",
                    "block_id": "blk-after",
                    "block_type": "paragraph",
                    "order_index": 3,
                    "page_anchor": "page_1",
                    "source_text": "二工区围挡未及时封闭",
                    "evidence_ids": ["ev-1"],
                },
            ],
        },
    )

    model = adapt_source_corpus(corpus)
    asset = model.image_assets_by_id["img-1"]

    assert asset.document_id == "doc-1"
    assert asset.source_path == "/input/report.doc"
    assert asset.asset_source == "mineru"
    assert asset.page_anchor == "page_1"
    assert asset.block_id == "blk-image"
    assert asset.order_index == 2
    assert asset.nearby_text_before == ["附件:"]
    assert asset.nearby_text_after == ["二工区围挡未及时封闭"]
    assert asset.nearby_evidence_ids == ["ev-1"]


def test_adapts_table_granularity_sidecars_into_row_and_cell_records(tmp_path: Path) -> None:
    corpus = _build_corpus(
        tmp_path,
        documents=[
            {
                "document_id": "doc-1",
                "source_path": "/input/report.docx",
                "parser_name": "mineru",
            }
        ],
        components={
            "source_manifest": [
                {
                    "document_id": "doc-1",
                    "source_path": "/input/report.docx",
                    "source_checksum": "checksum-1",
                    "doc_type": "document",
                    "document_title": "检查记录表",
                }
            ],
            "table_rows": [
                {
                    "document_id": "doc-1",
                    "source_path": "/input/report.docx",
                    "table_row_id": "tblrow-1",
                    "table_id": "tbl-1",
                    "table_title": "检查记录表",
                    "page_anchor": "page_1",
                    "row_index": 1,
                    "is_header": True,
                    "cells": ["项目名称", "隐患描述"],
                    "row_text": "项目名称 | 隐患描述",
                    "quality": {"issues": []},
                },
                {
                    "document_id": "doc-1",
                    "source_path": "/input/report.docx",
                    "table_row_id": "tblrow-2",
                    "table_id": "tbl-1",
                    "table_title": "检查记录表",
                    "page_anchor": "page_1",
                    "row_index": 2,
                    "is_header": False,
                    "cells": ["项目A", "临边防护缺失"],
                    "row_text": "项目名称=项目A | 隐患描述=临边防护缺失",
                    "quality": {"issues": []},
                },
            ],
            "table_cells": [
                {
                    "document_id": "doc-1",
                    "source_path": "/input/report.docx",
                    "table_cell_id": "tblcell-1",
                    "table_id": "tbl-1",
                    "table_title": "检查记录表",
                    "page_anchor": "page_1",
                    "row_index": 2,
                    "column_index": 1,
                    "header_value": "项目名称",
                    "value": "项目A",
                    "is_header": False,
                    "quality": {"issues": []},
                },
                {
                    "document_id": "doc-1",
                    "source_path": "/input/report.docx",
                    "table_cell_id": "tblcell-2",
                    "table_id": "tbl-1",
                    "table_title": "检查记录表",
                    "page_anchor": "page_1",
                    "row_index": 2,
                    "column_index": 2,
                    "header_value": "隐患描述",
                    "value": "临边防护缺失",
                    "is_header": False,
                    "quality": {"issues": []},
                },
            ],
        },
    )

    model = adapt_source_corpus(corpus)

    assert [record.record_id for record in model.table_row_records] == ["tblrow-1", "tblrow-2"]
    assert [record.record_id for record in model.table_cell_records] == ["tblcell-1", "tblcell-2"]

    header_row = model.table_row_records[0]
    assert header_row.values == []

    data_row = model.table_row_records[1]
    data_values = {value.canonical_key: value.value for value in data_row.values}
    assert data_values == {
        "row_text": "项目名称=项目A | 隐患描述=临边防护缺失",
        "项目名称": "项目A",
        "隐患描述": "临边防护缺失",
    }
    assert data_row.locator["row_index"] == 2
    assert data_row.locator["table_id"] == "tbl-1"
    assert data_row.values[1].provenance[0].source_kind == "table_cell"


@pytest.mark.parametrize(
    ("component_name", "record", "expected_message"),
    [
        (
            "source_manifest",
            {"source_path": "/input/report.docx", "source_checksum": "checksum"},
            "source_manifest[0] missing required field: document_id",
        ),
        (
            "evidence_units",
            {"document_id": "doc-1", "source_path": "/input/report.docx"},
            "evidence_units[0] missing required field: evidence_id",
        ),
        (
            "table_units",
            {"document_id": "doc-1", "source_path": "/input/report.docx"},
            "table_units[0] missing required field: table_id",
        ),
        (
            "cell_ranges",
            {"document_id": "doc-1", "source_path": "/input/report.xlsx", "sheet_id": "sheet-1"},
            "cell_ranges[0] missing required field: cell_range_id",
        ),
        (
            "sheets",
            {"document_id": "doc-1", "source_path": "/input/report.xlsx"},
            "sheets[0] missing required field: sheet_id",
        ),
        (
            "visual_asset_inventory",
            {"document_id": "doc-1", "source_path": "/input/report.xlsx", "source_ref": "final_images/a.jpeg"},
            "visual_asset_inventory[0] missing required field: asset_id",
        ),
        (
            "diagnostics",
            {"severity": "info", "code": "weak_caption"},
            "diagnostics[0] missing required field: diagnostic_id",
        ),
    ],
)
def test_missing_required_ids_raise_clear_errors(
    tmp_path: Path,
    component_name: str,
    record: dict[str, object],
    expected_message: str,
) -> None:
    components = {
        "source_manifest": [
            {
                "document_id": "doc-1",
                "source_path": "/input/report.xlsx",
                "doc_type": "spreadsheet",
                "document_title": "安全检查台账",
                "source_checksum": "abc123",
            }
        ]
    }
    components[component_name] = [record]
    if component_name == "source_manifest":
        components = {"source_manifest": [record]}

    corpus = _build_corpus(
        tmp_path,
        documents=[{"document_id": "doc-1", "source_path": "/input/report.xlsx"}],
        components=components,
    )

    with pytest.raises(SourceModelAdaptationError) as exc_info:
        adapt_source_corpus(corpus)

    assert str(exc_info.value) == expected_message


def test_smoke_adapts_real_dataproxy_bundle() -> None:
    corpus = read_parsed_document_bundle("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json")

    model = adapt_source_corpus(corpus)

    assert len(model.documents) == 4
    assert len(model.evidence_records) == 17
    assert len(model.table_records) == 2
    assert len(model.cell_range_records) == 11
    assert len(model.xlsx_row_records) == 11
    assert len(model.sheet_records) == 1
    assert len(model.image_assets) == 25
    assert len(model.diagnostics) == 29

    row_record = model.cell_ranges_by_id["range_605716d22b9e"]
    row_values = {value.canonical_key: value.value for value in row_record.values}
    assert row_values["项目名称"] == "西香TJ3标"
    assert row_values["隐患描述"].startswith("右幅作业人员安全带")

    asset = model.image_assets_by_id["sheet1_image1"]
    assert asset.source_ref == "final_images/sheet1_image1.jpeg"
    assert asset.asset_path.endswith(
        "/parsed/8d6aaab22bd9dfe7c310a0b619331bc537ebe324f2d1bd145f0dd83690684cde/final_images/sheet1_image1.jpeg"
    )
