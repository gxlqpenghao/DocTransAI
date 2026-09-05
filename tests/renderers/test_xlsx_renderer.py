from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from PIL import Image as PillowImage

from doctransai.models.render_plan import ImagePlacement, OutputRef, RenderPlan, TargetRef, TemplateRef, TextFill
from doctransai.renderers.xlsx import XlsxRenderer


def _build_plan(
    *,
    template_path: Path,
    output_path: Path,
    text_fills: list[TextFill] | None = None,
    image_placements: list[ImagePlacement] | None = None,
    source_bundle_path: Path | None = None,
) -> RenderPlan:
    bundle_path = source_bundle_path or template_path.parent / "parsed_document_bundle.json"
    return RenderPlan(
        plan_id="plan-xlsx-1",
        source_bundle_path=str(bundle_path),
        template=TemplateRef(template_path=str(template_path), format_key="xlsx"),
        output=OutputRef(output_path=str(output_path), output_format="xlsx"),
        text_fills=text_fills or [],
        image_placements=image_placements or [],
        created_at="2026-05-21T12:00:00Z",
    )


def test_xlsx_renderer_writes_cells_inserts_images_and_keeps_workbook_openable(tmp_path: Path) -> None:
    template_path = tmp_path / "template.xlsx"
    output_path = tmp_path / "outputs" / "result.xlsx"
    bundle_dir = tmp_path / "bundle"
    asset_path = bundle_dir / "final_images" / "photo-1.png"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Roster"
    worksheet["A1"] = "Name"
    worksheet["B1"] = "Photo"
    workbook.save(template_path)

    asset_path.parent.mkdir(parents=True)
    PillowImage.new("RGB", (32, 24), color="red").save(asset_path)

    plan = _build_plan(
        template_path=template_path,
        output_path=output_path,
        source_bundle_path=bundle_dir / "parsed_document_bundle.json",
        text_fills=[
            TextFill(
                slot_id="slot-name",
                target=TargetRef(format_key="xlsx", target_kind="cell", sheet_name="Roster", cell_ref="A2"),
                value="Alice",
            )
        ],
        image_placements=[
            ImagePlacement(
                slot_id="slot-photo",
                asset_id="asset-1",
                source_ref="final_images/photo-1.png",
                target=TargetRef(format_key="xlsx", target_kind="cell", sheet_name="Roster", cell_ref="B2"),
            )
        ],
    )

    result = XlsxRenderer().render(plan, bundle_dir=bundle_dir)

    rendered = load_workbook(output_path)
    rendered_sheet = rendered["Roster"]

    assert result.output_path == str(output_path)
    assert result.applied_text_slots == ["slot-name"]
    assert result.applied_image_slots == ["slot-photo"]
    assert result.diagnostics == []
    assert result.is_successful is True
    assert rendered_sheet["A2"].value == "Alice"
    assert len(rendered_sheet._images) == 1
    assert (rendered_sheet._images[0].anchor._from.col, rendered_sheet._images[0].anchor._from.row) == (1, 1)


def test_xlsx_renderer_constrains_cell_images_to_target_cell_box(tmp_path: Path) -> None:
    template_path = tmp_path / "template.xlsx"
    output_path = tmp_path / "outputs" / "result.xlsx"
    bundle_dir = tmp_path / "bundle"
    asset_path = bundle_dir / "final_images" / "large-photo.png"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Register"
    worksheet["B1"] = "Photo"
    worksheet.column_dimensions["B"].width = 12
    worksheet.row_dimensions[2].height = 75
    workbook.save(template_path)

    asset_path.parent.mkdir(parents=True)
    PillowImage.new("RGB", (1200, 800), color="orange").save(asset_path)

    plan = _build_plan(
        template_path=template_path,
        output_path=output_path,
        source_bundle_path=bundle_dir / "parsed_document_bundle.json",
        image_placements=[
            ImagePlacement(
                slot_id="slot-photo",
                asset_id="asset-large",
                source_ref="final_images/large-photo.png",
                target=TargetRef(format_key="xlsx", target_kind="cell", sheet_name="Register", cell_ref="B2"),
            )
        ],
    )

    result = XlsxRenderer().render(plan, bundle_dir=bundle_dir)

    rendered = load_workbook(output_path)
    rendered_image = rendered["Register"]._images[0]
    display_width_px, display_height_px = _first_drawing_extent_pixels(output_path)

    assert result.diagnostics == []
    assert result.applied_image_slots == ["slot-photo"]
    assert rendered_image.width == 1200
    assert rendered_image.height == 800
    assert display_width_px <= 90
    assert display_height_px <= 100
    assert display_width_px < 1200
    assert display_height_px < 800


def test_xlsx_renderer_reports_unsupported_target_kinds_and_still_saves_workbook(tmp_path: Path) -> None:
    template_path = tmp_path / "template.xlsx"
    output_path = tmp_path / "outputs" / "result.xlsx"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Roster"
    workbook.save(template_path)

    plan = _build_plan(
        template_path=template_path,
        output_path=output_path,
        text_fills=[
            TextFill(
                slot_id="slot-name",
                target=TargetRef(format_key="xlsx", target_kind="paragraph", sheet_name="Roster", cell_ref="A2"),
                value="Alice",
            )
        ],
        image_placements=[
            ImagePlacement(
                slot_id="slot-photo",
                asset_id="asset-1",
                source_ref=None,
                target=TargetRef(format_key="xlsx", target_kind="image_placeholder", sheet_name="Roster", cell_ref="B2"),
            )
        ],
    )

    result = XlsxRenderer().render(plan)

    rendered = load_workbook(output_path)
    rendered_sheet = rendered["Roster"]

    assert result.applied_text_slots == []
    assert result.applied_image_slots == []
    assert {(item.code, item.slot_id, item.asset_id) for item in result.diagnostics} == {
        ("unsupported_target_kind", "slot-name", None),
        ("unsupported_target_kind", "slot-photo", "asset-1"),
    }
    assert result.is_successful is False
    assert rendered_sheet["A2"].value is None
    assert len(rendered_sheet._images) == 0


def _first_drawing_extent_pixels(workbook_path: Path) -> tuple[float, float]:
    with ZipFile(workbook_path) as archive:
        drawing_name = next(name for name in archive.namelist() if name.startswith("xl/drawings/") and name.endswith(".xml"))
        drawing_xml = archive.read(drawing_name).decode("utf-8")

    match = re.search(r'<ext cx="(?P<cx>\d+)" cy="(?P<cy>\d+)"', drawing_xml)
    assert match is not None
    return int(match.group("cx")) / 9525, int(match.group("cy")) / 9525
