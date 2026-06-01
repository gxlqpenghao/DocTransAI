from __future__ import annotations

import re
from typing import Any, Callable

from doctransai.mapping.agent_resolver import (
    AgentDecision,
    prepare_agent_shared_context,
    prepare_agent_review_slot_packets,
    prepare_agent_slot_packets,
    resolve_mapping_decisions_with_trace,
)
from doctransai.mapping.consistency import MISMATCH_REASON_CODE, apply_cross_slot_consistency_checks
from doctransai.mapping.planner import build_render_plan
from doctransai.mapping.review_policy import select_review_text_fills
from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import (
    ImagePlacement,
    PlanDiagnostic,
    RenderPlan,
    RowPlan,
    TargetRef,
    TextFill,
    render_plan_from_dict,
    render_plan_to_dict,
)
from doctransai.models.source import ProvenanceRef, SourceModel
from doctransai.models.template import TemplateModel
from doctransai.source_model.instances import build_source_instance_index


_PER_SLOT_TEXT_CANDIDATE_PRODUCT_LIMIT = 512


def build_render_plan_with_agent(
    *,
    template_model: TemplateModel,
    source_model: SourceModel,
    source_bundle_path: str,
    output_path: str,
    primary_record_id: str | None = None,
    source_instance_id: str | None = None,
    decision_client: Callable[..., str] | None = None,
) -> dict[str, Any]:
    base_payload = build_render_plan(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=source_bundle_path,
        output_path=output_path,
        primary_record_id=primary_record_id,
        source_instance_id=source_instance_id,
        enable_repeat_region_autofill=False,
    )
    base_plan = render_plan_from_dict(base_payload)
    review_text_fills = select_review_text_fills(base_plan)
    if not base_plan.unresolved_slots and not review_text_fills:
        return base_payload

    primary_record = _primary_record(source_model, base_plan)
    slots_by_id = {slot.slot_id: slot for slot in template_model.slots}
    include_text_candidates = not _should_omit_per_slot_text_candidates(source_model=source_model, template_model=template_model)
    slot_packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=primary_record,
        unresolved_slots=base_plan.unresolved_slots,
        template_slots_by_id=slots_by_id,
        include_text_candidates=include_text_candidates,
    )
    slot_packets.extend(
        prepare_agent_review_slot_packets(
            source_model=source_model,
            primary_record=primary_record,
            review_text_fills=review_text_fills,
            template_slots_by_id=slots_by_id,
            include_text_candidates=include_text_candidates,
        )
    )
    if not slot_packets:
        return base_payload

    shared_context = prepare_agent_shared_context(
        source_model=source_model,
        primary_record=primary_record,
        template_model=template_model,
        template_slots_by_id=slots_by_id,
    )

    agent_trace = resolve_mapping_decisions_with_trace(
        slot_packets,
        decision_client=decision_client,
        shared_context=shared_context,
    )
    decisions = agent_trace.decisions
    merged_payload = build_render_plan_with_decisions(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=source_bundle_path,
        output_path=output_path,
        primary_record_id=primary_record_id,
        source_instance_id=source_instance_id,
        decisions=decisions,
    )
    _append_agent_context_diagnostics(merged_payload, shared_context)
    _append_agent_payload_preflight_diagnostics(merged_payload, agent_trace.payload_preflight)
    return merged_payload


