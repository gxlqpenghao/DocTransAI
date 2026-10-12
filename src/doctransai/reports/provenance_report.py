from __future__ import annotations

from dataclasses import asdict
from typing import Any

from doctransai.models.render_plan import RenderPlan
from doctransai.renderers import RenderResult
from doctransai.validation import OutputCheckResult

from doctransai.reports.conversion_report import (
    _aggregate_source_evidence,
    _collect_diagnostics,
    _fill_to_dict,
    _image_placement_to_dict,
    _source_evidence_markdown_lines,
    _slot_evidence_markdown_lines,
    _unresolved_slot_to_dict,
)


def build_provenance_report(
    plan: RenderPlan,
    render_result: RenderResult,
    output_check_result: OutputCheckResult,
) -> tuple[dict[str, Any], str]:
    payload = {
        "plan_id": plan.plan_id,
        "created_at": plan.created_at,
        "template": asdict(plan.template),
        "output": asdict(plan.output),
        "fills": [_fill_to_dict(fill) for fill in plan.text_fills],
        "image_placements": [_image_placement_to_dict(placement) for placement in plan.image_placements],
        "unresolved": [_unresolved_slot_to_dict(slot) for slot in plan.unresolved_slots],
        "diagnostics": _collect_diagnostics(
            plan_diagnostics=plan.diagnostics,
            render_diagnostics=render_result.diagnostics,
            output_issues=output_check_result.issues,
        ),
        "source_evidence": _aggregate_source_evidence(
            fill_refs=[(fill.slot_id, fill.provenance_refs) for fill in plan.text_fills],
            image_refs=[(placement.slot_id, placement.provenance_refs) for placement in plan.image_placements],
            unresolved_refs=[(slot.slot_id, slot.provenance_refs) for slot in plan.unresolved_slots],
        ),
    }
    markdown = _build_provenance_markdown(payload)
    return payload, markdown


def _build_provenance_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Provenance Report",
        "",
        f"- Plan ID: {payload['plan_id']}",
        f"- Output Path: {payload['output']['output_path']}",
        "",
        "## Fills",
    ]
    lines.extend(_provenance_fill_markdown_lines(payload["fills"]))
    lines.extend(["", "## Image Placements"])
    lines.extend(_provenance_image_markdown_lines(payload["image_placements"]))
    lines.extend(["", "## Unresolved"])
    lines.extend(_provenance_unresolved_markdown_lines(payload["unresolved"]))
    lines.extend(["", "## Diagnostics"])
    lines.extend(
        f"- [{diagnostic['stage']}] {diagnostic['code']}: {diagnostic['message']}"
        for diagnostic in payload["diagnostics"]
    )
    lines.extend(["", "## Source Evidence"])
    lines.extend(_source_evidence_markdown_lines(payload["source_evidence"]))
    return "\n".join(lines)


def _provenance_fill_markdown_lines(fills: list[dict[str, Any]]) -> list[str]:
    if not fills:
        return ["- None"]
    lines: list[str] = []
    for fill in fills:
        line = f"- {fill['slot_id']}: value={fill['value']} target={fill['target']}"
        if fill.get("traceability_status"):
            line = f"{line} traceability_status={fill['traceability_status']}"
        lines.append(line)
        lines.extend(_slot_evidence_markdown_lines(fill["source_evidence"]))
    return lines


def _provenance_image_markdown_lines(image_placements: list[dict[str, Any]]) -> list[str]:
    if not image_placements:
        return ["- None"]
    lines: list[str] = []
    for placement in image_placements:
        lines.append(
            f"- {placement['slot_id']}: asset_id={placement['asset_id']} source_ref={placement['source_ref']} "
            f"target={placement['target']}"
        )
        lines.extend(_slot_evidence_markdown_lines(placement["source_evidence"]))
    return lines


def _provenance_unresolved_markdown_lines(unresolved: list[dict[str, Any]]) -> list[str]:
    if not unresolved:
        return ["- None"]
    lines: list[str] = []
    for slot in unresolved:
        lines.append(
            f"- {slot['slot_id']}: canonical_key={slot['canonical_key']} "
            f"reason_code={slot['reason_code']} message={slot['message']}"
        )
        lines.extend(_slot_evidence_markdown_lines(slot["source_evidence"]))
    return lines


__all__ = [
    "build_provenance_report",
]
