from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from doctransai.agentic_mapping.assembler import assemble_render_plan_from_decisions
from doctransai.agentic_mapping.context import build_evidence_package
from doctransai.agentic_mapping.decision_repair import repair_duplicate_decisions
from doctransai.agentic_mapping.decisions import AgentDecision
from doctransai.agentic_mapping.mapper import AgentResponseParseError, map_slots_with_agent
from doctransai.agentic_mapping.template_targets import build_template_targets
from doctransai.agentic_mapping.target_ledger import build_target_ledger
from doctransai.agentic_mapping.validator import ValidationResult, validate_agent_decisions
from doctransai.agentic_mapping.visual_discovery import discover_template_visual_targets
from doctransai.data_layer import read_parsed_document_bundle
from doctransai.llm.client import (
    DoctransaiLLMConfigurationError,
    DoctransaiLLMHTTPStatusError,
    DoctransaiLLMInputTooLargeError,
    DoctransaiLLMRequestTooLargeError,
)
from doctransai.models.render_plan import RenderPlan
from doctransai.renderers.models import RenderResult
from doctransai.renderers.pipeline import renderer_for_format
from doctransai.source_model import AdaptedSourceModel, adapt_source_corpus
from doctransai.templates import analyze_template
from doctransai.templates.visual_preview import render_template_visual_pages


@dataclass(slots=True)
class AgenticConversionResult:
    evidence_package: dict[str, Any]
    decisions: list[AgentDecision]
    validation_result: ValidationResult
    render_plan: RenderPlan
    render_result: RenderResult
    audit_report: dict[str, Any]


_AGENT_FAILURE_EXCEPTIONS = (
    AgentResponseParseError,
    ValueError,
    DoctransaiLLMConfigurationError,
    DoctransaiLLMHTTPStatusError,
    DoctransaiLLMInputTooLargeError,
    DoctransaiLLMRequestTooLargeError,
)

_BRACE_PLACEHOLDER_RE = re.compile(r"\{[^{}\n]{1,80}\}")
_MAX_RESIDUAL_MARKER_ENTRIES = 50


def run_agentic_conversion(
    *,
    bundle_path: str | Path,
    template_path: str | Path,
    output_path: str | Path,
    decision_client=None,
    visual_discovery_client=None,
    source_file_path: str | Path | None = None,
    source_page_images: list[str | Path | dict[str, Any]] | None = None,
    template_page_images: list[str | Path | dict[str, Any]] | None = None,
    source_record_id: str | None = None,
) -> AgenticConversionResult:
    resolved_bundle_path = Path(bundle_path).expanduser().resolve()
    resolved_template_path = Path(template_path).expanduser().resolve()
    resolved_output_path = Path(output_path).expanduser().resolve()

    corpus = read_parsed_document_bundle(resolved_bundle_path)
    source_model = adapt_source_corpus(corpus)
    if source_file_path is not None:
        source_model = _filter_source_model_by_source_path(source_model, source_file_path)
    resolved_source_page_images = source_page_images
    if resolved_source_page_images is None:
        resolved_source_page_images = _render_source_page_images(source_model)

    template_model = analyze_template(resolved_template_path)
    resolved_template_page_images = template_page_images
    if resolved_template_page_images is None:
        resolved_template_page_images = render_template_visual_pages(
            resolved_template_path,
            format_key=template_model.format_key,
        )

    evidence_package = build_evidence_package(
        source_model,
        template_model,
        source_page_images=resolved_source_page_images,
        template_page_images=resolved_template_page_images,
        task_context=_task_context(source_record_id=source_record_id),
    )
    diagnostics: list[dict[str, Any]] = []
    template_visual_discovery: dict[str, Any] = {"performed": False, "target_count": 0, "visual_targets": []}
    if visual_discovery_client is not None or decision_client is None:
        template_visual_discovery = _add_template_visual_discovery(
            evidence_package,
            diagnostics=diagnostics,
            visual_discovery_client=visual_discovery_client,
        )
    try:
        decisions = map_slots_with_agent(evidence_package, decision_client=decision_client)
    except _AGENT_FAILURE_EXCEPTIONS as exc:
        decisions = _agent_failure_decisions(evidence_package, exc)
        diagnostics.append(_agent_failure_diagnostic(exc))
    decisions = _backfill_decision_target_refs(decisions, evidence_package)
    decisions, repair_diagnostics = repair_duplicate_decisions(decisions)
    diagnostics.extend(repair_diagnostics)
    decisions = _add_missing_slot_decisions(decisions, evidence_package)
    validation_result = validate_agent_decisions(decisions, evidence_package)
    validation_result.diagnostics[:0] = diagnostics
    render_decisions = _decisions_for_render(validation_result)
    render_plan = assemble_render_plan_from_decisions(
        source_bundle_path=str(resolved_bundle_path),
        template_model=template_model,
        output_path=str(resolved_output_path),
        decisions=render_decisions,
        evidence_package=evidence_package,
        diagnostics=validation_result.diagnostics,
    )

    renderer = renderer_for_format(render_plan.output.output_format)
    render_result = renderer.render(render_plan, bundle_dir=resolved_bundle_path.parent)
    audit_report = _build_audit_report(
        evidence_package=evidence_package,
        decisions=decisions,
        validation_result=validation_result,
        render_plan=render_plan,
        render_result=render_result,
        template_visual_discovery=template_visual_discovery,
    )
    _write_audit_report(resolved_output_path, audit_report)

    return AgenticConversionResult(
        evidence_package=evidence_package,
        decisions=decisions,
        validation_result=validation_result,
        render_plan=render_plan,
        render_result=render_result,
        audit_report=audit_report,
    )


