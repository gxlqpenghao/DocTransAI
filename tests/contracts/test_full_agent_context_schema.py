from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def test_full_agent_context_schema_accepts_minimal_complete_payload() -> None:
    payload = {
        "schema_version": "doctransai_full_agent_context_v1",
        "full_source_context": {
            "documents": [],
            "records": [],
            "image_assets": [],
            "diagnostics": [],
            "document_view": "",
            "record_count": 0,
            "image_asset_count": 0,
            "diagnostic_count": 0,
        },
        "full_template_context": {
            "template": {
                "template_id": "template-1",
                "template_path": "/templates/template.docx",
                "format_key": "docx",
                "analyzer_key": "p1b",
            },
            "slots": [],
            "repeat_regions": [],
            "header_regions": [],
            "diagnostics": [],
            "document_view": "",
            "visual_pages": [],
            "slot_count": 0,
            "repeat_region_count": 0,
            "header_region_count": 0,
        },
        "navigation_context": {
            "authority": "navigation_only_not_evidence",
            "source_instance_overview": None,
            "source_cluster_plan": None,
        },
        "task_context": {},
    }
    schema_path = Path("contracts/doctransai/full_agent_context_v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

    assert errors == []


def test_full_agent_context_schema_rejects_template_context_without_complete_views() -> None:
    payload = {
        "schema_version": "doctransai_full_agent_context_v1",
        "full_source_context": {
            "documents": [],
            "records": [],
            "image_assets": [],
            "diagnostics": [],
            "document_view": "",
            "record_count": 0,
            "image_asset_count": 0,
            "diagnostic_count": 0,
        },
        "full_template_context": {
            "template": None,
            "slots": [],
            "repeat_regions": [],
            "header_regions": [],
            "diagnostics": [],
            "slot_count": 0,
            "repeat_region_count": 0,
            "header_region_count": 0,
        },
        "navigation_context": {
            "authority": "navigation_only_not_evidence",
            "source_instance_overview": None,
            "source_cluster_plan": None,
        },
        "task_context": {},
    }
    schema_path = Path("contracts/doctransai/full_agent_context_v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

    assert {tuple(error.path) for error in errors} >= {
        ("full_template_context",),
    }


def test_full_agent_context_schema_rejects_malformed_object_index_entries() -> None:
    payload = {
        "schema_version": "doctransai_full_agent_context_v1",
        "full_source_context": {
            "documents": [],
            "records": [],
            "image_assets": [],
            "diagnostics": [],
            "document_view": "",
            "record_count": 0,
            "image_asset_count": 0,
            "diagnostic_count": 0,
            "object_index": {
                "by_object_key": {
                    "record:record-1": {
                        "object_kind": "record",
                        "object_id": "record-1",
                    }
                }
            },
        },
        "full_template_context": {
            "template": None,
            "slots": [],
            "repeat_regions": [],
            "header_regions": [],
            "diagnostics": [],
            "document_view": "",
            "visual_pages": [],
            "slot_count": 0,
            "repeat_region_count": 0,
            "header_region_count": 0,
        },
        "navigation_context": {
            "authority": "navigation_only_not_evidence",
            "source_instance_overview": None,
            "source_cluster_plan": None,
        },
        "task_context": {},
    }
    schema_path = Path("contracts/doctransai/full_agent_context_v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

    assert {tuple(error.path) for error in errors} >= {
        ("full_source_context", "object_index", "by_object_key", "record:record-1"),
    }
