from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from doctransai.data_layer.bundle_reader import read_parsed_document_bundle
from doctransai.mapping.planner import build_render_plan
from doctransai.models.render_plan import render_plan_from_dict
from doctransai.models.template import SlotAddress, TemplateModel, TemplateSlot
from doctransai.source_model.adapter import adapt_source_corpus


def _synthetic_template_model() -> TemplateModel:
    return TemplateModel(
        template_id="synthetic-docx",
        template_path="/templates/synthetic.docx",
        format_key="docx",
        analyzer_key="synthetic",
        slots=[
            TemplateSlot(
                slot_id="slot-project",
                raw_name="项目名称",
                canonical_name="项目名称",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=0),
            ),
            TemplateSlot(
                slot_id="slot-desc",
                raw_name="隐患描述",
                canonical_name="隐患描述",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=1),
            ),
            TemplateSlot(
                slot_id="slot-demand",
                raw_name="整改要求",
                canonical_name="整改要求",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=2),
            ),
            TemplateSlot(
                slot_id="slot-owner",
                raw_name="整改责任人",
                canonical_name="整改责任人",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=3),
            ),
            TemplateSlot(
                slot_id="slot-hazard-photo",
                raw_name="隐患照片",
                canonical_name="隐患照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=4),
            ),
            TemplateSlot(
                slot_id="slot-fix-photo",
                raw_name="整改照片",
                canonical_name="整改照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=5),
            ),
            TemplateSlot(
                slot_id="slot-review-photo",
                raw_name="复查照片",
                canonical_name="复查照片",
                slot_kind="image",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=6),
            ),
            TemplateSlot(
                slot_id="slot-missing-lead",
                raw_name="责任单位负责人",
                canonical_name="责任单位负责人",
                slot_kind="text",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=7),
            ),
        ],
    )


def test_build_render_plan_from_real_dataproxy_bundle_without_writing_output(tmp_path: Path) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json")
    corpus = read_parsed_document_bundle(bundle_path)
    source_model = adapt_source_corpus(corpus)
    primary_record = next(
        record
        for record in source_model.cell_range_records
        if record.locator.get("sheet_name") == "Sheet0" and record.locator.get("row_index") == 6
    )
    output_path = tmp_path / "outputs" / "result.docx"

    payload = build_render_plan(
        template_model=_synthetic_template_model(),
        source_model=source_model,
        source_bundle_path=str(bundle_path.resolve()),
        output_path=str(output_path),
        primary_record_id=primary_record.record_id,
        plan_id="bundle-plan",
        created_at="2026-05-21T13:00:00Z",
    )

    plan = render_plan_from_dict(payload)
    text_by_slot = {fill.slot_id: fill.value for fill in plan.text_fills}
    image_by_slot = {placement.slot_id: placement for placement in plan.image_placements}
    unresolved_by_slot = {slot.slot_id: slot for slot in plan.unresolved_slots}

    schema = json.loads(Path("contracts/doctransai/render_plan_v1.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda error: list(error.path))

    assert errors == []
    assert output_path.exists() is False
    assert text_by_slot["slot-project"] == "西香TJ3标"
    assert text_by_slot["slot-desc"] == "电线杂乱"
    assert text_by_slot["slot-demand"] == "排列整齐"
    assert text_by_slot["slot-owner"] == "杨恩赐"
    assert set(image_by_slot) == {"slot-hazard-photo", "slot-fix-photo", "slot-review-photo"}
    assert unresolved_by_slot["slot-missing-lead"].reason_code == "ambiguous_match"
    assert all(fill.provenance_refs for fill in plan.text_fills)
    assert all(placement.provenance_refs for placement in plan.image_placements)