def build_render_plan_with_decisions(
    *,
    template_model: TemplateModel,
    source_model: SourceModel,
    source_bundle_path: str,
    output_path: str,
    primary_record_id: str | None = None,
    source_instance_id: str | None = None,
    decisions: list[AgentDecision],
) -> dict[str, Any]:
    base_payload = build_render_plan(
        template_model=template_model,
        source_model=source_model,
        source_bundle_path=source_bundle_path,
        output_path=output_path,
        primary_record_id=primary_record_id,
        source_instance_id=source_instance_id,
        enable_repeat_region_autofill=False,
    )
    base_plan = render_plan_from_dict(base_payload)
    review_text_fills = select_review_text_fills(base_plan)
    if not base_plan.unresolved_slots and not review_text_fills:
        return base_payload

    primary_record = _primary_record(source_model, base_plan)
    source_instance_index = build_source_instance_index(source_model)
    slots_by_id = {slot.slot_id: slot for slot in template_model.slots}
    include_text_candidates = not _should_omit_per_slot_text_candidates(source_model=source_model, template_model=template_model)
    slot_packets = prepare_agent_slot_packets(
        source_model=source_model,
        primary_record=primary_record,
        unresolved_slots=base_plan.unresolved_slots,
        template_slots_by_id=slots_by_id,
        include_text_candidates=include_text_candidates,
    )
    slot_packets.extend(
        prepare_agent_review_slot_packets(
            source_model=source_model,
            primary_record=primary_record,
            review_text_fills=review_text_fills,
            template_slots_by_id=slots_by_id,
            include_text_candidates=include_text_candidates,
        )
    )
    packet_index = {
        packet.slot_id: {candidate.candidate_id: candidate for candidate in packet.candidates}
        for packet in slot_packets
    }
    decisions_by_slot = {decision.slot_id: decision for decision in decisions}
    paired_caption_slot_ids = _paired_caption_slot_ids_for_image_decisions(
        decisions=decisions,
        slots_by_id=slots_by_id,
        decisions_by_slot=decisions_by_slot,
        packet_index=packet_index,
    )

    unresolved_by_slot = {slot.slot_id: slot for slot in base_plan.unresolved_slots}
    review_slot_ids = {fill.slot_id for fill in review_text_fills}
    text_fills = list(base_plan.text_fills)
    image_placements = list(base_plan.image_placements)
    image_roles_by_asset = _image_roles_by_asset(image_placements)
    diagnostics = list(base_plan.diagnostics)
    agent_success_diagnostics_by_slot: dict[str, list[PlanDiagnostic]] = {}
    record_plans = list(base_plan.record_plans)
    if not record_plans:
        record_plans.append(RowPlan(record_id=primary_record.record_id))

    for decision in decisions:
        original_unresolved = unresolved_by_slot.get(decision.slot_id)
        is_review_decision = decision.slot_id in review_slot_ids
        if original_unresolved is None and not is_review_decision:
            continue

        if is_review_decision:
            text_fills = [fill for fill in text_fills if fill.slot_id != decision.slot_id]
            image_placements = [placement for placement in image_placements if placement.slot_id != decision.slot_id]
            for record_plan in record_plans:
                record_plan.slot_ids = [slot_id for slot_id in record_plan.slot_ids if slot_id != decision.slot_id]

        if decision.slot_id in paired_caption_slot_ids:
            slot = slots_by_id.get(decision.slot_id)
            if slot is not None:
                diagnostics = _drop_stale_slot_diagnostics(diagnostics, slot)
                unresolved_by_slot.pop(decision.slot_id, None)
                record_plans[0].slot_ids.append(slot.slot_id)
            continue

        if decision.decision == "candidate" and decision.candidate_id is not None:
            packet = packet_index.get(decision.slot_id, {})
            slot = slots_by_id.get(decision.slot_id)
            selected_candidate_ids = _selected_candidate_ids(decision)
            selected_candidates = [packet[candidate_id] for candidate_id in selected_candidate_ids if candidate_id in packet]
            if not selected_candidates or slot is None:
                continue

            if selected_candidates[0].candidate_kind == "image":
                caption_slot = _paired_caption_slot(slot, slots_by_id)
                caption_decision = decisions_by_slot.get(caption_slot.slot_id) if caption_slot is not None else None
                captions = (
                    _captions_for_selected_images(
                        caption_decision=caption_decision,
                        packet_index=packet_index,
                        selected_candidates=selected_candidates,
                    )
                    if caption_slot is not None
                    else []
                )
                applied_image_slot_ids: list[str] = []
                had_role_conflict = False
                for index, candidate in enumerate(selected_candidates):
                    caption = captions[index] if index < len(captions) else None
                    expanded_slot_id = _expanded_image_slot_id(slot.slot_id, index, total=len(selected_candidates))
                    role_conflict = _image_role_conflict(image_roles_by_asset, asset_id=candidate.candidate_id, slot=slot)
                    if role_conflict is not None:
                        had_role_conflict = True
                        unresolved_by_slot[slot.slot_id] = UnresolvedSlot(
                            slot_id=slot.slot_id,
                            canonical_key=slot.raw_name,
                            reason_code="image_role_conflict",
                            message=(
                                f"Image asset {candidate.candidate_id} was already assigned to {role_conflict}; "
                                f"refusing to reuse it for {slot.raw_name} without independent source support."
                            ),
                            candidate_ids=[candidate.candidate_id],
                            provenance_refs=[_provenance_from_candidate(candidate)],
                        )
                        diagnostics.append(
                            PlanDiagnostic(
                                severity="warning",
                                code="image_role_conflict",
                                message=(
                                    f"Image asset {candidate.candidate_id} was already assigned to {role_conflict}; "
                                    f"refusing to reuse it for {slot.raw_name}."
                                ),
                                field=slot.raw_name,
                            )
                        )
                        continue
                    image_placements.append(
                        ImagePlacement(
                            slot_id=expanded_slot_id,
                            asset_id=candidate.candidate_id,
                            source_ref=_image_source_ref_from_candidate(candidate),
                            target=_target_for_slot(slot),
                            provenance_refs=[_provenance_from_candidate(candidate)],
                            caption=caption,
                            caption_slot_id=caption_slot.slot_id if caption and caption_slot is not None else None,
                            caption_target=_target_for_slot(caption_slot) if caption and caption_slot is not None else None,
                        )
                    )
                    image_roles_by_asset[candidate.candidate_id] = _image_role_key(slot)
                    applied_image_slot_ids.append(expanded_slot_id)
                if not applied_image_slot_ids and had_role_conflict:
                    continue
            else:
                candidate = selected_candidates[0]
                semantic_risk = _agent_text_candidate_semantic_risk(
                    slot=slot,
                    candidate=candidate,
                    decision=decision,
                )
                if semantic_risk is not None:
                    diagnostics.append(semantic_risk)
                text_fills.append(
                    TextFill(
                        slot_id=slot.slot_id,
                        target=_target_for_slot(slot),
                        value=candidate.value_text,
                        provenance_refs=[_provenance_from_candidate(candidate)],
                        confidence=decision.confidence,
                        transform="agent_selected_candidate",
                    )
                )
            diagnostics = _drop_stale_slot_diagnostics(diagnostics, slot)
            if selected_candidates[0].candidate_kind == "image":
                record_plans[0].slot_ids.extend(applied_image_slot_ids)
            else:
                record_plans[0].slot_ids.append(slot.slot_id)
            agent_diagnostic = PlanDiagnostic(
                severity="info",
                code="agent_reviewed_slot" if is_review_decision else "agent_resolved_slot",
                message=decision.reason,
                field=slot.raw_name,
            )
            diagnostics.append(agent_diagnostic)
            agent_success_diagnostics_by_slot.setdefault(slot.slot_id, []).append(agent_diagnostic)
            if selected_candidates[0].candidate_kind != "image" or not had_role_conflict:
                unresolved_by_slot.pop(decision.slot_id, None)
            continue

        if decision.decision == "generated" and decision.generated_value:
            slot = slots_by_id.get(decision.slot_id)
            if slot is None:
                continue
            text_fills.append(
                TextFill(
                    slot_id=slot.slot_id,
                    target=_target_for_slot(slot),
                    value=decision.generated_value,
                    provenance_refs=[
                        ProvenanceRef(
                            source_kind="generated",
                            document_id=primary_record.document_id,
                            object_id=primary_record.record_id,
                            locator=dict(primary_record.locator),
                            source_path=primary_record.source_path,
                        )
                    ],
                    confidence=decision.confidence,
                    transform="agent_generated_value",
                )
            )
            diagnostics = _drop_stale_slot_diagnostics(diagnostics, slot)
            record_plans[0].slot_ids.append(slot.slot_id)
            unresolved_by_slot.pop(decision.slot_id, None)
            if is_review_decision:
                agent_diagnostic = PlanDiagnostic(
                    severity="info",
                    code="agent_reviewed_slot",
                    message=decision.reason,
                    field=slot.raw_name,
                )
                diagnostics.append(agent_diagnostic)
                agent_success_diagnostics_by_slot.setdefault(slot.slot_id, []).append(agent_diagnostic)
            continue

        if original_unresolved is not None:
            original_unresolved.message = f"{original_unresolved.message} Agent reason: {decision.reason}"
        elif is_review_decision:
            slot = slots_by_id.get(decision.slot_id)
            if slot is None:
                continue
            unresolved_by_slot[decision.slot_id] = UnresolvedSlot(
                slot_id=slot.slot_id,
                canonical_key=slot.raw_name,
                reason_code="agent_review_unresolved",
                message=f"Agent rejected a risky auto-fill. Agent reason: {decision.reason}",
            )

    consistency_result = apply_cross_slot_consistency_checks(
        template_model=template_model,
        primary_record=primary_record,
        text_fills=text_fills,
        image_placements=image_placements,
        unresolved_slots=list(unresolved_by_slot.values()),
        resolved_slot_ids=record_plans[0].slot_ids if record_plans else [],
        source_instance_index=source_instance_index,
    )
    text_fills = consistency_result.text_fills
    image_placements = consistency_result.image_placements
    unresolved_by_slot = {slot.slot_id: slot for slot in consistency_result.unresolved_slots}
    if record_plans:
        record_plans[0].slot_ids = consistency_result.resolved_slot_ids
    diagnostics = _append_consistency_diagnostics(
        diagnostics,
        unresolved_slots=list(unresolved_by_slot.values()),
        agent_success_diagnostics_by_slot=agent_success_diagnostics_by_slot,
    )

    merged_plan = RenderPlan(
        plan_id=base_plan.plan_id,
        source_bundle_path=base_plan.source_bundle_path,
        template=base_plan.template,
        output=base_plan.output,
        text_fills=text_fills,
        image_placements=image_placements,
        unresolved_slots=list(unresolved_by_slot.values()),
        diagnostics=diagnostics,
        created_at=base_plan.created_at,
        record_plans=record_plans,
        schema_version=base_plan.schema_version,
    )
    return render_plan_to_dict(merged_plan)


