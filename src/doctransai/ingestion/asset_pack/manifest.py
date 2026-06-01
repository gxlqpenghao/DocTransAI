from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from doctransai.ingestion.asset_pack.constants import CONTRACT_VERSION


def build_parsed_document_bundle_manifest(
    *,
    components: Mapping[str, Sequence[dict[str, Any]]],
    component_paths: Mapping[str, str],
    documents: Sequence[dict[str, Any]] | None = None,
    parse_errors: Sequence[dict[str, Any]] | None = None,
    capabilities: Mapping[str, bool] | None = None,
    reports: Mapping[str, str] | None = None,
    issue_buckets: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
    summary: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    component_descriptors = {
        name: {"count": len(records), "path": component_paths[name]}
        for name, records in components.items()
    }
    derived_summary = {
        "document_count": len(documents or []),
        "parse_error_count": len(parse_errors or []),
    }
    for name, records in components.items():
        derived_summary[_summary_key_for_component(name)] = len(records)
    if summary:
        derived_summary.update(summary)

    return {
        "bundle_type": "ParsedDocumentBundle",
        "contract_version": CONTRACT_VERSION,
        "database_writes": False,
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "capabilities": dict(capabilities or {}),
        "components": component_descriptors,
        "summary": derived_summary,
        "reports": dict(reports or {}),
        "issue_buckets": dict(issue_buckets or {}),
        "documents": list(documents or []),
        "parse_errors": list(parse_errors or []),
    }


def _summary_key_for_component(component_name: str) -> str:
    if component_name.endswith("_inventory"):
        base = component_name[: -len("_inventory")]
    elif component_name.endswith("_units"):
        base = component_name[: -len("_units")]
    else:
        base = component_name
    return f"{base}_count"
