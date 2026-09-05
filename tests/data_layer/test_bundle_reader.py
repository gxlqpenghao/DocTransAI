from __future__ import annotations

import json
from pathlib import Path

import pytest

from doctransai.data_layer import BundleValidationError, read_parsed_document_bundle
from doctransai.data_layer.schema_validation import schema_for_component


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    payload = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    path.write_text(payload, encoding="utf-8")


def test_reads_minimal_bundle_and_resolves_sidecars(tmp_path: Path) -> None:
    block_record = {
        "contract_version": "data_asset_pack_v0",
        "block_id": "block-1",
        "document_id": "doc-1",
        "source_path": "/input/report.docx",
        "block_type": "paragraph",
        "page_anchor": "page:1",
        "bbox": [1, 2, 3, 4],
        "sheet_name": None,
        "range_ref": None,
        "order_index": 0,
        "section_id": None,
        "table_id": None,
        "sheet_id": None,
        "cell_range_id": None,
        "evidence_ids": ["ev-1"],
        "asset_id": None,
        "parser_name": "fixture",
        "parser_signals": {},
        "source_text": "隐患描述",
        "quality": {"issues": []},
    }
    diagnostic_record = {
        "contract_version": "data_asset_pack_v0",
        "diagnostic_id": "diag-1",
        "diagnostic_class": "quality_gate",
        "code": "fixture",
        "severity": "info",
        "phase": "fixture",
        "source_path": "/input/report.docx",
        "document_id": "doc-1",
        "block_id": "block-1",
        "evidence_id": None,
        "table_id": None,
        "asset_id": None,
        "sheet_id": None,
        "cell_range_id": None,
        "page_anchor": "page:1",
        "bbox": None,
        "sheet_name": None,
        "range_ref": None,
        "remediation_eligible": False,
        "remediation_executed": False,
        "residual": False,
        "producer": "fixture",
        "message": None,
        "field": None,
    }
    source_record = {
        "contract_version": "data_asset_pack_v0",
        "document_id": "doc-1",
        "source_path": "/input/report.docx",
    }

    _write_jsonl(tmp_path / "block_inventory.jsonl", [block_record])
    _write_jsonl(tmp_path / "diagnostics.jsonl", [diagnostic_record])
    _write_jsonl(tmp_path / "source_manifest.jsonl", [source_record])
    _write_json(tmp_path / "data_quality_report.json", {"ok": True})
    _write_json(
        tmp_path / "parsed_document_bundle.json",
        {
            "bundle_type": "ParsedDocumentBundle",
            "contract_version": "data_asset_pack_v0",
            "database_writes": False,
            "generated_at": "2026-05-21T00:00:00Z",
            "capabilities": {"block_inventory": True, "diagnostics": True},
            "components": {
                "block_inventory": {"count": 1, "path": "block_inventory.jsonl"},
                "diagnostics": {"count": 1, "path": "diagnostics.jsonl"},
                "source_manifest": {"count": 1, "path": "source_manifest.jsonl"},
            },
            "summary": {"document_count": 1, "block_count": 1, "diagnostic_count": 1},
            "reports": {"data_quality": "data_quality_report.json"},
            "issue_buckets": {},
            "documents": [{"document_id": "doc-1", "source_path": "/input/report.docx"}],
            "parse_errors": [],
        },
    )

    corpus = read_parsed_document_bundle(tmp_path / "parsed_document_bundle.json")

    assert corpus.contract_version == "data_asset_pack_v0"
    assert corpus.summary["block_count"] == 1
    assert corpus.component_records("block_inventory") == [block_record]
    assert corpus.component_records("source_manifest") == [source_record]
    assert corpus.reports["data_quality"] == tmp_path / "data_quality_report.json"
    assert corpus.component("block_inventory").path == tmp_path / "block_inventory.jsonl"


def test_reads_bundle_with_float_summary_metrics_from_upstream(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "parsed_document_bundle.json",
        {
            "bundle_type": "ParsedDocumentBundle",
            "contract_version": "data_asset_pack_v0",
            "database_writes": False,
            "generated_at": "2026-05-25T00:00:00Z",
            "capabilities": {},
            "components": {},
            "summary": {
                "document_count": 1,
                "qa_seed_llm_review_elapsed_seconds": 0.0002,
            },
            "reports": {},
            "issue_buckets": {},
            "documents": [{"document_id": "doc-1", "source_path": "/input/report.pdf"}],
            "parse_errors": [],
        },
    )

    corpus = read_parsed_document_bundle(tmp_path / "parsed_document_bundle.json")

    assert corpus.summary["document_count"] == 1
    assert corpus.summary["qa_seed_llm_review_elapsed_seconds"] == 0.0002