def _primary_record(source_model: SourceModel, plan: RenderPlan):
    record_id = plan.record_plans[0].record_id if plan.record_plans else None
    for record in source_model.records:
        if record.record_id == record_id:
            return record
    return source_model.records[0]


def _should_omit_per_slot_text_candidates(*, source_model: SourceModel, template_model: TemplateModel) -> bool:
    text_slot_count = sum(1 for slot in template_model.slots if slot.slot_kind != "image")
    return len(source_model.records) * max(text_slot_count, 1) > _PER_SLOT_TEXT_CANDIDATE_PRODUCT_LIMIT


def _selected_candidate_ids(decision: AgentDecision) -> list[str]:
    if decision.candidate_ids:
        return list(decision.candidate_ids)
    return [decision.candidate_id] if decision.candidate_id is not None else []


def _expanded_image_slot_id(slot_id: str, index: int, *, total: int) -> str:
    return f"{slot_id}@{index}" if total > 1 else slot_id


def _paired_caption_slot_ids_for_image_decisions(
    *,
    decisions: list[AgentDecision],
    slots_by_id: dict[str, Any],
    decisions_by_slot: dict[str, AgentDecision],
    packet_index: dict[str, dict[str, Any]],
) -> set[str]:
    caption_slot_ids: set[str] = set()
    for decision in decisions:
        if decision.decision != "candidate":
            continue
        image_slot = slots_by_id.get(decision.slot_id)
        if image_slot is None or image_slot.slot_kind != "image":
            continue
        caption_slot = _paired_caption_slot(image_slot, slots_by_id)
        if caption_slot is None:
            continue
        caption_decision = decisions_by_slot.get(caption_slot.slot_id)
        if _caption_lines_for_decision(caption_decision, packet_index):
            caption_slot_ids.add(caption_slot.slot_id)
    return caption_slot_ids