def _add_missing_slot_decisions(
    decisions: list[AgentDecision],
    evidence_package: dict[str, Any],
) -> list[AgentDecision]:
    decided_slot_ids = {decision.slot_id for decision in decisions}
    missing_decisions = [
        AgentDecision(
            slot_id=slot_id,
            decision_type="unresolved",
            reason="Agent returned no decision for this template slot.",
        )
        for slot_id in _template_slot_ids(evidence_package)
        if slot_id not in decided_slot_ids
    ]
    if not missing_decisions:
        return decisions
    return [*decisions, *missing_decisions]


def _task_context(*, source_record_id: str | None) -> dict[str, Any] | None:
    if not source_record_id:
        return None
    return {
        "source_selection": {
            "preferred_record_id": source_record_id,
            "preferred_source_refs": [f"record:{source_record_id}"],
        }
    }


def _decisions_for_render(validation_result: ValidationResult) -> list[AgentDecision]:
    accepted_slot_ids = {decision.slot_id for decision in validation_result.accepted_decisions}
    unresolved_for_rejected: list[AgentDecision] = []
    seen_rejected_slots: set[str] = set()
    diagnostics_by_slot = _diagnostics_by_slot(validation_result.diagnostics)
    for rejected_decision in validation_result.rejected_decisions:
        if rejected_decision.slot_id in accepted_slot_ids or rejected_decision.slot_id in seen_rejected_slots:
            continue
        unresolved_for_rejected.append(
            AgentDecision(
                slot_id=rejected_decision.slot_id,
                decision_type="unresolved",
                source_refs=list(rejected_decision.source_refs),
                reason=_diagnostic_message(
                    diagnostics_by_slot.get(rejected_decision.slot_id),
                    rejected_decision,
                ),
            )
        )
        seen_rejected_slots.add(rejected_decision.slot_id)
    return [*validation_result.accepted_decisions, *unresolved_for_rejected]


def _agent_failure_decisions(
    evidence_package: dict[str, Any],
    exc: Exception,
) -> list[AgentDecision]:
    return [
        AgentDecision(
            slot_id=slot_id,
            decision_type="unresolved",
            reason=f"Agent response could not be parsed: {type(exc).__name__}: {exc}",
        )
        for slot_id in _template_slot_ids(evidence_package)
    ]


def _agent_failure_diagnostic(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, DoctransaiLLMInputTooLargeError):
        code = "agent_input_too_large"
    elif isinstance(exc, DoctransaiLLMRequestTooLargeError):
        code = "agent_request_too_large"
    elif isinstance(exc, (DoctransaiLLMConfigurationError, DoctransaiLLMHTTPStatusError)):
        code = "agent_execution_failed"
    else:
        code = "agent_response_invalid"
    return {
        "severity": "error",
        "code": code,
        "message": f"Agent response could not be parsed: {type(exc).__name__}: {exc}",
    }


