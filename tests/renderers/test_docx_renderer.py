from __future__ import annotations

from importlib import import_module
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Emu
from docx.shared import Inches
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image

from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import ImagePlacement, OutputRef, RenderPlan, TargetRef, TemplateRef, TextFill
from doctransai.renderers.models import ImageSize, ResolvedImagePlacement


def _renderer():
    try:
        module = import_module("doctransai.renderers.docx")
    except ModuleNotFoundError as exc:
        pytest.fail(f"DOCX renderer module is missing: {exc}")
    return module.DocxRenderer()


def _build_plan(
    *,
    template_path: Path,
    output_path: Path,
    text_fills: list[TextFill] | None = None,
    image_placements: list[ImagePlacement] | None = None,
    unresolved_slots: list[UnresolvedSlot] | None = None,
) -> RenderPlan:
    return RenderPlan(
        plan_id="plan-docx-render",
        source_bundle_path=str(template_path.parent / "parsed_document_bundle.json"),
        template=TemplateRef(template_path=str(template_path), format_key="docx"),
        output=OutputRef(output_path=str(output_path), output_format="docx"),
        text_fills=text_fills or [],
        image_placements=image_placements or [],
        unresolved_slots=unresolved_slots or [],
    )


def test_docx_renderer_replaces_cross_run_paragraph_placeholder_and_keeps_base_style(tmp_path: Path) -> None:
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "outputs" / "rendered.docx"

    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("项目：")
    run = paragraph.add_run("{项")
    run.bold = True
    run = paragraph.add_run("目名称")
    run.bold = True
    run = paragraph.add_run("}")
    run.bold = True
    run = paragraph.add_run(" 完成")
    run.italic = True
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-project-name",
                    target=TargetRef(format_key="docx", target_kind="placeholder", paragraph_index=0),
                    value="新计划",
                )
            ],
        )
    )

    rendered = Document(output_path)
    paragraph = rendered.paragraphs[0]

    assert paragraph.text == "项目：新计划 完成"
    assert paragraph.runs[0].text == "项目："
    assert paragraph.runs[1].text == "新计划"
    assert paragraph.runs[1].bold is True
    assert paragraph.runs[-1].text == " 完成"
    assert paragraph.runs[-1].italic is True
    assert result.output_path == str(output_path)
    assert result.applied_text_slots == ["slot-project-name"]
    assert result.applied_image_slots == []
    assert result.diagnostics == []


def test_docx_renderer_replaces_specific_placeholder_when_multiple_exist_in_same_paragraph(tmp_path: Path) -> None:
    template_path = tmp_path / "multi-slot-template.docx"
    output_path = tmp_path / "outputs" / "multi-slot-rendered.docx"

    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("{项目名称}")
    paragraph.add_run(" / ")
    paragraph.add_run("{责任单位}")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-owner-org",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        paragraph_index=0,
                        notes="责任单位",
                    ),
                    value="华东分公司",
                ),
                TextFill(
                    slot_id="slot-project-name",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        paragraph_index=0,
                        notes="项目名称",
                    ),
                    value="新建工程",
                ),
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.paragraphs[0].text == "新建工程 / 华东分公司"
    assert result.applied_text_slots == ["slot-owner-org", "slot-project-name"]
    assert result.diagnostics == []


def test_docx_renderer_keeps_residual_same_name_placeholder_by_default(tmp_path: Path) -> None:
    template_path = tmp_path / "repeated-name-template.docx"
    output_path = tmp_path / "outputs" / "repeated-name-rendered.docx"

    document = Document()
    document.add_paragraph("责任人：{整改责任人}")
    document.add_paragraph("签字：{整改责任人}")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-owner",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        paragraph_index=0,
                        notes="整改责任人",
                    ),
                    value="杨恩赐",
                    confidence=0.9,
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert [paragraph.text for paragraph in rendered.paragraphs] == ["责任人：杨恩赐", "签字：{整改责任人}"]
    assert result.applied_text_slots == ["slot-owner"]
    assert result.diagnostics == []