def _paired_caption_slot(slot, slots_by_id: dict[str, Any]):
    caption_slot_id = slot.placement_constraints.get("paired_caption_slot_id")
    if not isinstance(caption_slot_id, str) or not caption_slot_id:
        return None
    caption_slot = slots_by_id.get(caption_slot_id)
    if caption_slot is None or caption_slot.slot_kind != "text":
        return None
    return caption_slot


def _captions_for_selected_images(
    *,
    caption_decision: AgentDecision | None,
    packet_index: dict[str, dict[str, Any]],
    selected_candidates: list[Any],
) -> list[str | None]:
    caption_lines = _caption_lines_for_decision(caption_decision, packet_index)
    captions: list[str | None] = []
    for index, candidate in enumerate(selected_candidates):
        if index < len(caption_lines):
            captions.append(caption_lines[index])
        else:
            captions.append(_caption_from_candidate_context(candidate))
    return captions


def _caption_lines_for_decision(
    decision: AgentDecision | None,
    packet_index: dict[str, dict[str, Any]],
) -> list[str]:
    if decision is None:
        return []
    if decision.decision == "generated" and decision.generated_value:
        return _split_caption_text(decision.generated_value)
    if decision.decision != "candidate":
        return []

    packet = packet_index.get(decision.slot_id, {})
    lines: list[str] = []
    for candidate_id in _selected_candidate_ids(decision):
        candidate = packet.get(candidate_id)
        if candidate is not None:
            lines.extend(_split_caption_text(candidate.value_text))
    return lines


