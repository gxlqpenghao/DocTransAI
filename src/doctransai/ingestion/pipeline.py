from __future__ import annotations


FRESH_ASSET_PACK_STAGES: tuple[str, ...] = (
    "scan_file",
    "route_parser",
    "parse_source",
    "enrich_mineru_paired_validation",
    "resolve_asset_base_dir",
    "quality_gate",
    "reload_repaired_artifact",
    "normalize_artifact",
    "build_data_asset_rows",
    "build_visual_asset_inventory",
    "link_evidence_visual_assets",
    "build_block_inventory",
    "build_sheet_inventory",
    "build_cell_range_inventory",
    "append_document_summary",
    "write_core_sidecars",
    "build_qa_seed_outputs",
    "build_data_quality_report",
    "write_data_quality_report",
    "build_visual_quality_report",
    "write_visual_quality_report",
    "build_fresh_validation_report",
    "build_diagnostics",
    "write_diagnostics",
    "build_parsed_document_bundle_manifest",
    "write_parsed_document_bundle",
    "write_fresh_validation_report",
    "return_fresh_asset_pack_result",
)


def fresh_asset_pack_stage_names() -> tuple[str, ...]:
    return FRESH_ASSET_PACK_STAGES