def test_docx_renderer_replaces_residual_same_name_placeholder_when_explicitly_allowed(tmp_path: Path) -> None:
    template_path = tmp_path / "repeated-name-opt-in-template.docx"
    output_path = tmp_path / "outputs" / "repeated-name-opt-in-rendered.docx"

    document = Document()
    document.add_paragraph("责任人：{整改责任人}")
    document.add_paragraph("签字：{整改责任人}")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-owner",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        paragraph_index=0,
                        notes="整改责任人",
                        allow_same_name_residual_fill=True,
                    ),
                    value="杨恩赐",
                    confidence=0.9,
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert [paragraph.text for paragraph in rendered.paragraphs] == ["责任人：杨恩赐", "签字：杨恩赐"]
    assert result.applied_text_slots == ["slot-owner"]
    assert result.diagnostics == []


def test_docx_renderer_replaces_table_cell_placeholder(tmp_path: Path) -> None:
    template_path = tmp_path / "table-template.docx"
    output_path = tmp_path / "outputs" / "table-rendered.docx"

    document = Document()
    table = document.add_table(rows=1, cols=1)
    paragraph = table.cell(0, 0).paragraphs[0]
    paragraph.add_run("负责人：")
    paragraph.add_run("{负责人}")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-owner",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        table_index=0,
                        row_index=0,
                        column_index=0,
                    ),
                    value="张三",
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.tables[0].cell(0, 0).text == "负责人：张三"
    assert result.applied_text_slots == ["slot-owner"]
    assert result.applied_image_slots == []
    assert result.diagnostics == []


def test_docx_renderer_writes_text_into_empty_table_cell_slot(tmp_path: Path) -> None:
    template_path = tmp_path / "empty-cell-template.docx"
    output_path = tmp_path / "outputs" / "empty-cell-rendered.docx"

    document = Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "责任单位"
    table.cell(0, 1).text = ""
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-owner-org",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="table_cell_blank",
                        table_index=0,
                        row_index=0,
                        column_index=1,
                        cell_paragraph_index=0,
                        notes="责任单位",
                    ),
                    value="龚文升劳务队",
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.tables[0].cell(0, 0).text == "责任单位"
    assert rendered.tables[0].cell(0, 1).text == "龚文升劳务队"
    assert result.applied_text_slots == ["slot-owner-org"]
    assert result.diagnostics == []


def test_docx_renderer_inherits_paragraph_default_font_for_empty_table_cell_fill(tmp_path: Path) -> None:
    template_path = tmp_path / "empty-cell-paragraph-font-template.docx"
    output_path = tmp_path / "outputs" / "empty-cell-paragraph-font-rendered.docx"

    document = Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "单位名称"
    paragraph = table.cell(0, 1).paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    ppr = paragraph._p.get_or_add_pPr()
    rpr = OxmlElement("w:rPr")
    ppr.append(rpr)
    rfonts = OxmlElement("w:rFonts")
    rfonts.set(qn("w:eastAsia"), "方正仿宋_GBK")
    rfonts.set(qn("w:ascii"), "Times New Roman")
    rfonts.set(qn("w:hAnsi"), "Times New Roman")
    rpr.append(rfonts)
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-org",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="table_cell_blank",
                        table_index=0,
                        row_index=0,
                        column_index=1,
                        cell_paragraph_index=0,
                        notes="单位名称",
                    ),
                    value="广西路桥工程集团有限公司",
                )
            ],
        )
    )

    rendered_paragraph = Document(output_path).tables[0].cell(0, 1).paragraphs[0]
    rendered_run = rendered_paragraph.runs[0]
    rfonts = rendered_run._element.rPr.rFonts

    assert rendered_paragraph.text == "广西路桥工程集团有限公司"
    assert rendered_paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert rfonts.get(qn("w:eastAsia")) == "方正仿宋_GBK"
    assert rfonts.get(qn("w:ascii")) == "Times New Roman"
    assert rfonts.get(qn("w:hAnsi")) == "Times New Roman"
    assert result.applied_text_slots == ["slot-org"]
    assert result.diagnostics == []