def _split_caption_text(value: str) -> list[str]:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    raw_parts = normalized.split("\n") if "\n" in normalized else re.split(r"[；;]\s*", normalized)
    return [cleaned for part in raw_parts if (cleaned := _clean_caption_text(part))]


def _caption_from_candidate_context(candidate) -> str | None:
    for key in ("nearby_text_before", "nearby_text_after", "related_evidence_preview"):
        value = candidate.locator.get(key)
        if isinstance(value, list):
            for item in value:
                cleaned = _clean_caption_text(str(item))
                if cleaned:
                    return cleaned
        elif isinstance(value, str):
            cleaned = _clean_caption_text(value)
            if cleaned:
                return cleaned
    return None


def _clean_caption_text(value: str) -> str:
    text = value.strip().replace("**", "")
    text = re.sub(r"^\s*(?:[-*•]+|\d+[、.)．]|[（(]\s*[一二三四五六七八九十\d]+\s*[）)]|[一二三四五六七八九十]+[、.．])\s*", "", text)
    return text.strip("：:；;，,。.、 ")


def _drop_stale_slot_diagnostics(diagnostics: list[PlanDiagnostic], slot) -> list[PlanDiagnostic]:
    stale_codes = {
        "ambiguous_match",
        "low_confidence",
        "missing_asset",
        "missing_image_asset_file",
        "missing_value",
        MISMATCH_REASON_CODE,
    }
    slot_names = {slot.raw_name, slot.canonical_name}
    return [
        diagnostic
        for diagnostic in diagnostics
        if not (diagnostic.code in stale_codes and diagnostic.field in slot_names)
    ]


def _append_consistency_diagnostics(
    diagnostics: list[PlanDiagnostic],
    *,
    unresolved_slots: list[UnresolvedSlot],
    agent_success_diagnostics_by_slot: dict[str, list[PlanDiagnostic]],
) -> list[PlanDiagnostic]:
    rejected_slot_ids = {
        slot.slot_id
        for slot in unresolved_slots
        if slot.reason_code == MISMATCH_REASON_CODE
    }
    rejected_agent_diagnostic_ids = {
        id(diagnostic)
        for slot_id in rejected_slot_ids
        for diagnostic in agent_success_diagnostics_by_slot.get(slot_id, [])
    }
    result = [
        diagnostic
        for diagnostic in diagnostics
        if id(diagnostic) not in rejected_agent_diagnostic_ids
    ]
    existing = {(diagnostic.code, diagnostic.field) for diagnostic in result}
    for slot in unresolved_slots:
        if slot.reason_code != MISMATCH_REASON_CODE:
            continue
        key = (slot.reason_code, slot.canonical_key)
        if key in existing:
            continue
        existing.add(key)
        result.append(
            PlanDiagnostic(
                severity="warning",
                code=slot.reason_code,
                message=slot.message,
                field=slot.canonical_key,
            )
        )
    return result