def _backfill_decision_target_refs(
    decisions: list[AgentDecision],
    evidence_package: dict[str, Any],
) -> list[AgentDecision]:
    target_refs_by_id = _template_target_refs_by_id(evidence_package)
    if not target_refs_by_id:
        return decisions

    normalized: list[AgentDecision] = []
    for decision in decisions:
        target_ref = target_refs_by_id.get(decision.slot_id)
        if target_ref is None or not _should_backfill_target_ref(decision):
            normalized.append(decision)
            continue
        normalized.append(replace(decision, target_ref=target_ref))
    return normalized


def _template_target_refs_by_id(evidence_package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    targets = evidence_package.get("template", {}).get("targets", [])
    if not isinstance(targets, list):
        return {}
    refs: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict):
            continue
        target_id = target.get("target_id")
        target_ref = target.get("target_ref")
        if isinstance(target_id, str) and target_id and isinstance(target_ref, dict):
            refs[target_id] = dict(target_ref)
    return refs


def _should_backfill_target_ref(decision: AgentDecision) -> bool:
    if decision.target_ref is None:
        return True
    if not isinstance(decision.target_ref, dict):
        return False
    if decision.target_ref.get("target_kind") != "visual_text_anchor":
        return False
    label = decision.target_ref.get("label_or_nearby_text")
    suffix = decision.slot_id.removeprefix("visual-target-")
    return isinstance(label, str) and suffix.isdigit() and label == suffix


def _filter_source_model_by_source_path(
    source_model: AdaptedSourceModel,
    source_file_path: str | Path,
) -> AdaptedSourceModel:
    resolved_source_path = str(Path(source_file_path).expanduser().resolve())
    documents = [document for document in source_model.documents if document.source_path == resolved_source_path]
    if not documents:
        raise ValueError(f"Source file path not found in bundle: {resolved_source_path}")

    document_ids = {document.document_id for document in documents}

    def record_matches(record) -> bool:
        return record.document_id in document_ids and record.source_path == resolved_source_path

    image_assets = [
        asset
        for asset in source_model.image_assets
        if asset.document_id in document_ids
        or asset.source_path == resolved_source_path
        or asset.raw.get("source_path") == resolved_source_path
    ]
    diagnostics = [
        diagnostic
        for diagnostic in source_model.diagnostics
        if diagnostic.get("source_path") == resolved_source_path
        or diagnostic.get("document_id") in document_ids
    ]

    return AdaptedSourceModel(
        documents=documents,
        records=[record for record in source_model.records if record_matches(record)],
        image_assets=image_assets,
        diagnostics=diagnostics,
        evidence_records=[record for record in source_model.evidence_records if record_matches(record)],
        table_records=[record for record in source_model.table_records if record_matches(record)],
        cell_range_records=[record for record in source_model.cell_range_records if record_matches(record)],
        table_row_records=[record for record in source_model.table_row_records if record_matches(record)],
        table_cell_records=[record for record in source_model.table_cell_records if record_matches(record)],
        xlsx_row_records=[record for record in source_model.xlsx_row_records if record_matches(record)],
        sheet_records=[record for record in source_model.sheet_records if record_matches(record)],
    )


def _render_source_page_images(source_model: AdaptedSourceModel) -> list[dict[str, Any]]:
    page_images: list[dict[str, Any]] = []
    for document in source_model.documents:
        format_key = _visual_preview_format_key(document.source_path)
        if format_key is None:
            continue
        rendered_pages = render_template_visual_pages(
            document.source_path,
            format_key=format_key,
            cache_root=Path.cwd() / "tmp" / "source_visual_previews",
        )
        for page_index, page_path in enumerate(rendered_pages):
            page_images.append(
                {
                    "image_ref": str(page_path),
                    "page_index": page_index,
                    "source": document.document_id,
                }
            )
    return page_images