def test_docx_renderer_replaces_instruction_table_cell_slot(tmp_path: Path) -> None:
    template_path = tmp_path / "instruction-cell-template.docx"
    output_path = tmp_path / "outputs" / "instruction-cell-rendered.docx"

    document = Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "成果简介"
    table.cell(0, 1).text = "（500字以内，简要说明研究背景、主要创新点、应用场景及成效）"
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-summary",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="table_cell_instruction",
                        table_index=0,
                        row_index=0,
                        column_index=1,
                        cell_paragraph_index=0,
                        notes="成果简介",
                    ),
                    value="本成果面向隧道地质信息融合解译与风险评估。",
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.tables[0].cell(0, 0).text == "成果简介"
    assert rendered.tables[0].cell(0, 1).text == "本成果面向隧道地质信息融合解译与风险评估。"
    assert result.applied_text_slots == ["slot-summary"]
    assert result.diagnostics == []


def test_docx_renderer_marks_matching_checkbox_options_in_choice_cell(tmp_path: Path) -> None:
    template_path = tmp_path / "choice-cell-template.docx"
    output_path = tmp_path / "outputs" / "choice-cell-rendered.docx"

    document = Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "所属领域"
    table.cell(0, 1).text = "□智能建造□建筑节能□BIM应用□其他（注明：__________）"
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-field",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="table_cell_choice",
                        table_index=0,
                        row_index=0,
                        column_index=1,
                        cell_paragraph_index=0,
                        notes="所属领域",
                    ),
                    value="智能建造；BIM应用",
                )
            ],
        )
    )

    rendered_text = Document(output_path).tables[0].cell(0, 1).text

    assert rendered_text == "☑智能建造□建筑节能☑BIM应用□其他（注明：__________）"
    assert result.applied_text_slots == ["slot-field"]
    assert result.diagnostics == []


def test_docx_renderer_writes_inline_detail_for_any_detail_choice(tmp_path: Path) -> None:
    template_path = tmp_path / "choice-detail-cell-template.docx"
    output_path = tmp_path / "outputs" / "choice-detail-cell-rendered.docx"

    document = Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "所属领域"
    table.cell(0, 1).text = "□智能建造□专项类别（说明：__________）"
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-field",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="table_cell_choice",
                        table_index=0,
                        row_index=0,
                        column_index=1,
                        cell_paragraph_index=0,
                        notes="所属领域",
                    ),
                    value="专项类别：隧道地质风险评估",
                )
            ],
        )
    )

    rendered_text = Document(output_path).tables[0].cell(0, 1).text

    assert rendered_text == "□智能建造☑专项类别（说明：隧道地质风险评估）"
    assert result.applied_text_slots == ["slot-field"]
    assert result.diagnostics == []


def test_docx_renderer_inserts_image_into_empty_table_cell_slot(tmp_path: Path) -> None:
    template_path = tmp_path / "empty-image-cell-template.docx"
    output_path = tmp_path / "outputs" / "empty-image-cell-rendered.docx"
    image_path = tmp_path / "现场照片.png"

    Image.new("RGB", (120, 60), color="navy").save(image_path)

    document = Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "现场照片"
    table.cell(0, 1).text = ""
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            image_placements=[
                ImagePlacement(
                    slot_id="slot-photo",
                    asset_id="asset-photo",
                    source_ref=str(image_path),
                    target=TargetRef(
                        format_key="docx",
                        target_kind="table_cell_blank",
                        table_index=0,
                        row_index=0,
                        column_index=1,
                        cell_paragraph_index=0,
                        notes="现场照片",
                    ),
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.tables[0].cell(0, 1).text == ""
    assert len(rendered.inline_shapes) == 1
    assert result.applied_image_slots == ["slot-photo"]
    assert result.diagnostics == []


def test_docx_renderer_keeps_inline_image_when_later_placeholder_is_cleared(tmp_path: Path) -> None:
    template_path = tmp_path / "mixed-placeholder-image-template.docx"
    output_path = tmp_path / "outputs" / "mixed-placeholder-image-rendered.docx"
    image_path = tmp_path / "整改照片.png"

    Image.new("RGB", (120, 60), color="navy").save(image_path)

    document = Document()
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "一、存在问题\n{存在问题}\n\n{整改照片}\n{整改描述}"
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-issue",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="table_cell",
                        table_index=0,
                        row_index=0,
                        column_index=0,
                        cell_paragraph_index=0,
                        notes="存在问题",
                    ),
                    value="临边防护缺失",
                )
            ],
            image_placements=[
                ImagePlacement(
                    slot_id="slot-photo",
                    asset_id="asset-photo",
                    source_ref=str(image_path),
                    target=TargetRef(
                        format_key="docx",
                        target_kind="table_cell",
                        table_index=0,
                        row_index=0,
                        column_index=0,
                        cell_paragraph_index=0,
                        notes="整改照片",
                    ),
                )
            ],
            unresolved_slots=[
                UnresolvedSlot(
                    slot_id="slot-description",
                    canonical_key="整改描述",
                    reason_code="missing_value",
                    message="missing",
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert "临边防护缺失" in rendered.tables[0].cell(0, 0).text
    assert "{整改描述}" not in rendered.tables[0].cell(0, 0).text
    assert len(rendered.inline_shapes) == 1
    assert result.applied_image_slots == ["slot-photo"]
    assert result.diagnostics == []


def test_docx_renderer_targets_specific_paragraph_inside_table_cell(tmp_path: Path) -> None:
    template_path = tmp_path / "table-multi-paragraph-template.docx"
    output_path = tmp_path / "outputs" / "table-multi-paragraph-rendered.docx"

    document = Document()
    table = document.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    cell.paragraphs[0].add_run("项目：{项目名称}")
    cell.add_paragraph("单位：{责任单位}")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-owner-org",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        table_index=0,
                        row_index=0,
                        column_index=0,
                        cell_paragraph_index=1,
                        notes="责任单位",
                    ),
                    value="华东分公司",
                )
            ],
        )
    )

    rendered = Document(output_path)
    cell = rendered.tables[0].cell(0, 0)

    assert cell.paragraphs[0].text == "项目：{项目名称}"
    assert cell.paragraphs[1].text == "单位：华东分公司"
    assert result.applied_text_slots == ["slot-owner-org"]
    assert result.diagnostics == []


