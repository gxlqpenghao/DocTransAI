from __future__ import annotations

from dataclasses import asdict
from typing import Any

from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import ImagePlacement, PlanDiagnostic, RenderPlan, TargetRef, TextFill
from doctransai.models.source import ProvenanceRef
from doctransai.renderers import RenderDiagnostic, RenderResult
from doctransai.validation import OutputCheckResult, OutputIssue


_AGENT_DIAGNOSTIC_CODES = {"agent_resolved_slot", "agent_reviewed_slot"}
LOW_TRACEABILITY_GENERATED = "low_traceability_generated"


def build_conversion_report(
    plan: RenderPlan,
    render_result: RenderResult,
    output_check_result: OutputCheckResult,
    *,
    full_agent_context_summary: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    agent_diagnostics = _agent_diagnostic_by_slot_id(plan.text_fills, plan.diagnostics)
    fills = [
        _conversion_fill(
            fill=fill,
            applied_text_slots=render_result.applied_text_slots,
            agent_diagnostic=agent_diagnostics.get(fill.slot_id),
        )
        for fill in plan.text_fills
    ]
    image_placements = [
        _conversion_image_placement(placement=placement, applied_image_slots=render_result.applied_image_slots)
        for placement in plan.image_placements
    ]
    unresolved = [_unresolved_slot_to_dict(slot) for slot in plan.unresolved_slots]
    low_traceability_generated_count = sum(
        1 for fill in fills if fill.get("traceability_status") == LOW_TRACEABILITY_GENERATED
    )
    diagnostics = _collect_diagnostics(
        plan_diagnostics=plan.diagnostics,
        render_diagnostics=render_result.diagnostics,
        output_issues=output_check_result.issues,
    )
    payload = {
        "plan_id": plan.plan_id,
        "created_at": plan.created_at,
        "template": asdict(plan.template),
        "output": asdict(plan.output),
        "status": _status_payload(
            render_result=render_result,
            output_check_result=output_check_result,
            unresolved_slots=plan.unresolved_slots,
            low_traceability_generated_count=low_traceability_generated_count,
        ),
        "fills": fills,
        "image_placements": image_placements,
        "unresolved": unresolved,
        "diagnostics": diagnostics,
        "source_evidence": _aggregate_source_evidence(
            fill_refs=[(fill.slot_id, fill.provenance_refs) for fill in plan.text_fills],
            image_refs=[(placement.slot_id, placement.provenance_refs) for placement in plan.image_placements],
            unresolved_refs=[(slot.slot_id, slot.provenance_refs) for slot in plan.unresolved_slots],
        ),
    }
    if full_agent_context_summary is not None:
        payload["full_agent_context_summary"] = dict(full_agent_context_summary)
    markdown = _build_conversion_markdown(payload)
    return payload, markdown


def build_full_agent_context_summary(
    full_agent_context: dict[str, Any],
    *,
    source_overview: dict[str, Any] | None = None,
    agent_payload_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    full_source_context = _dict_or_empty(full_agent_context.get("full_source_context"))
    task_context = _dict_or_empty(full_agent_context.get("task_context"))
    context_status = _dict_or_empty(_dict_or_empty(source_overview).get("context_status"))
    repeat_region_cluster_hints = task_context.get("repeat_region_cluster_hints")
    if not isinstance(repeat_region_cluster_hints, list):
        repeat_region_cluster_hints = []

    summary = {
        "full_agent_context_schema_version": str(full_agent_context.get("schema_version") or ""),
        "full_source_record_count": _int_or_zero(full_source_context.get("record_count")),
        "full_source_image_asset_count": _int_or_zero(full_source_context.get("image_asset_count")),
        "full_source_diagnostic_count": _int_or_zero(full_source_context.get("diagnostic_count")),
        "records_truncated": bool(context_status.get("records_truncated", False)),
        "diagnostics_truncated": bool(context_status.get("diagnostics_truncated", False)),
        "source_instance_id": _optional_string(task_context.get("source_instance_id")),
        "repeat_region_cluster_hints_present": bool(repeat_region_cluster_hints),
        "repeat_region_cluster_hint_count": len(repeat_region_cluster_hints),
    }
    payload_summary = _dict_or_empty(agent_payload_summary)
    summary.update(
        {
            "agent_input_estimated_bytes": _optional_int(payload_summary.get("estimated_request_bytes")),
            "agent_input_limit_bytes": _optional_int(payload_summary.get("max_request_body_bytes")),
            "agent_input_estimated_chars": _optional_int(payload_summary.get("estimated_input_chars")),
            "agent_input_char_limit": _optional_int(payload_summary.get("max_input_chars")),
            "agent_input_request_body_exceeded": _optional_bool(payload_summary.get("request_body_exceeded")),
            "agent_input_length_exceeded": _optional_bool(payload_summary.get("input_length_exceeded")),
            "agent_input_within_limit": _optional_bool(payload_summary.get("within_limit")),
            "agent_input_preflight_blocked": _optional_bool(payload_summary.get("preflight_blocked")),
        }
    )
    packaging = _dict_or_empty(payload_summary.get("agent_input_packaging"))
    if packaging:
        summary["agent_input_packaging"] = dict(packaging)
    return summary


def _status_payload(
    *,
    render_result: RenderResult,
    output_check_result: OutputCheckResult,
    unresolved_slots: list[UnresolvedSlot],
    low_traceability_generated_count: int = 0,
) -> dict[str, Any]:
    issue_counts = _issue_counts(output_check_result.issues)
    blocking_issue = (not render_result.is_successful) or issue_counts["error"] > 0
    review_required = (
        bool(unresolved_slots)
        or issue_counts["warning"] > 0
        or issue_counts["info"] > 0
        or low_traceability_generated_count > 0
    )
    return {
        "render_successful": render_result.is_successful,
        "render_clean": not blocking_issue,
        "review_required": review_required,
        "blocking_issue": blocking_issue,
        "output_clean": output_check_result.is_clean,
        "issue_counts": issue_counts,
        "low_traceability_generated_count": low_traceability_generated_count,
    }


def _issue_counts(issues: list[OutputIssue]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues:
        severity = issue.severity if issue.severity in counts else "info"
        counts[severity] += 1
    return counts


def _conversion_fill(
    *,
    fill: TextFill,
    applied_text_slots: list[str],
    agent_diagnostic: PlanDiagnostic | None,
) -> dict[str, Any]:
    payload = _fill_to_dict(fill)
    payload["transform"] = fill.transform
    payload["decision_kind"] = _fill_decision_kind(transform=fill.transform, agent_diagnostic=agent_diagnostic)
    if agent_diagnostic is not None:
        payload["decision_reason"] = agent_diagnostic.message
    payload["applied"] = fill.slot_id in applied_text_slots
    return payload


def _conversion_image_placement(*, placement: ImagePlacement, applied_image_slots: list[str]) -> dict[str, Any]:
    payload = _image_placement_to_dict(placement)
    payload["applied"] = placement.slot_id in applied_image_slots
    return payload


def _fill_to_dict(fill: TextFill) -> dict[str, Any]:
    payload = {
        "slot_id": fill.slot_id,
        "value": fill.value,
        "value_type": fill.value_type,
        "confidence": fill.confidence,
        "target": _target_to_dict(fill.target),
        "source_evidence": [_provenance_to_dict(ref) for ref in fill.provenance_refs],
    }
    if _is_low_traceability_generated(fill):
        payload["traceability_status"] = LOW_TRACEABILITY_GENERATED
        payload["review_required"] = True
    return payload


def _agent_diagnostic_by_slot_id(
    text_fills: list[TextFill],
    plan_diagnostics: list[PlanDiagnostic],
) -> dict[str, PlanDiagnostic]:
    diagnostics_by_field: dict[str, list[PlanDiagnostic]] = {}
    for diagnostic in plan_diagnostics:
        if diagnostic.code not in _AGENT_DIAGNOSTIC_CODES or diagnostic.field is None:
            continue
        diagnostics_by_field.setdefault(diagnostic.field, []).append(diagnostic)

    fill_keys_by_slot: dict[str, set[str]] = {}
    key_counts: dict[str, int] = {}
    for fill in text_fills:
        keys = _agent_diagnostic_keys(fill)
        fill_keys_by_slot[fill.slot_id] = keys
        for key in keys:
            key_counts[key] = key_counts.get(key, 0) + 1

    matched: dict[str, PlanDiagnostic] = {}
    for fill in text_fills:
        diagnostics: list[PlanDiagnostic] = []
        for key in fill_keys_by_slot[fill.slot_id]:
            if key_counts[key] != 1:
                continue
            field_diagnostics = diagnostics_by_field.get(key, [])
            if len(field_diagnostics) == 1:
                diagnostics.append(field_diagnostics[0])
        if len({id(diagnostic) for diagnostic in diagnostics}) == 1:
            matched[fill.slot_id] = diagnostics[0]
    return matched


def _agent_diagnostic_keys(fill: TextFill) -> set[str]:
    keys = {fill.slot_id}
    if fill.target.notes:
        keys.add(fill.target.notes)
    return keys


def _fill_decision_kind(*, transform: str | None, agent_diagnostic: PlanDiagnostic | None) -> str:
    if agent_diagnostic is not None and agent_diagnostic.code == "agent_reviewed_slot":
        return "agent_reviewed"
    if transform == "agent_generated_value":
        return "agent_generated"
    if transform == "agent_selected_candidate":
        return "agent_selected_candidate"
    if transform is None:
        return "rule_candidate"
    if _is_rule_transform(transform):
        return "rule_candidate"
    return "unknown"


def _is_low_traceability_generated(fill: TextFill) -> bool:
    return fill.transform == "agent_generated_value" and not _has_precise_non_generated_provenance(fill.provenance_refs)


def _has_precise_non_generated_provenance(refs: list[ProvenanceRef]) -> bool:
    for ref in refs:
        if ref.source_kind == "generated":
            continue
        if ref.evidence_id or ref.asset_id or ref.object_id:
            return True
        if _has_precise_locator(ref.locator):
            return True
    return False


def _has_precise_locator(locator: dict[str, Any]) -> bool:
    precise_keys = {
        "bbox",
        "cell_anchor",
        "cell_range",
        "page_anchor",
        "page_index",
        "range_ref",
        "row_index",
        "sheet_name",
        "table_id",
    }
    return any(locator.get(key) is not None for key in precise_keys)


def _is_rule_transform(transform: str) -> bool:
    return (
        "->" in transform
        or transform.endswith("_typed_row_match")
        or transform.startswith("unique_")
        or transform.startswith("repeat_region_")
    )


def _image_placement_to_dict(placement: ImagePlacement) -> dict[str, Any]:
    return {
        "slot_id": placement.slot_id,
        "asset_id": placement.asset_id,
        "source_ref": placement.source_ref,
        "target": _target_to_dict(placement.target),
        "sizing_policy": placement.sizing_policy,
        "caption": placement.caption,
        "source_evidence": [_provenance_to_dict(ref) for ref in placement.provenance_refs],
    }


def _unresolved_slot_to_dict(slot: UnresolvedSlot) -> dict[str, Any]:
    return {
        "slot_id": slot.slot_id,
        "canonical_key": slot.canonical_key,
        "reason_code": slot.reason_code,
        "message": slot.message,
        "candidate_ids": list(slot.candidate_ids),
        "source_evidence": [_provenance_to_dict(ref) for ref in slot.provenance_refs],
    }


def _target_to_dict(target: TargetRef) -> dict[str, Any]:
    payload = asdict(target)
    if payload.get("repeat_region_id") is None:
        payload.pop("repeat_region_id", None)
    if payload.get("instance_index") is None:
        payload.pop("instance_index", None)
    return payload


def _provenance_to_dict(ref: ProvenanceRef) -> dict[str, Any]:
    return {
        "source_kind": ref.source_kind,
        "document_id": ref.document_id,
        "evidence_id": ref.evidence_id,
        "asset_id": ref.asset_id,
        "object_id": ref.object_id,
        "source_path": ref.source_path,
        "locator": dict(ref.locator),
    }


def _collect_diagnostics(
    *,
    plan_diagnostics: list[PlanDiagnostic],
    render_diagnostics: list[RenderDiagnostic],
    output_issues: list[OutputIssue],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    diagnostics.extend(
        {
            "stage": "plan",
            "severity": diagnostic.severity,
            "code": diagnostic.code,
            "message": diagnostic.message,
            "field": diagnostic.field,
        }
        for diagnostic in plan_diagnostics
    )
    diagnostics.extend(
        {
            "stage": "render",
            "severity": diagnostic.severity,
            "code": diagnostic.code,
            "message": diagnostic.message,
            "slot_id": diagnostic.slot_id,
            "asset_id": diagnostic.asset_id,
            "source_ref": diagnostic.source_ref,
        }
        for diagnostic in render_diagnostics
    )
    diagnostics.extend(
        {
            "stage": "output_check",
            "severity": issue.severity,
            "code": issue.code,
            "message": issue.message,
            "artifact_name": issue.artifact_name,
            "slot_id": issue.slot_id,
            "asset_id": issue.asset_id,
            "placeholder_text": issue.placeholder_text,
        }
        for issue in output_issues
    )
    return diagnostics


def _aggregate_source_evidence(
    *,
    fill_refs: list[tuple[str, list[ProvenanceRef]]],
    image_refs: list[tuple[str, list[ProvenanceRef]]],
    unresolved_refs: list[tuple[str, list[ProvenanceRef]]],
) -> list[dict[str, Any]]:
    aggregated: list[dict[str, Any]] = []
    index_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}

    for slot_id, refs in [*fill_refs, *image_refs, *unresolved_refs]:
        for ref in refs:
            key = _provenance_key(ref)
            if key not in index_by_key:
                item = _provenance_to_dict(ref)
                item["slots"] = [slot_id]
                index_by_key[key] = item
                aggregated.append(item)
                continue
            slots = index_by_key[key]["slots"]
            if slot_id not in slots:
                slots.append(slot_id)

    return aggregated


def _provenance_key(ref: ProvenanceRef) -> tuple[Any, ...]:
    locator_items = tuple(sorted((key, _hashable_value(value)) for key, value in ref.locator.items()))
    return (
        ref.source_kind,
        ref.document_id,
        ref.evidence_id,
        ref.asset_id,
        ref.object_id,
        ref.source_path,
        locator_items,
    )


def _hashable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((key, _hashable_value(nested_value)) for key, nested_value in value.items()))
    if isinstance(value, list):
        return tuple(_hashable_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_hashable_value(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_hashable_value(item) for item in value))
    return value


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return bool(value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _build_conversion_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Conversion Report",
        "",
        f"- Plan ID: {payload['plan_id']}",
        f"- Output Path: {payload['output']['output_path']}",
        f"- Render Successful: {payload['status']['render_successful']}",
        f"- Render Clean: {payload['status']['render_clean']}",
        f"- Review Required: {payload['status']['review_required']}",
        f"- Blocking Issue: {payload['status']['blocking_issue']}",
        f"- Output Clean: {payload['status']['output_clean']}",
    ]
    if isinstance(payload.get("full_agent_context_summary"), dict):
        lines.extend(["", "## Agent Context"])
        lines.extend(_agent_context_markdown_lines(payload["full_agent_context_summary"]))
    lines.extend(["", "## Fills"])
    lines.extend(_fill_markdown_lines(payload["fills"]))
    lines.extend(["", "## Image Placements"])
    lines.extend(_image_markdown_lines(payload["image_placements"]))
    lines.extend(["", "## Unresolved"])
    lines.extend(_unresolved_markdown_lines(payload["unresolved"]))
    lines.extend(["", "## Diagnostics"])
    lines.extend(_diagnostic_markdown_lines(payload["diagnostics"]))
    lines.extend(["", "## Source Evidence"])
    lines.extend(_source_evidence_markdown_lines(payload["source_evidence"]))
    return "\n".join(lines)


def _agent_context_markdown_lines(summary: dict[str, Any]) -> list[str]:
    lines = [
        f"- Schema Version: {summary.get('full_agent_context_schema_version')}",
        f"- Full Source Records: {summary.get('full_source_record_count')}",
        f"- Full Source Images: {summary.get('full_source_image_asset_count')}",
        f"- Full Source Diagnostics: {summary.get('full_source_diagnostic_count')}",
        f"- Records Truncated: {summary.get('records_truncated')}",
        f"- Diagnostics Truncated: {summary.get('diagnostics_truncated')}",
        f"- Source Instance ID: {summary.get('source_instance_id')}",
        f"- Repeat Region Cluster Hints: {summary.get('repeat_region_cluster_hint_count')}",
        f"- Agent Input Estimated Bytes: {summary.get('agent_input_estimated_bytes')}",
        f"- Agent Input Limit Bytes: {summary.get('agent_input_limit_bytes')}",
        f"- Agent Input Estimated Chars: {summary.get('agent_input_estimated_chars')}",
        f"- Agent Input Char Limit: {summary.get('agent_input_char_limit')}",
        f"- Agent Input Request Body Exceeded: {summary.get('agent_input_request_body_exceeded')}",
        f"- Agent Input Length Exceeded: {summary.get('agent_input_length_exceeded')}",
        f"- Agent Input Within Limit: {summary.get('agent_input_within_limit')}",
        f"- Agent Input Preflight Blocked: {summary.get('agent_input_preflight_blocked')}",
    ]
    packaging = _dict_or_empty(summary.get("agent_input_packaging"))
    if packaging:
        lines.extend(
            [
                f"- Agent Input Packaging Mode: {packaging.get('mode')}",
                f"- Agent Input Full Estimated Bytes: {packaging.get('full_estimated_bytes')}",
                f"- Agent Input Compact Estimated Bytes: {packaging.get('compact_estimated_bytes')}",
                f"- Agent Input Selected Estimated Bytes: {packaging.get('selected_estimated_bytes')}",
                f"- Agent Input Full Estimated Chars: {packaging.get('full_estimated_chars')}",
                f"- Agent Input Compact Estimated Chars: {packaging.get('compact_estimated_chars')}",
                f"- Agent Input Selected Estimated Chars: {packaging.get('selected_estimated_chars')}",
                f"- Agent Input Char Limit: {packaging.get('char_limit')}",
                f"- Slot Packets Compacted: {packaging.get('slot_packets_compacted')}",
                f"- Legacy Fields Removed: {', '.join(str(item) for item in packaging.get('legacy_fields_removed') or [])}",
            ]
        )
    return lines


def _fill_markdown_lines(fills: list[dict[str, Any]]) -> list[str]:
    if not fills:
        return ["- None"]
    lines: list[str] = []
    for fill in fills:
        lines.append(
            f"- {fill['slot_id']}: applied={fill.get('applied')}, value={fill['value']}, "
            f"confidence={fill['confidence']}, decision_kind={fill['decision_kind']}, "
            f"transform={fill['transform']}"
        )
        if fill.get("traceability_status"):
            lines[-1] = f"{lines[-1]}, traceability_status={fill['traceability_status']}"
        if fill.get("decision_reason"):
            lines[-1] = f"{lines[-1]}, reason={fill['decision_reason']}"
        lines.extend(_slot_evidence_markdown_lines(fill.get("source_evidence", [])))
    return lines


def _image_markdown_lines(image_placements: list[dict[str, Any]]) -> list[str]:
    if not image_placements:
        return ["- None"]
    lines: list[str] = []
    for placement in image_placements:
        lines.append(
            f"- {placement['slot_id']}: applied={placement.get('applied')}, asset_id={placement['asset_id']}, "
            f"source_ref={placement['source_ref']}"
        )
        lines.extend(_slot_evidence_markdown_lines(placement.get("source_evidence", [])))
    return lines


def _unresolved_markdown_lines(unresolved: list[dict[str, Any]]) -> list[str]:
    if not unresolved:
        return ["- None"]
    lines: list[str] = []
    for slot in unresolved:
        lines.append(
            f"- {slot['slot_id']}: canonical_key={slot['canonical_key']}, "
            f"reason_code={slot['reason_code']}, message={slot['message']}"
        )
        lines.extend(_slot_evidence_markdown_lines(slot.get("source_evidence", [])))
    return lines


def _diagnostic_markdown_lines(diagnostics: list[dict[str, Any]]) -> list[str]:
    if not diagnostics:
        return ["- None"]
    return [
        f"- [{diagnostic['stage']}] {diagnostic['code']}: {diagnostic['message']}"
        for diagnostic in diagnostics
    ]


def _source_evidence_markdown_lines(source_evidence: list[dict[str, Any]]) -> list[str]:
    if not source_evidence:
        return ["- None"]
    return [
        f"- {item['source_kind']}: document_id={item['document_id']}, evidence_id={item['evidence_id']}, "
        f"asset_id={item['asset_id']}, locator={item['locator']}, slots={', '.join(item['slots'])}"
        for item in source_evidence
    ]


def _slot_evidence_markdown_lines(source_evidence: list[dict[str, Any]]) -> list[str]:
    if not source_evidence:
        return []
    return [
        f"  - source evidence: {item['source_kind']} locator={item['locator']} source_path={item['source_path']}"
        for item in source_evidence
    ]


__all__ = [
    "build_conversion_report",
    "build_full_agent_context_summary",
]
