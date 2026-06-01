from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from doctransai.models.render_plan import ImagePlacement, RenderPlan, TargetRef, TextFill
from doctransai.renderers import RenderDiagnostic, RenderResult, resolve_image_placement


class XlsxRenderer:
    format_key = "xlsx"

    def render(
        self,
        plan: RenderPlan,
        *,
        bundle_dir: str | Path | None = None,
    ) -> RenderResult:
        workbook = load_workbook(plan.template.template_path)
        diagnostics: list[RenderDiagnostic] = []
        applied_text_slots: list[str] = []
        applied_image_slots: list[str] = []

        for text_fill in plan.text_fills:
            if text_fill.target.target_kind != "cell":
                diagnostics.append(_unsupported_target_diagnostic(text_fill.slot_id, text_fill.target))
                continue

            target = _resolve_target_cell(workbook, text_fill.target, slot_id=text_fill.slot_id)
            if isinstance(target, RenderDiagnostic):
                diagnostics.append(target)
                continue

            worksheet, cell_ref = target
            worksheet[cell_ref] = text_fill.value
            applied_text_slots.append(text_fill.slot_id)

        for placement in plan.image_placements:
            if placement.target.target_kind != "cell":
                diagnostics.append(
                    _unsupported_target_diagnostic(
                        placement.slot_id,
                        placement.target,
                        asset_id=placement.asset_id,
                        source_ref=placement.source_ref,
                    )
                )
                continue

            target = _resolve_target_cell(workbook, placement.target, slot_id=placement.slot_id, asset_id=placement.asset_id)
            if isinstance(target, RenderDiagnostic):
                diagnostics.append(target)
                continue

            resolved = resolve_image_placement(
                placement,
                bundle_dir=bundle_dir,
                source_bundle_path=plan.source_bundle_path,
            )
            if resolved.diagnostics:
                diagnostics.extend(resolved.diagnostics)
                continue
            if resolved.asset_path is None:
                continue

            worksheet, cell_ref = target
            image = XLImage(str(resolved.asset_path))
            if resolved.render_size is not None:
                image.width = max(1, int(round(resolved.render_size.width)))
                image.height = max(1, int(round(resolved.render_size.height)))
            worksheet.add_image(image, cell_ref)
            applied_image_slots.append(placement.slot_id)

        output_path = Path(plan.output.output_path).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(output_path)

        return RenderResult(
            output_path=str(output_path),
            applied_text_slots=applied_text_slots,
            applied_image_slots=applied_image_slots,
            diagnostics=diagnostics,
        )


def _resolve_target_cell(
    workbook: Workbook,
    target: TargetRef,
    *,
    slot_id: str,
    asset_id: str | None = None,
) -> tuple[Worksheet, str] | RenderDiagnostic:
    sheet_name = target.sheet_name or workbook.sheetnames[0]
    cell_ref = target.cell_ref
    if not cell_ref:
        return RenderDiagnostic(
            severity="error",
            code="invalid_target",
            message=f"XLSX cell target for slot {slot_id} is missing cell_ref.",
            slot_id=slot_id,
            asset_id=asset_id,
        )
    if sheet_name not in workbook.sheetnames:
        return RenderDiagnostic(
            severity="error",
            code="missing_sheet",
            message=f"Worksheet '{sheet_name}' was not found for slot {slot_id}.",
            slot_id=slot_id,
            asset_id=asset_id,
        )
    return workbook[sheet_name], cell_ref


def _unsupported_target_diagnostic(
    slot_id: str,
    target: TargetRef,
    *,
    asset_id: str | None = None,
    source_ref: str | None = None,
) -> RenderDiagnostic:
    return RenderDiagnostic(
        severity="error",
        code="unsupported_target_kind",
        message=f"XLSX renderer does not support target_kind '{target.target_kind}' for slot {slot_id}.",
        slot_id=slot_id,
        asset_id=asset_id,
        source_ref=source_ref,
    )