def test_docx_renderer_expands_numbered_placeholder_into_multiple_list_items(tmp_path: Path) -> None:
    template_path = tmp_path / "numbered-list-template.docx"
    output_path = tmp_path / "outputs" / "numbered-list-rendered.docx"

    document = Document()
    table = document.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    cell.paragraphs[0].text = "安全问题（隐患）内容："
    cell.add_paragraph("{隐患描述}", style="List Number")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-hazard",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        table_index=0,
                        row_index=0,
                        column_index=0,
                        cell_paragraph_index=1,
                        notes="隐患描述",
                    ),
                    value="二工区围挡未及时封闭；有村民进入施工现场",
                )
            ],
        )
    )

    rendered_cell = Document(output_path).tables[0].cell(0, 0)

    assert [paragraph.text for paragraph in rendered_cell.paragraphs] == [
        "安全问题（隐患）内容：",
        "二工区围挡未及时封闭",
        "有村民进入施工现场",
    ]
    assert rendered_cell.paragraphs[1].style.name == rendered_cell.paragraphs[2].style.name
    assert result.applied_text_slots == ["slot-hazard"]
    assert result.diagnostics == []


def test_docx_renderer_replaces_underlined_blank_run_by_index(tmp_path: Path) -> None:
    template_path = tmp_path / "underlined-blank-template.docx"
    output_path = tmp_path / "outputs" / "underlined-blank-rendered.docx"

    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("检查日期：")
    blank = paragraph.add_run("        ")
    blank.underline = True
    paragraph.add_run("。")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-check-date",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="implicit_blank",
                        paragraph_index=0,
                        run_index=1,
                        run_end_index=1,
                        notes="检查日期",
                    ),
                    value="2022年3月27日",
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.paragraphs[0].text == "检查日期：2022年3月27日。"
    assert rendered.paragraphs[0].runs[1].underline is True
    assert result.applied_text_slots == ["slot-check-date"]
    assert result.diagnostics == []


def test_docx_renderer_preserves_underlined_literal_before_implicit_blank(tmp_path: Path) -> None:
    template_path = tmp_path / "underlined-marker-template.docx"
    output_path = tmp_path / "outputs" / "underlined-marker-rendered.docx"

    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("于")
    marker = paragraph.add_run("X")
    marker.underline = True
    blank = paragraph.add_run("        ")
    blank.underline = True
    paragraph.add_run("进行检查")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-check-date",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="implicit_blank",
                        paragraph_index=0,
                        run_index=2,
                        run_end_index=2,
                        notes="检查日期",
                    ),
                    value="2022年3月27日",
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.paragraphs[0].text == "于X2022年3月27日进行检查"
    assert result.applied_text_slots == ["slot-check-date"]
    assert result.diagnostics == []


