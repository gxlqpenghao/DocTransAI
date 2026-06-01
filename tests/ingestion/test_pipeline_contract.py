from __future__ import annotations

from doctransai.ingestion.pipeline import fresh_asset_pack_stage_names


def test_fresh_asset_pack_pipeline_matches_dataproxy_mainline_order() -> None:
    stages = fresh_asset_pack_stage_names()

    assert stages[:3] == ("scan_file", "route_parser", "parse_source")
    assert stages.index("quality_gate") < stages.index("reload_repaired_artifact")
    assert stages.index("reload_repaired_artifact") < stages.index("normalize_artifact")
    assert stages.index("normalize_artifact") < stages.index("build_data_asset_rows")
    assert stages.index("build_visual_asset_inventory") < stages.index("link_evidence_visual_assets")
    assert stages.index("build_diagnostics") < stages.index("write_parsed_document_bundle")
    assert stages[-1] == "return_fresh_asset_pack_result"
