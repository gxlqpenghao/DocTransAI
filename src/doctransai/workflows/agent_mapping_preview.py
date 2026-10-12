from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from doctransai.data_layer import read_parsed_document_bundle
from doctransai.mapping.agent_resolver import (
    prepare_agent_review_slot_packets,
    prepare_agent_shared_context,
    prepare_agent_slot_packets,
)
from doctransai.mapping.planner import build_render_plan
from doctransai.mapping.review_policy import select_review_text_fills
from doctransai.models.render_plan import RenderPlan, render_plan_from_dict
from doctransai.models.source import SourceModel, SourceRecord
from doctransai.source_model import adapt_source_corpus
from doctransai.templates import analyze_template


def build_agent_mapping_preview(
    *,
    bundle_path: str | Path,
    template_path: str | Path,
    primary_record_id: str | None = None,
    source_instance_id: str | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_bundle_path = Path(bundle_path).expanduser().resolve()
    resolved_template_path = Path(template_path).expanduser().resolve()

    corpus = read_parsed_document_bundle(resolved_bundle_path)
    source_model = adapt_source_corpus(corpus)
    template_model = analyze_template(resolved_template_path)
    plan_payload = build_render_plan(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=str(resolved_bundle_path),
        output_path=str(resolved_template_path.with_suffix(".preview.docx")),
        primary_record_id=primary_record_id,
        source_instance_id=source_instance_id,
        enable_repeat_region_autofill=False,
    )
    plan = render_plan_from_dict(plan_payload)

    slots_by_id = {slot.slot_id: slot for slot in template_model.slots}
    primary_record = _primary_record_from_plan(source_model, plan)
    slot_packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=primary_record,
        unresolved_slots=plan.unresolved_slots,
        template_slots_by_id=slots_by_id,
    )
    review_text_fills = select_review_text_fills(plan)
    slot_packets.extend(
        prepare_agent_review_slot_packets(
            source_model=source_model,
            primary_record=primary_record,
            review_text_fills=review_text_fills,
            template_slots_by_id=slots_by_id,
        )
    )
    shared_context = prepare_agent_shared_context(
        source_model=source_model,
        primary_record=primary_record,
        template_model=template_model,
        template_slots_by_id=slots_by_id,
        source_instance_id=source_instance_id,
    )

    payload = {
        "bundle_path": str(resolved_bundle_path),
        "template_path": str(resolved_template_path),
        "primary_record_id": primary_record.record_id,
        "source_instance_id": source_instance_id,
        "template_overview": shared_context["template_overview"],
        "source_overview": shared_context["source_overview"],
        "source_instance_overview": shared_context["source_instance_overview"],
        "source_cluster_plan": shared_context["source_cluster_plan"],
        "full_agent_context": shared_context["full_agent_context"],
        "unresolved_slots": [
            {
                "slot_id": slot.slot_id,
                "canonical_key": slot.canonical_key,
                "reason_code": slot.reason_code,
                "message": slot.message,
            }
            for slot in plan.unresolved_slots
        ],
        "review_slots": [
            {
                "slot_id": fill.slot_id,
                "current_value": fill.value,
                "current_confidence": fill.confidence,
                "current_transform": fill.transform,
            }
            for fill in review_text_fills
        ],
        "slot_packets": [asdict(packet) for packet in slot_packets],
    }

    if output_path is not None:
        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return payload


def _primary_record_from_plan(source_model: SourceModel, plan: RenderPlan) -> SourceRecord:
    record_id = plan.record_plans[0].record_id if plan.record_plans else None
    for record in source_model.records:
        if record.record_id == record_id:
            return record
    raise ValueError(f"Primary record not found in source model: {record_id}")