def test_docx_renderer_preserves_underlined_literal_before_placeholder(tmp_path: Path) -> None:
    template_path = tmp_path / "underlined-placeholder-marker-template.docx"
    output_path = tmp_path / "outputs" / "underlined-placeholder-marker-rendered.docx"

    document = Document()
    paragraph = document.add_paragraph()
    marker = paragraph.add_run("X")
    marker.underline = True
    placeholder = paragraph.add_run("{责任单位}：")
    placeholder.underline = True
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-org",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        paragraph_index=0,
                        notes="责任单位",
                    ),
                    value="龚文升劳务队",
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.paragraphs[0].text == "X龚文升劳务队："
    assert result.applied_text_slots == ["slot-org"]
    assert result.diagnostics == []


def test_docx_renderer_preserves_underlined_literal_only_paragraphs(tmp_path: Path) -> None:
    template_path = tmp_path / "marker-only-template.docx"
    output_path = tmp_path / "outputs" / "marker-only-rendered.docx"

    document = Document()
    paragraph = document.add_paragraph()
    marker = paragraph.add_run("X")
    marker.underline = True
    document.add_paragraph("{责任单位}")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-org",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        paragraph_index=1,
                        notes="责任单位",
                    ),
                    value="龚文升劳务队",
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.paragraphs[0].text == "X"
    assert rendered.paragraphs[1].text == "龚文升劳务队"
    assert result.applied_text_slots == ["slot-org"]
    assert result.diagnostics == []