def _visual_preview_format_key(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix == ".doc":
        return "doc"
    if suffix == ".docx":
        return "docx"
    if suffix == ".xlsx":
        return "xlsx"
    if suffix == ".pdf":
        return "pdf"
    return None


def _build_audit_report(
    *,
    evidence_package: dict[str, Any],
    decisions: list[AgentDecision],
    validation_result: ValidationResult,
    render_plan: RenderPlan,
    render_result: RenderResult,
    template_visual_discovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_audit = _audit_rendered_output(render_result)
    return {
        "schema_name": "agentic_mapping_audit_report",
        "status": {
            "render_successful": render_result.is_successful,
            "has_rejected_decisions": bool(validation_result.rejected_decisions),
            "has_residual_template_markers": output_audit["residual_marker_count"] > 0,
        },
        "counts": {
            "source_records": len(evidence_package["source"]["structured"]["records"]),
            "source_images": len(evidence_package["source"]["structured"]["image_assets"]),
            "source_page_images": len(evidence_package["source"]["page_images"]),
            "template_slots": len(evidence_package["template"]["structured"]["slots"]),
            "template_page_images": len(evidence_package["template"]["page_images"]),
            "decisions": len(decisions),
            "accepted_decisions": len(validation_result.accepted_decisions),
            "rejected_decisions": len(validation_result.rejected_decisions),
            "text_fills": len(render_plan.text_fills),
            "image_placements": len(render_plan.image_placements),
            "unresolved_slots": len(render_plan.unresolved_slots),
        },
        "input_gaps": {
            "source": list(evidence_package["source"]["input_gaps"]),
            "template": list(evidence_package["template"]["input_gaps"]),
        },
        "task": dict(evidence_package.get("task", {})),
        "diagnostics": list(validation_result.diagnostics),
        "agent_input": dict(evidence_package.get("agent_input", {})),
        "template_visual_discovery": dict(template_visual_discovery or {"performed": False}),
        "visual_scan": dict(evidence_package.get("visual_scan", {"performed": False})),
        "decisions": {
            "accepted": [_decision_summary(decision) for decision in validation_result.accepted_decisions],
            "rejected": [_decision_summary(decision) for decision in validation_result.rejected_decisions],
        },
        "target_ledger": build_target_ledger(
            evidence_package=evidence_package,
            decisions=decisions,
            validation_result=validation_result,
            render_plan=render_plan,
            render_result=render_result,
        ),
        "unresolved": _unresolved_summary(
            evidence_package=evidence_package,
            validation_result=validation_result,
            render_plan=render_plan,
        ),
        "render_diagnostics": [asdict(diagnostic) for diagnostic in render_result.diagnostics],
        "applied_text_slots": list(render_result.applied_text_slots),
        "applied_image_slots": list(render_result.applied_image_slots),
        "output_audit": output_audit,
    }


def _decision_summary(decision: AgentDecision) -> dict[str, Any]:
    return {
        "slot_id": decision.slot_id,
        "decision_type": decision.decision_type,
        "value": decision.value,
        "value_type": decision.value_type,
        "transform": decision.transform,
        "asset_ref": decision.asset_ref,
        "source_ref": decision.source_ref,
        "source_refs": list(decision.source_refs),
        "target_ref": decision.target_ref,
        "sizing_policy": decision.sizing_policy,
        "caption": decision.caption,
        "caption_slot_id": decision.caption_slot_id,
        "caption_target": decision.caption_target,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "candidate_ids": list(decision.candidate_ids),
    }


def _unresolved_summary(
    *,
    evidence_package: dict[str, Any],
    validation_result: ValidationResult,
    render_plan: RenderPlan,
) -> list[dict[str, Any]]:
    filled_slot_ids = {_base_slot_id(fill.slot_id) for fill in render_plan.text_fills}
    filled_slot_ids.update(_base_slot_id(placement.slot_id) for placement in render_plan.image_placements)
    accepted_unresolved = _decisions_by_slot(
        decision
        for decision in validation_result.accepted_decisions
        if decision.decision_type == "unresolved"
    )
    rejected_decisions = _decisions_by_slot(validation_result.rejected_decisions)
    diagnostics_by_slot = _diagnostics_by_slot(validation_result.diagnostics)

    entries: list[dict[str, Any]] = []
    summarized_slot_ids = set(filled_slot_ids)

    for unresolved_slot in render_plan.unresolved_slots:
        slot_id = unresolved_slot.slot_id
        if slot_id in summarized_slot_ids:
            continue
        rejected_decision = rejected_decisions.get(slot_id)
        if rejected_decision is not None:
            entry = {
                "slot_id": slot_id,
                "reason": "validation_rejected",
                "message": _diagnostic_message(diagnostics_by_slot.get(slot_id), rejected_decision),
            }
            _add_decision_context(entry, rejected_decision)
        else:
            decision = accepted_unresolved.get(slot_id)
            entry = {
                "slot_id": slot_id,
                "reason": unresolved_slot.reason_code,
                "message": unresolved_slot.message,
            }
            _add_non_empty(entry, "candidate_ids", list(unresolved_slot.candidate_ids))
            if decision is not None:
                _add_decision_context(entry, decision)
        entries.append(entry)
        summarized_slot_ids.add(slot_id)

    for slot_id in _template_slot_ids(evidence_package):
        if slot_id in summarized_slot_ids:
            continue
        rejected_decision = rejected_decisions.get(slot_id)
        if rejected_decision is not None:
            entry = {
                "slot_id": slot_id,
                "reason": "validation_rejected",
                "message": _diagnostic_message(diagnostics_by_slot.get(slot_id), rejected_decision),
            }
            _add_decision_context(entry, rejected_decision)
        else:
            entry = {
                "slot_id": slot_id,
                "reason": "agent_unidentified",
                "message": "Agent returned no decision for this template slot.",
            }
        entries.append(entry)
        summarized_slot_ids.add(slot_id)

    return entries


def _template_slot_ids(evidence_package: dict[str, Any]) -> list[str]:
    targets = evidence_package.get("template", {}).get("targets", [])
    if isinstance(targets, list) and targets:
        target_ids: list[str] = []
        seen_targets: set[str] = set()
        for target in targets:
            if not isinstance(target, dict):
                continue
            target_id = target.get("target_id")
            if not isinstance(target_id, str) or not target_id or target_id in seen_targets:
                continue
            target_ids.append(target_id)
            seen_targets.add(target_id)
        return target_ids

    slots = evidence_package.get("template", {}).get("structured", {}).get("slots", [])
    slot_ids: list[str] = []
    seen: set[str] = set()
    for slot in slots:
        slot_id = _slot_id(slot)
        if slot_id is None or slot_id in seen:
            continue
        slot_ids.append(slot_id)
        seen.add(slot_id)
    return slot_ids


def _base_slot_id(slot_id: str) -> str:
    base, _, suffix = slot_id.partition("@")
    if base and suffix.isdigit():
        return base
    return slot_id


def _add_template_visual_discovery(
    evidence_package: dict[str, Any],
    *,
    diagnostics: list[dict[str, Any]],
    visual_discovery_client,
) -> dict[str, Any]:
    try:
        discovery = discover_template_visual_targets(
            evidence_package,
            discovery_client=visual_discovery_client,
        )
    except _AGENT_FAILURE_EXCEPTIONS as exc:
        discovery = {
            "performed": False,
            "error": f"{type(exc).__name__}: {exc}",
            "target_count": 0,
            "visual_targets": [],
        }
        diagnostics.append(
            {
                "severity": "warning",
                "code": "template_visual_discovery_failed",
                "message": discovery["error"],
            }
        )
    visual_targets = discovery.get("visual_targets", [])
    if not isinstance(visual_targets, list):
        visual_targets = []
    template = evidence_package.setdefault("template", {})
    template["targets"] = build_template_targets(
        template.get("structured", {}) if isinstance(template.get("structured"), dict) else {},
        visual_targets=visual_targets,
    )
    return discovery


def _slot_id(slot: Any) -> str | None:
    if isinstance(slot, dict):
        value = slot.get("slot_id")
    else:
        value = getattr(slot, "slot_id", None)
    return value if isinstance(value, str) and value else None


def _decisions_by_slot(decisions: Any) -> dict[str, AgentDecision]:
    by_slot: dict[str, AgentDecision] = {}
    for decision in decisions:
        by_slot.setdefault(decision.slot_id, decision)
    return by_slot


def _diagnostics_by_slot(diagnostics: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_slot: dict[str, list[dict[str, Any]]] = {}
    for diagnostic in diagnostics:
        slot_id = diagnostic.get("slot_id")
        if isinstance(slot_id, str) and slot_id:
            by_slot.setdefault(slot_id, []).append(diagnostic)
    return by_slot


def _diagnostic_message(
    diagnostics: list[dict[str, Any]] | None,
    decision: AgentDecision,
) -> str:
    messages = [
        str(diagnostic["message"])
        for diagnostic in diagnostics or []
        if isinstance(diagnostic.get("message"), str) and diagnostic["message"]
    ]
    if messages:
        return "; ".join(messages)
    if decision.reason:
        return decision.reason
    return "Decision was rejected by validation."


def _add_decision_context(entry: dict[str, Any], decision: AgentDecision) -> None:
    if decision.source_ref:
        entry["source_ref"] = decision.source_ref
    _add_non_empty(entry, "source_refs", list(decision.source_refs))
    entry["decision_type"] = decision.decision_type
    value_preview = _value_preview(decision.value)
    if value_preview is not None:
        entry["value_preview"] = value_preview


def _value_preview(value: Any, *, limit: int = 80) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _add_non_empty(entry: dict[str, Any], key: str, value: list[str]) -> None:
    if value:
        entry[key] = value


def _write_audit_report(output_path: Path, audit_report: dict[str, Any]) -> None:
    report_path = output_path.with_suffix(".agentic_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(audit_report, ensure_ascii=False, indent=2), encoding="utf-8")


def _audit_rendered_output(render_result: RenderResult) -> dict[str, Any]:
    output_path = Path(render_result.output_path)
    output_format = output_path.suffix.lower().lstrip(".")
    audit: dict[str, Any] = {
        "checked": False,
        "format": output_format,
        "residual_marker_count": 0,
        "residual_template_markers": [],
    }
    if output_format != "docx":
        audit["reason"] = "unsupported_output_format"
        return audit
    if not output_path.exists():
        audit["reason"] = "output_file_not_found"
        return audit

    try:
        markers = _docx_residual_template_markers(output_path)
    except Exception as exc:  # pragma: no cover - defensive report path
        audit["reason"] = "output_audit_failed"
        audit["error"] = f"{type(exc).__name__}: {exc}"
        return audit

    audit["checked"] = True
    audit["residual_marker_count"] = len(markers)
    audit["residual_template_markers"] = markers[:_MAX_RESIDUAL_MARKER_ENTRIES]
    audit["residual_template_markers_truncated"] = len(markers) > _MAX_RESIDUAL_MARKER_ENTRIES
    audit["residual_marker_counts_by_type"] = _marker_counts_by_type(markers)
    return audit


def _docx_residual_template_markers(output_path: Path) -> list[dict[str, Any]]:
    from docx import Document

    document = Document(output_path)
    markers: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(document.paragraphs):
        markers.extend(_paragraph_residual_template_markers(paragraph, f"paragraph:{paragraph_index}"))
    for table_index, table in enumerate(document.tables):
        for row_index, row in enumerate(table.rows):
            for column_index, cell in enumerate(row.cells):
                for paragraph_index, paragraph in enumerate(cell.paragraphs):
                    location = f"table:{table_index}:row:{row_index}:col:{column_index}:paragraph:{paragraph_index}"
                    markers.extend(_paragraph_residual_template_markers(paragraph, location))
    return markers


def _paragraph_residual_template_markers(paragraph: Any, location: str) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    text = paragraph.text or ""
    for match in _BRACE_PLACEHOLDER_RE.finditer(text):
        markers.append(
            {
                "type": "brace_placeholder",
                "text": match.group(0),
                "location": location,
                "context": _text_context(text),
            }
        )

    for run_index, run in enumerate(paragraph.runs):
        run_text = run.text or ""
        if run_text.strip() == "X":
            markers.append(
                {
                    "type": "x_run_marker",
                    "text": run_text,
                    "location": f"{location}:run:{run_index}",
                    "context": _text_context(text),
                }
            )
    return markers


def _text_context(text: str, *, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _marker_counts_by_type(markers: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for marker in markers:
        marker_type = str(marker.get("type", "unknown"))
        counts[marker_type] = counts.get(marker_type, 0) + 1
    return counts