def test_reads_table_granularity_sidecars_when_present(tmp_path: Path) -> None:
    table_row_record = {
        "contract_version": "data_asset_pack_v0",
        "table_row_id": "tblrow-1",
        "document_id": "doc-1",
        "source_path": "/input/report.docx",
        "table_id": "tbl-1",
        "table_title": "检查记录表",
        "page_anchor": "page:1",
        "row_index": 2,
        "is_header": False,
        "cells": ["项目A", "临边防护缺失"],
        "row_text": "项目名称=项目A | 隐患描述=临边防护缺失",
        "quality": {"issues": []},
    }
    table_cell_record = {
        "contract_version": "data_asset_pack_v0",
        "table_cell_id": "tblcell-1",
        "document_id": "doc-1",
        "source_path": "/input/report.docx",
        "table_id": "tbl-1",
        "table_title": "检查记录表",
        "page_anchor": "page:1",
        "row_index": 2,
        "column_index": 1,
        "header_value": "项目名称",
        "value": "项目A",
        "is_header": False,
        "quality": {"issues": []},
    }

    _write_jsonl(tmp_path / "table_rows.jsonl", [table_row_record])
    _write_jsonl(tmp_path / "table_cells.jsonl", [table_cell_record])
    _write_json(
        tmp_path / "parsed_document_bundle.json",
        {
            "bundle_type": "ParsedDocumentBundle",
            "contract_version": "data_asset_pack_v0",
            "database_writes": False,
            "generated_at": "2026-05-21T00:00:00Z",
            "capabilities": {"table_granularity_inventory": True},
            "components": {
                "table_rows": {"count": 1, "path": "table_rows.jsonl"},
                "table_cells": {"count": 1, "path": "table_cells.jsonl"},
            },
            "summary": {"document_count": 1, "table_row_count": 1, "table_cell_count": 1},
            "reports": {},
            "issue_buckets": {},
            "documents": [{"document_id": "doc-1", "source_path": "/input/report.docx"}],
            "parse_errors": [],
        },
    )

    corpus = read_parsed_document_bundle(tmp_path / "parsed_document_bundle.json")

    assert corpus.table_rows == [table_row_record]
    assert corpus.table_cells == [table_cell_record]


def test_ignores_qa_seed_pack_by_default_even_if_manifest_lists_it(tmp_path: Path) -> None:
    qa_seed_record = {
        "contract_version": "data_asset_pack_v0",
        "qa_id": "qa-1",
        "question": "示例问题",
        "answer": "示例答案",
        "evidence_ids": ["ev-1"],
        "asset_refs": [],
        "locator": {},
        "source_path": "/input/report.docx",
        "qa_type": "table_cell",
        "requires_visual_context": False,
        "generator": "dataproxy",
        "validation": {
            "grounded": True,
            "answer_supported_by_evidence": True,
            "locator_resolvable": True,
            "issues": [],
        },
        "review_status": "unreviewed",
    }
    source_record = {
        "contract_version": "data_asset_pack_v0",
        "document_id": "doc-1",
        "source_path": "/input/report.docx",
    }

    _write_jsonl(tmp_path / "qa_seed_pack.jsonl", [qa_seed_record])
    _write_jsonl(tmp_path / "source_manifest.jsonl", [source_record])
    _write_json(
        tmp_path / "parsed_document_bundle.json",
        {
            "bundle_type": "ParsedDocumentBundle",
            "contract_version": "data_asset_pack_v0",
            "database_writes": False,
            "generated_at": "2026-05-21T00:00:00Z",
            "capabilities": {"qa_seed_pack": True},
            "components": {
                "qa_seed_pack": {"count": 1, "path": "qa_seed_pack.jsonl"},
                "source_manifest": {"count": 1, "path": "source_manifest.jsonl"},
            },
            "summary": {"document_count": 1, "qa_seed_count": 1},
            "reports": {},
            "issue_buckets": {},
            "documents": [{"document_id": "doc-1", "source_path": "/input/report.docx"}],
            "parse_errors": [],
        },
    )

    corpus = read_parsed_document_bundle(tmp_path / "parsed_document_bundle.json")

    assert "qa_seed_pack" not in corpus.components
    assert corpus.source_manifest == [source_record]


def test_schema_validation_reports_component_and_record_index(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "block_inventory.jsonl",
        [{"contract_version": "data_asset_pack_v0", "block_id": "missing-required-fields"}],
    )
    _write_json(
        tmp_path / "parsed_document_bundle.json",
        {
            "bundle_type": "ParsedDocumentBundle",
            "contract_version": "data_asset_pack_v0",
            "database_writes": False,
            "generated_at": "2026-05-21T00:00:00Z",
            "capabilities": {"block_inventory": True},
            "components": {"block_inventory": {"count": 1, "path": "block_inventory.jsonl"}},
            "summary": {"document_count": 1},
            "reports": {},
            "issue_buckets": {},
            "documents": [{"document_id": "doc-1"}],
            "parse_errors": [],
        },
    )

    with pytest.raises(BundleValidationError) as exc_info:
        read_parsed_document_bundle(tmp_path / "parsed_document_bundle.json")

    assert "block_inventory[0]" in str(exc_info.value)


def test_knows_local_schema_snapshot_for_supported_components() -> None:
    assert schema_for_component("parsed_document_bundle").name == "parsed_document_bundle.schema.json"
    assert schema_for_component("block_inventory").name == "block_inventory.schema.json"
    assert schema_for_component("table_rows").name == "table_rows.schema.json"
    assert schema_for_component("table_cells").name == "table_cells.schema.json"
    assert schema_for_component("source_manifest") is None


def test_known_schema_missing_fails_closed(tmp_path, monkeypatch):
    from doctransai.data_layer import schema_validation

    monkeypatch.setattr(schema_validation, "schema_root", lambda: tmp_path)
    with pytest.raises(FileNotFoundError, match="Missing DataProxy contract schema"):
        schema_validation.validate_instance("parsed_document_bundle", {})
    assert schema_validation.schema_for_component("source_manifest") is None