def test_docx_renderer_clears_unresolved_placeholders_but_keeps_them_unapplied(tmp_path: Path) -> None:
    template_path = tmp_path / "unresolved-placeholder-template.docx"
    output_path = tmp_path / "outputs" / "unresolved-placeholder-rendered.docx"

    document = Document()
    document.add_paragraph("检查人员：{检查人}")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            unresolved_slots=[
                UnresolvedSlot(
                    slot_id="slot-inspector",
                    canonical_key="检查人",
                    reason_code="missing_value",
                    message="No source-supported inspector.",
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.paragraphs[0].text == "检查人员："
    assert result.applied_text_slots == []
    assert result.diagnostics == []


def test_docx_renderer_inserts_image_for_placeholder(tmp_path: Path) -> None:
    template_path = tmp_path / "image-template.docx"
    output_path = tmp_path / "outputs" / "image-rendered.docx"
    image_path = tmp_path / "现场照片.png"

    Image.new("RGB", (120, 60), color="navy").save(image_path)

    document = Document()
    document.add_paragraph("{现场照片}")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            image_placements=[
                ImagePlacement(
                    slot_id="slot-photo",
                    asset_id="asset-photo",
                    source_ref=str(image_path),
                    target=TargetRef(format_key="docx", target_kind="image_placeholder", paragraph_index=0),
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.paragraphs[0].text == ""
    assert len(rendered.inline_shapes) == 1
    assert result.applied_text_slots == []
    assert result.applied_image_slots == ["slot-photo"]
    assert result.diagnostics == []


def test_docx_renderer_inserts_multiple_images_for_one_placeholder(tmp_path: Path) -> None:
    template_path = tmp_path / "multi-image-template.docx"
    output_path = tmp_path / "outputs" / "multi-image-rendered.docx"
    image_one = tmp_path / "照片1.png"
    image_two = tmp_path / "照片2.png"

    Image.new("RGB", (120, 60), color="navy").save(image_one)
    Image.new("RGB", (120, 60), color="green").save(image_two)

    document = Document()
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "图片区：{整改照片}"
    document.save(template_path)

    target = TargetRef(
        format_key="docx",
        target_kind="table_cell",
        table_index=0,
        row_index=0,
        column_index=0,
        cell_paragraph_index=0,
        notes="整改照片",
    )
    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            image_placements=[
                ImagePlacement(slot_id="slot-photo@0", asset_id="asset-photo-1", source_ref=str(image_one), target=target),
                ImagePlacement(slot_id="slot-photo@1", asset_id="asset-photo-2", source_ref=str(image_two), target=target),
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.tables[0].cell(0, 0).text == "图片区："
    assert len(rendered.inline_shapes) == 2
    assert result.applied_image_slots == ["slot-photo@0", "slot-photo@1"]
    assert result.diagnostics == []


def test_docx_renderer_interleaves_multiple_images_with_captions_and_clears_caption_placeholder(tmp_path: Path) -> None:
    template_path = tmp_path / "multi-image-caption-template.docx"
    output_path = tmp_path / "outputs" / "multi-image-caption-rendered.docx"
    image_one = tmp_path / "照片1.png"
    image_two = tmp_path / "照片2.png"

    Image.new("RGB", (120, 60), color="navy").save(image_one)
    Image.new("RGB", (120, 60), color="green").save(image_two)

    document = Document()
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "图片区：{整改照片}\n{整改照片说明}"
    document.save(template_path)

    image_target = TargetRef(
        format_key="docx",
        target_kind="table_cell",
        table_index=0,
        row_index=0,
        column_index=0,
        cell_paragraph_index=0,
        notes="整改照片",
    )
    caption_target = TargetRef(
        format_key="docx",
        target_kind="table_cell",
        table_index=0,
        row_index=0,
        column_index=0,
        cell_paragraph_index=0,
        notes="整改照片说明",
    )
    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            image_placements=[
                ImagePlacement(
                    slot_id="slot-photo@0",
                    asset_id="asset-photo-1",
                    source_ref=str(image_one),
                    target=image_target,
                    caption="蜂窝麻面",
                    caption_slot_id="slot-caption",
                    caption_target=caption_target,
                ),
                ImagePlacement(
                    slot_id="slot-photo@1",
                    asset_id="asset-photo-2",
                    source_ref=str(image_two),
                    target=image_target,
                    caption="涨模错缝",
                    caption_slot_id="slot-caption",
                    caption_target=caption_target,
                ),
            ],
        )
    )

    rendered = Document(output_path)
    cell_text = rendered.tables[0].cell(0, 0).text

    assert "{整改照片说明}" not in cell_text
    assert "蜂窝麻面" in cell_text
    assert "涨模错缝" in cell_text
    assert cell_text.index("蜂窝麻面") < cell_text.index("涨模错缝")
    assert len(rendered.inline_shapes) == 2
    assert result.applied_image_slots == ["slot-photo@0", "slot-photo@1"]
    assert result.diagnostics == []


def test_docx_renderer_maps_render_size_to_word_emu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    template_path = tmp_path / "image-size-template.docx"
    output_path = tmp_path / "outputs" / "image-size-rendered.docx"
    image_path = tmp_path / "dpi-sensitive-photo.png"

    Image.new("RGB", (240, 120), color="navy").save(image_path, dpi=(144, 144))

    document = Document()
    document.add_paragraph("{现场照片}")
    document.save(template_path)

    module = import_module("doctransai.renderers.docx")

    def _fake_resolve(*args, **kwargs) -> ResolvedImagePlacement:
        del args, kwargs
        return ResolvedImagePlacement(
            slot_id="slot-photo",
            asset_id="asset-photo",
            source_ref=str(image_path),
            asset_path=image_path,
            intrinsic_size=ImageSize(width=240.0, height=120.0),
            render_size=ImageSize(width=96.0, height=48.0),
        )

    monkeypatch.setattr(module, "resolve_image_placement", _fake_resolve)

    result = module.DocxRenderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            image_placements=[
                ImagePlacement(
                    slot_id="slot-photo",
                    asset_id="asset-photo",
                    source_ref=str(image_path),
                    target=TargetRef(
                        format_key="docx",
                        target_kind="image_placeholder",
                        paragraph_index=0,
                        notes="现场照片",
                    ),
                )
            ],
        )
    )

    rendered = Document(output_path)
    shape = rendered.inline_shapes[0]

    assert shape.width == Emu(914400)
    assert shape.height == Emu(457200)
    assert result.applied_image_slots == ["slot-photo"]
    assert result.diagnostics == []


def test_docx_renderer_reports_missing_image_asset(tmp_path: Path) -> None:
    template_path = tmp_path / "missing-image-template.docx"
    output_path = tmp_path / "outputs" / "missing-image-rendered.docx"

    document = Document()
    document.add_paragraph("{现场照片}")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            image_placements=[
                ImagePlacement(
                    slot_id="slot-missing-photo",
                    asset_id="asset-missing-photo",
                    source_ref="final_images/missing-photo.png",
                    target=TargetRef(format_key="docx", target_kind="image_placeholder", paragraph_index=0),
                )
            ],
        ),
        bundle_dir=tmp_path / "bundle",
    )

    rendered = Document(output_path)

    assert rendered.paragraphs[0].text == "{现场照片}"
    assert len(rendered.inline_shapes) == 0
    assert result.applied_text_slots == []
    assert result.applied_image_slots == []
    assert [(item.severity, item.code, item.slot_id) for item in result.diagnostics] == [
        ("error", "missing_asset", "slot-missing-photo"),
    ]