def _target_for_slot(slot) -> Any:
    return TargetRef(
        format_key=slot.address.format_key,
        target_kind=slot.address.address_kind,
        paragraph_index=slot.address.paragraph_index,
        cell_paragraph_index=slot.address.cell_paragraph_index,
        run_index=slot.address.run_index,
        run_end_index=slot.address.run_end_index,
        table_index=slot.address.table_index,
        row_index=slot.address.row_index,
        column_index=slot.address.column_index,
        sheet_name=slot.address.sheet_name,
        cell_ref=slot.address.cell_ref,
        page_index=slot.address.page_index,
        form_field_name=slot.address.form_field_name,
        bbox=slot.address.bbox,
        notes=slot.raw_name,
        repeat_region_id=slot.repeat_region_id,
        instance_index=0 if slot.repeat_region_id is not None else None,
    )


def _provenance_from_candidate(candidate) -> ProvenanceRef:
    return ProvenanceRef(
        source_kind=candidate.candidate_kind,
        object_id=candidate.candidate_id,
        locator=dict(candidate.locator),
        source_path=candidate.source_path,
    )


def _image_source_ref_from_candidate(candidate) -> str | None:
    source_ref = candidate.locator.get("source_ref")
    if isinstance(source_ref, str) and source_ref:
        return source_ref
    return candidate.value_text


def _agent_text_candidate_semantic_risk(*, slot, candidate, decision: AgentDecision) -> PlanDiagnostic | None:
    if decision.confidence >= 0.8:
        return None
    if candidate.candidate_kind != "text":
        return None

    slot_label = f"{slot.raw_name} {slot.canonical_name}"
    candidate_label = str(candidate.value_label or "")
    if _label_overlap(slot_label, candidate_label) >= 0.55:
        return None

    return PlanDiagnostic(
        severity="warning",
        code="agent_candidate_semantic_risk",
        message=(
            f"Agent selected candidate `{candidate.candidate_id}` for {slot.raw_name}, but candidate label "
            f"`{candidate_label}` has weak semantic overlap with the target and confidence is only "
            f"{decision.confidence:.2f}. Agent reason: {decision.reason}"
        ),
        field=slot.raw_name,
    )


