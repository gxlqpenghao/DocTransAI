from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import (
    ImagePlacement,
    OutputRef,
    PlanDiagnostic,
    RenderPlan,
    TargetRef,
    TemplateRef,
    TextFill,
    render_plan_to_dict,
)
from doctransai.models.source import ProvenanceRef


def test_render_plan_schema_validates_minimal_plan() -> None:
    plan = RenderPlan(
        plan_id="plan-schema",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/template.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/result.docx", output_format="docx"),
        text_fills=[
            TextFill(
                slot_id="slot-text",
                target=TargetRef(format_key="docx", target_kind="placeholder", paragraph_index=1, cell_paragraph_index=None),
                value="项目名称",
                provenance_refs=[
                    ProvenanceRef(
                        source_kind="evidence",
                        document_id="doc-1",
                        evidence_id="ev-1",
                        object_id="ev-1",
                        locator={"page_anchor": "page:1"},
                        source_path="/input.docx",
                    )
                ],
            )
        ],
        image_placements=[
            ImagePlacement(
                slot_id="slot-image",
                asset_id="asset-1",
                source_ref="final_images/image1.jpeg",
                target=TargetRef(
                    format_key="docx",
                    target_kind="image_placeholder",
                    paragraph_index=2,
                    cell_paragraph_index=None,
                    repeat_region_id="region-1",
                    instance_index=0,
                ),
                provenance_refs=[
                    ProvenanceRef(
                        source_kind="asset",
                        document_id="doc-1",
                        asset_id="asset-1",
                        object_id="asset-1",
                        locator={"page_anchor": "page:1"},
                        source_path="/input.docx",
                    )
                ],
            )
        ],
        unresolved_slots=[
            UnresolvedSlot(
                slot_id="slot-missing",
                canonical_key="整改期限",
                reason_code="missing_value",
                message="整改期限缺失",
                provenance_refs=[],
            )
        ],
        diagnostics=[
            PlanDiagnostic(
                severity="warning",
                code="missing_field",
                message="整改期限缺失",
            )
        ],
        created_at="2026-05-21T10:00:00Z",
    )

    schema_path = Path("contracts/doctransai/render_plan_v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(render_plan_to_dict(plan)), key=lambda error: list(error.path))

    assert errors == []


def test_render_plan_schema_accepts_legacy_v1_target_without_residual_fill_flag() -> None:
    plan = RenderPlan(
        plan_id="plan-schema-legacy",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/template.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/result.docx", output_format="docx"),
        text_fills=[
            TextFill(
                slot_id="slot-text",
                target=TargetRef(format_key="docx", target_kind="placeholder", paragraph_index=1),
                value="项目名称",
            )
        ],
        image_placements=[],
        unresolved_slots=[],
        diagnostics=[],
        created_at="2026-05-21T10:00:00Z",
    )
    payload = render_plan_to_dict(plan)
    del payload["text_fills"][0]["target"]["allow_same_name_residual_fill"]

    schema_path = Path("contracts/doctransai/render_plan_v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

    assert errors == []


def test_render_plan_v1_schema_rejects_multi_instance_v2_fields() -> None:
    plan = RenderPlan(
        plan_id="plan-schema-v1-guard",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/template.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/result.docx", output_format="docx"),
        text_fills=[],
        image_placements=[],
        unresolved_slots=[],
        diagnostics=[],
        created_at="2026-05-27T10:00:00Z",
    )
    payload = render_plan_to_dict(plan)
    payload["record_plans"] = [
        {
            "record_id": "record-1",
            "repeat_region_id": None,
            "slot_ids": [],
            "plan_unit_kind": "source_cluster",
            "source_cluster_id": "sheet:doc-1:Sheet0",
            "parent_plan_unit_id": None,
            "child_plan_unit_ids": ["region-1#0"],
        }
    ]

    schema_path = Path("contracts/doctransai/render_plan_v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

    assert any(
        error.validator == "additionalProperties"
        and list(error.path) == ["record_plans", 0]
        and "plan_unit_kind" in error.message
        and "source_cluster_id" in error.message
        for error in errors
    )


def test_render_plan_v1_schema_definition_has_no_v2_planning_fields() -> None:
    schema_path = Path("contracts/doctransai/render_plan_v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    forbidden_fields = {
        "plan_unit_id",
        "plan_unit_kind",
        "source_instance_id",
        "source_cluster_id",
        "parent_plan_unit_id",
        "child_plan_unit_ids",
    }

    assert _schema_property_names(schema).isdisjoint(forbidden_fields)


def _schema_property_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            names.update(str(key) for key in properties)
        for child in value.values():
            names.update(_schema_property_names(child))
    elif isinstance(value, list):
        for child in value:
            names.update(_schema_property_names(child))
    return names