def test_docx_renderer_scales_paragraph_image_with_page_box_heuristic(tmp_path: Path) -> None:
    template_path = tmp_path / "image-page-box-template.docx"
    output_path = tmp_path / "outputs" / "image-page-box-rendered.docx"
    image_path = tmp_path / "huge-photo.png"

    Image.new("RGB", (2400, 1800), color="navy").save(image_path)

    document = Document()
    document.add_paragraph("{现场照片}")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            image_placements=[
                ImagePlacement(
                    slot_id="slot-photo",
                    asset_id="asset-photo",
                    source_ref=str(image_path),
                    target=TargetRef(format_key="docx", target_kind="image_placeholder", paragraph_index=0),
                )
            ],
        )
    )

    rendered = Document(output_path)
    section = rendered.sections[0]
    shape = rendered.inline_shapes[0]
    content_width = section.page_width - section.left_margin - section.right_margin

    assert shape.width < Emu(int(round((2400 / 96.0) * 914400)))
    assert shape.width <= content_width
    assert result.diagnostics == []


def test_docx_renderer_scales_table_cell_image_with_cell_width_heuristic(tmp_path: Path) -> None:
    template_path = tmp_path / "image-cell-box-template.docx"
    output_path = tmp_path / "outputs" / "image-cell-box-rendered.docx"
    image_path = tmp_path / "huge-cell-photo.png"

    Image.new("RGB", (2400, 1800), color="navy").save(image_path)

    document = Document()
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).width = Inches(2.0)
    table.cell(0, 0).text = "{现场照片}"
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            image_placements=[
                ImagePlacement(
                    slot_id="slot-photo",
                    asset_id="asset-photo",
                    source_ref=str(image_path),
                    target=TargetRef(format_key="docx", target_kind="image_placeholder", table_index=0, row_index=0, column_index=0),
                )
            ],
        )
    )

    rendered = Document(output_path)
    shape = rendered.inline_shapes[0]
    cell_width = rendered.tables[0].cell(0, 0).width

    assert shape.width < Emu(int(round((2400 / 96.0) * 914400)))
    assert shape.width <= cell_width
    assert result.diagnostics == []


