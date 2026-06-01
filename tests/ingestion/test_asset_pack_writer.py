from __future__ import annotations

import json
from pathlib import Path

from doctransai.data_layer import read_parsed_document_bundle
from doctransai.ingestion.asset_pack import write_asset_pack


def test_writes_minimal_asset_pack_that_data_layer_can_read(tmp_path: Path) -> None:
    block_record = {
        "contract_version": "data_asset_pack_v0",
        "block_id": "block-1",
        "document_id": "doc-1",
        "source_path": "/input/report.docx",
        "block_type": "paragraph",
        "page_anchor": "page:1",
        "bbox": None,
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
    source_record = {
        "contract_version": "data_asset_pack_v0",
        "document_id": "doc-1",
        "source_path": "/input/report.docx",
    }

    bundle_path = write_asset_pack(
        tmp_path,
        components={
            "block_inventory": [block_record],
            "source_manifest": [source_record],
        },
        documents=[{"document_id": "doc-1", "source_path": "/input/report.docx"}],
        capabilities={"mineru_document": True},
    )

    corpus = read_parsed_document_bundle(bundle_path)
    manifest = json.loads(bundle_path.read_text(encoding="utf-8"))

    assert manifest["bundle_type"] == "ParsedDocumentBundle"
    assert manifest["database_writes"] is False
    assert manifest["components"]["block_inventory"]["path"] == "block_inventory.jsonl"
    assert corpus.component_records("block_inventory") == [block_record]
    assert corpus.component_records("source_manifest") == [source_record]