def _image_roles_by_asset(image_placements: list[ImagePlacement]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for placement in image_placements:
        role = _normalize_image_role(placement.target.notes or placement.slot_id)
        if role:
            roles.setdefault(placement.asset_id, role)
    return roles


def _image_role_conflict(roles_by_asset: dict[str, str], *, asset_id: str, slot) -> str | None:
    existing_role = roles_by_asset.get(asset_id)
    if existing_role is None:
        return None
    requested_role = _image_role_key(slot)
    if existing_role == requested_role:
        return None
    return existing_role


def _image_role_key(slot) -> str:
    return _normalize_image_role(f"{slot.raw_name} {slot.canonical_name}")


def _normalize_image_role(value: str) -> str:
    normalized = re.sub(r"\s+", "", value or "")
    normalized = re.sub(r"[{}【】\\[\\]（）()：:；;，,。.、/\\\\_-]+", "", normalized)
    return normalized.casefold()


def _label_overlap(left: str, right: str) -> float:
    left_tokens = set(_label_tokens(left))
    right_tokens = set(_label_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _label_tokens(value: str):
    text = re.sub(r"\s+", "", value or "")
    if any("\u4e00" <= character <= "\u9fff" for character in text):
        return tuple(character for character in text if character.isalnum() or "\u4e00" <= character <= "\u9fff")
    return tuple(token for token in re.split(r"[_\W]+", text.casefold()) if token)


def _append_agent_context_diagnostics(plan_payload: dict[str, Any], shared_context: dict[str, Any]) -> None:
    source_overview = shared_context.get("source_overview")
    if not isinstance(source_overview, dict):
        return
    context_diagnostics = source_overview.get("context_diagnostics")
    if not isinstance(context_diagnostics, list):
        return

    diagnostics = plan_payload.setdefault("diagnostics", [])
    for diagnostic in context_diagnostics:
        if not isinstance(diagnostic, dict):
            continue
        code = str(diagnostic.get("code") or "")
        if code != "content_truncated_for_agent_input":
            continue
        diagnostics.append(
            {
                "severity": str(diagnostic.get("severity") or "warning"),
                "code": "agent_context_truncated",
                "message": str(diagnostic.get("message") or "Agent source context was shortened."),
                "field": "agent_input",
            }
        )


def _append_agent_payload_preflight_diagnostics(plan_payload: dict[str, Any], preflight: dict[str, Any]) -> None:
    if not preflight:
        return
    estimated = preflight.get("estimated_request_bytes")
    limit = preflight.get("max_request_body_bytes")
    estimated_chars = preflight.get("estimated_input_chars")
    char_limit = preflight.get("max_input_chars")
    request_body_exceeded = bool(preflight.get("request_body_exceeded"))
    input_length_exceeded = bool(preflight.get("input_length_exceeded"))
    phase = preflight.get("phase")
    exceeded = bool(preflight.get("exceeded"))
    preflight_blocked = bool(preflight.get("preflight_blocked"))
    packaging = preflight.get("agent_input_packaging") if isinstance(preflight.get("agent_input_packaging"), dict) else {}
    packaging_message = _agent_input_packaging_message(packaging)
    if not preflight_blocked:
        diagnostics = plan_payload.setdefault("diagnostics", [])
        diagnostics.append(
            {
                "severity": "info",
                "code": "agent_input_payload_preflight",
                "message": (
                    "Agent input provider-limit estimate completed. "
                    f"estimated_request_bytes={estimated}; max_request_body_bytes={limit}; "
                    f"request_body_exceeded={str(request_body_exceeded).lower()}; "
                    f"estimated_input_chars={estimated_chars}; max_input_chars={char_limit}; "
                    f"input_length_exceeded={str(input_length_exceeded).lower()}; "
                    f"within_limit={str(not exceeded).lower()}; "
                    f"preflight_blocked=false; phase={phase}{packaging_message}"
                ),
                "field": "agent_input",
            }
        )
        return
    diagnostics = plan_payload.setdefault("diagnostics", [])
    diagnostics.append(
        {
            "severity": "warning",
            "code": "agent_input_payload_too_large",
            "message": (
                "Agent input exceeded configured provider limits; "
                "skipped the LLM call and kept affected slots unresolved. "
                f"estimated_request_bytes={estimated}; max_request_body_bytes={limit}; "
                f"request_body_exceeded={str(request_body_exceeded).lower()}; "
                f"estimated_input_chars={estimated_chars}; max_input_chars={char_limit}; "
                f"input_length_exceeded={str(input_length_exceeded).lower()}; "
                "within_limit=false; "
                f"preflight_blocked=true; phase={phase}{packaging_message}"
            ),
            "field": "agent_input",
        }
    )


def _agent_input_packaging_message(packaging: dict[str, Any]) -> str:
    if not packaging:
        return ""
    legacy_fields_removed = packaging.get("legacy_fields_removed")
    if isinstance(legacy_fields_removed, list):
        legacy_fields_text = ",".join(str(item) for item in legacy_fields_removed)
    else:
        legacy_fields_text = ""
    return (
        f"; packaging_mode={packaging.get('mode')}; "
        f"full_estimated_bytes={packaging.get('full_estimated_bytes')}; "
        f"compact_estimated_bytes={packaging.get('compact_estimated_bytes')}; "
        f"selected_estimated_bytes={packaging.get('selected_estimated_bytes')}; "
        f"limit_bytes={packaging.get('limit_bytes')}; "
        f"full_estimated_chars={packaging.get('full_estimated_chars')}; "
        f"compact_estimated_chars={packaging.get('compact_estimated_chars')}; "
        f"selected_estimated_chars={packaging.get('selected_estimated_chars')}; "
        f"char_limit={packaging.get('char_limit')}; "
        f"request_body_exceeded={str(bool(packaging.get('request_body_exceeded'))).lower()}; "
        f"input_length_exceeded={str(bool(packaging.get('input_length_exceeded'))).lower()}; "
        f"slot_packets_compacted={str(bool(packaging.get('slot_packets_compacted'))).lower()}; "
        f"full_context_compacted={str(bool(packaging.get('full_context_compacted'))).lower()}; "
        f"legacy_fields_removed={legacy_fields_text}"
    )