def test_docx_renderer_clones_paragraph_media_region_for_multiple_instances(tmp_path: Path) -> None:
    template_path = tmp_path / "repeat-image-template.docx"
    output_path = tmp_path / "outputs" / "repeat-image-rendered.docx"
    image_one = tmp_path / "现场照片-1.png"
    image_two = tmp_path / "现场照片-2.png"

    Image.new("RGB", (80, 40), color="navy").save(image_one)
    Image.new("RGB", (80, 40), color="green").save(image_two)

    document = Document()
    document.add_paragraph("附件：")
    document.add_paragraph("{隐患照片}")
    document.add_paragraph("{隐患描述}")
    document.add_paragraph("结束")
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-desc@0",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        paragraph_index=2,
                        notes="隐患描述",
                        repeat_region_id="region-1",
                        instance_index=0,
                    ),
                    value="二工区围挡未及时封闭",
                ),
                TextFill(
                    slot_id="slot-desc@1",
                    target=TargetRef(
                        format_key="docx",
                        target_kind="placeholder",
                        paragraph_index=2,
                        notes="隐患描述",
                        repeat_region_id="region-1",
                        instance_index=1,
                    ),
                    value="有村民进入施工现场",
                ),
            ],
            image_placements=[
                ImagePlacement(
                    slot_id="slot-photo@0",
                    asset_id="asset-photo-1",
                    source_ref=str(image_one),
                    target=TargetRef(
                        format_key="docx",
                        target_kind="image_placeholder",
                        paragraph_index=1,
                        notes="隐患照片",
                        repeat_region_id="region-1",
                        instance_index=0,
                    ),
                ),
                ImagePlacement(
                    slot_id="slot-photo@1",
                    asset_id="asset-photo-2",
                    source_ref=str(image_two),
                    target=TargetRef(
                        format_key="docx",
                        target_kind="image_placeholder",
                        paragraph_index=1,
                        notes="隐患照片",
                        repeat_region_id="region-1",
                        instance_index=1,
                    ),
                ),
            ],
        )
    )

    rendered = Document(output_path)

    assert [paragraph.text for paragraph in rendered.paragraphs] == [
        "附件：",
        "",
        "二工区围挡未及时封闭",
        "",
        "有村民进入施工现场",
        "结束",
    ]
    assert rendered.paragraphs[1].paragraph_format.keep_with_next is True
    assert rendered.paragraphs[3].paragraph_format.keep_with_next is True
    assert len(rendered.inline_shapes) == 2
    assert result.applied_text_slots == ["slot-desc@0", "slot-desc@1"]
    assert result.applied_image_slots == ["slot-photo@0", "slot-photo@1"]
    assert result.diagnostics == []


def test_docx_renderer_refuses_unsafe_paragraph_markup_and_preserves_placeholder(tmp_path: Path) -> None:
    template_path = tmp_path / "unsafe-template.docx"
    output_path = tmp_path / "outputs" / "unsafe-rendered.docx"

    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("{姓名}")
    unsupported = OxmlElement("w:customXml")
    unsupported.set(qn("w:element"), "unsafe")
    paragraph._p.append(unsupported)
    document.save(template_path)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-name",
                    target=TargetRef(format_key="docx", target_kind="placeholder", paragraph_index=0),
                    value="张三",
                )
            ],
        )
    )

    rendered = Document(output_path)

    assert rendered.paragraphs[0].text == "{姓名}"
    assert result.applied_text_slots == []
    assert [(item.code, item.slot_id) for item in result.diagnostics] == [
        ("unsafe_paragraph_markup", "slot-name"),
    ]


def test_docx_renderer_marks_word_fields_for_refresh_on_open(tmp_path: Path) -> None:
    template_path = tmp_path / "field-template.docx"
    output_path = tmp_path / "outputs" / "field-rendered.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.save(template_path)

    _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-project-name",
                    target=TargetRef(format_key="docx", target_kind="placeholder", paragraph_index=0),
                    value="新计划",
                )
            ],
        )
    )

    with zipfile.ZipFile(output_path, "r") as archive:
        settings_xml = archive.read("word/settings.xml")
    root = ET.fromstring(settings_xml)
    update_fields = root.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}updateFields")

    assert update_fields is not None
    assert update_fields.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") == "true"


def test_docx_renderer_prunes_orphaned_media_parts_after_render(tmp_path: Path) -> None:
    template_path = tmp_path / "orphan-media-template.docx"
    output_path = tmp_path / "outputs" / "orphan-media-rendered.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.save(template_path)

    with zipfile.ZipFile(template_path, "r") as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    rels_root = ET.fromstring(contents["word/_rels/document.xml.rels"])
    relationship = ET.SubElement(rels_root, "Relationship")
    relationship.set("Id", "rIdOrphan")
    relationship.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image")
    relationship.set("Target", "media/orphan.png")
    contents["word/_rels/document.xml.rels"] = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)
    contents["word/media/orphan.png"] = b"orphaned-image"
    with zipfile.ZipFile(template_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in contents.items():
            archive.writestr(name, payload)

    result = _renderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-project",
                    target=TargetRef(format_key="docx", target_kind="placeholder", paragraph_index=0, notes="项目名称"),
                    value="新项目",
                )
            ],
        )
    )

    with zipfile.ZipFile(output_path, "r") as archive:
        media_parts = [name for name in archive.namelist() if name.startswith("word/media/")]

    assert media_parts == []
    assert result.applied_text_slots == ["slot-project"]
    assert result.diagnostics == []
