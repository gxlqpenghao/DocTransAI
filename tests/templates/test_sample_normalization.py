from __future__ import annotations

from pathlib import Path
import zipfile

from docx import Document
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from PIL import Image

from doctransai.templates import analyze_template, normalize_sample_template


def _docx_media_parts(path: Path) -> list[str]:
    with zipfile.ZipFile(path, "r") as archive:
        return [name for name in archive.namelist() if name.startswith("word/media/")]


def test_normalize_xlsx_sample_template_placeholderizes_sample_row_and_preserves_static_rows(tmp_path: Path) -> None:
    template_path = tmp_path / "filled-register.xlsx"
    output_path = tmp_path / "outputs" / "result.xlsx"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "登记表"
    worksheet.append(["项目登记表", None, None, None, None])
    worksheet.append(["序号", "项目名称", "事项说明", "现场图片", "处理要求"])
    worksheet.append([1, "南宁项目", "路基沉降", None, "加固处理"])
    worksheet.append([2, "固定保留项目", "固定保留事项", None, "固定保留要求"])
    worksheet["B3"].font = Font(bold=True)
    workbook.save(template_path)

    result = normalize_sample_template(template_path, output_path, enabled=True)
    normalized_workbook = load_workbook(result.analysis_template_path)
    normalized_sheet = normalized_workbook["登记表"]
    model = analyze_template(result.analysis_template_path)

    assert result.analysis_template_path != template_path.resolve()
    assert result.metadata["strategy"] == "sample_template_normalization"
    assert normalized_sheet["B3"].value == "{项目名称}"
    assert normalized_sheet["B3"].font.bold is True
    assert normalized_sheet["E4"].value == "固定保留要求"

    text_slots = {slot.raw_name: slot for slot in model.slots if slot.slot_kind == "text"}
    assert {"序号", "项目名称", "事项说明", "处理要求"}.issubset(text_slots)
    assert text_slots["项目名称"].address.cell_ref == "B3"
    assert [slot.raw_name for slot in model.slots if slot.slot_kind == "image"] == ["现场图片"]


def test_normalize_docx_sample_preserves_top_level_static_images(tmp_path: Path) -> None:
    template_path = tmp_path / "reference-with-logo.docx"
    output_path = tmp_path / "outputs" / "result.docx"
    image_path = tmp_path / "logo.png"

    Image.new("RGB", (80, 40), color="teal").save(image_path)
    document = Document()
    document.add_paragraph().add_run().add_picture(str(image_path))
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "项目名称：样例项目"
    document.save(template_path)

    result = normalize_sample_template(template_path, output_path, enabled=True)

    assert result.metadata["removed_image_count"] == 0
    assert len(_docx_media_parts(result.analysis_template_path)) == 1
    assert "{项目名称}" in Document(result.analysis_template_path).tables[0].cell(0, 0).text


def test_normalize_docx_sample_preserves_fixed_section_instructions_and_cell_images(tmp_path: Path) -> None:
    template_path = tmp_path / "reference-with-instructions.docx"
    output_path = tmp_path / "outputs" / "result.docx"
    image_path = tmp_path / "static-guide.png"

    Image.new("RGB", (80, 40), color="gray").save(image_path)
    document = Document()
    table = document.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    cell.text = (
        "一、填写说明\n"
        "请按本表字段完整填写，内容应真实准确。\n\n"
        "二、固定条款\n"
        "本表经确认后作为双方记录留存。"
    )
    cell.add_paragraph().add_run().add_picture(str(image_path))
    document.save(template_path)

    result = normalize_sample_template(template_path, output_path, enabled=True)
    normalized_cell_text = Document(result.analysis_template_path).tables[0].cell(0, 0).text

    assert result.metadata["normalized_docx_cell_count"] == 0
    assert result.metadata["removed_image_count"] == 0
    assert "请按本表字段完整填写，内容应真实准确。" in normalized_cell_text
    assert "本表经确认后作为双方记录留存。" in normalized_cell_text
    assert "{填写说明}" not in normalized_cell_text
    assert len(_docx_media_parts(result.analysis_template_path)) == 1


def test_normalize_docx_sample_replaces_generic_filled_sections_with_slots(tmp_path: Path) -> None:
    template_path = tmp_path / "filled-reference.docx"
    output_path = tmp_path / "outputs" / "result.docx"

    document = Document()
    document.add_paragraph("项目处理反馈表")
    table = document.add_table(rows=2, cols=1)
    table.cell(0, 0).text = (
        "接收单位：样例接收方\n"
        "来文名称：样例通知\n"
        "联系人：样例联系人"
    )
    table.cell(1, 0).text = (
        "一、事项说明\n"
        "1、这里是第一条事项。\n"
        "2、这里是第二条事项。\n\n"
        "二、处理方案\n"
        "1、这里是第一条方案。\n"
        "2、这里是第二条方案。"
    )
    document.save(template_path)

    result = normalize_sample_template(template_path, output_path, enabled=True)
    normalized = Document(result.analysis_template_path)
    normalized_text = "\n".join(paragraph.text for paragraph in normalized.tables[0].cell(1, 0).paragraphs)
    model = analyze_template(result.analysis_template_path)

    assert result.metadata["normalized_docx_cell_count"] == 2
    assert "这里是第一条事项" not in normalized_text
    assert "{事项说明}" in normalized.tables[0].cell(1, 0).text
    assert "{处理方案}" in normalized.tables[0].cell(1, 0).text
    assert "{接收单位}" in normalized.tables[0].cell(0, 0).text

    slots = {slot.raw_name: slot for slot in model.slots}
    assert {
        "接收单位",
        "来文名称",
        "联系人",
        "事项说明",
        "处理方案",
    }.issubset(slots)


def test_normalize_docx_sample_removes_unreferenced_media_parts(tmp_path: Path) -> None:
    template_path = tmp_path / "filled-reference-with-images.docx"
    output_path = tmp_path / "outputs" / "result.docx"
    image_path = tmp_path / "sample-photo.png"

    Image.new("RGB", (80, 40), color="navy").save(image_path)
    document = Document()
    table = document.add_table(rows=1, cols=1)
    issue_cell = table.cell(0, 0)
    issue_cell.text = (
        "一、事项说明\n"
        "1、这里是事项。\n\n"
        "二、处理方案\n"
        "1、这里是方案。"
    )
    issue_cell.add_paragraph().add_run().add_picture(str(image_path))
    document.save(template_path)

    result = normalize_sample_template(template_path, output_path, enabled=True)

    assert result.metadata["removed_image_count"] == 1
    assert result.metadata["removed_media_part_count"] == 1
    assert "{处理方案图片}" in Document(result.analysis_template_path).tables[0].cell(0, 0).text
    assert _docx_media_parts(result.analysis_template_path) == []


def test_normalize_sample_template_is_noop_when_disabled(tmp_path: Path) -> None:
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "outputs" / "result.docx"
    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.save(template_path)

    result = normalize_sample_template(template_path, output_path, enabled=False)

    assert result.analysis_template_path == template_path.resolve()
    assert result.metadata["strategy"] == "sample_normalization_disabled"
