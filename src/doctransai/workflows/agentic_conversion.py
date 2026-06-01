from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from doctransai.agentic_mapping.assembler import assemble_render_plan_from_decisions
from doctransai.agentic_mapping.context import build_evidence_package
from doctransai.agentic_mapping.decisions import AgentDecision
from doctransai.agentic_mapping.mapper import map_slots_with_agent
from doctransai.agentic_mapping.validator import ValidationResult, validate_agent_decisions
from doctransai.data_layer import read_parsed_document_bundle
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


def run_agentic_conversion(
    *,
    bundle_path: str | Path,
    template_path: str | Path,
    output_path: str | Path,
    decision_client=None,
    source_file_path: str | Path | None = None,
    source_page_images: list[str | Path | dict[str, Any]] | None = None,
    template_page_images: list[str | Path | dict[str, Any]] | None = None,
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
    )
    decisions = map_slots_with_agent(evidence_package, decision_client=decision_client)
    validation_result = validate_agent_decisions(decisions, evidence_package)
    render_plan = assemble_render_plan_from_decisions(
        source_bundle_path=str(resolved_bundle_path),
        template_model=template_model,
        output_path=str(resolved_output_path),
        decisions=validation_result.accepted_decisions,
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
) -> dict[str, Any]:
    return {
        "schema_name": "agentic_mapping_audit_report",
        "status": {
            "render_successful": render_result.is_successful,
            "has_rejected_decisions": bool(validation_result.rejected_decisions),
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
        "diagnostics": list(validation_result.diagnostics),
        "render_diagnostics": [asdict(diagnostic) for diagnostic in render_result.diagnostics],
        "applied_text_slots": list(render_result.applied_text_slots),
        "applied_image_slots": list(render_result.applied_image_slots),
    }


def _write_audit_report(output_path: Path, audit_report: dict[str, Any]) -> None:
    report_path = output_path.with_suffix(".agentic_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(audit_report, ensure_ascii=False, indent=2), encoding="utf-8")
