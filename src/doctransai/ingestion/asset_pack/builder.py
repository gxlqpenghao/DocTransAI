from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from doctransai.ingestion.asset_pack.constants import COMPONENT_FILENAMES, PARSED_DOCUMENT_BUNDLE_FILE
from doctransai.ingestion.asset_pack.manifest import build_parsed_document_bundle_manifest
from doctransai.ingestion.asset_pack.writers import write_json, write_jsonl


def write_asset_pack(
    output_dir: str | Path,
    *,
    components: Mapping[str, Sequence[dict[str, Any]]],
    documents: Sequence[dict[str, Any]] | None = None,
    parse_errors: Sequence[dict[str, Any]] | None = None,
    capabilities: Mapping[str, bool] | None = None,
    reports: Mapping[str, str] | None = None,
    issue_buckets: Mapping[str, Any] | None = None,
    summary: Mapping[str, int] | None = None,
) -> Path:
    target_dir = Path(output_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    component_paths: dict[str, str] = {}
    for component_name, records in components.items():
        filename = COMPONENT_FILENAMES.get(component_name, f"{component_name}.jsonl")
        write_jsonl(target_dir / filename, records)
        component_paths[component_name] = filename

    manifest = build_parsed_document_bundle_manifest(
        components=components,
        component_paths=component_paths,
        documents=documents,
        parse_errors=parse_errors,
        capabilities=capabilities,
        reports=reports,
        issue_buckets=issue_buckets,
        summary=summary,
    )
    return write_json(target_dir / PARSED_DOCUMENT_BUNDLE_FILE, manifest)
