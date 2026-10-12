from __future__ import annotations

CONTRACT_VERSION = "data_asset_pack_v0"
PARSED_DOCUMENT_BUNDLE_FILE = "parsed_document_bundle.json"

COMPONENT_FILENAMES: dict[str, str] = {
    "evidence_units": "evidence_units.jsonl",
    "table_units": "table_units.jsonl",
    "section_units": "section_units.jsonl",
    "source_manifest": "source_manifest.jsonl",
    "block_inventory": "block_inventory.jsonl",
    "sheets": "sheets.jsonl",
    "cell_ranges": "cell_ranges.jsonl",
    "visual_asset_inventory": "visual_asset_inventory.jsonl",
    "diagnostics": "diagnostics.jsonl",
    "qa_seed_pack": "qa_seed_pack.jsonl",
}
