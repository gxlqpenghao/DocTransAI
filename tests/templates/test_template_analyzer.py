from __future__ import annotations

from pathlib import Path

from docx import Document
from openpyxl import Workbook

from doctransai.templates import analyze_template


def test_docx_analyzer_extracts_placeholders_across_runs_and_tables(tmp_path: Path) -> None:
    template_path = tmp_path / "project-template.docx"

    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("项目名称：")
    paragraph.add_run("{项")
    paragraph.add_run("目名称}")

    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "负责人：{负责人}"
    document.save(template_path)

    model = analyze_template(template_path)

    assert model.format_key == "docx"
    assert model.analyzer_key == "docx_template"
    assert [(slot.raw_name, slot.address.address_kind) for slot in model.slots] == [
        ("项目名称", "paragraph"),
        ("负责人", "table_cell"),
    ]
    assert model.slots[0].address.paragraph_index == 0
    assert model.slots[1].address.table_index == 0
    assert model.slots[1].address.row_index == 0
    assert model.slots[1].address.column_index == 0


def test_docx_analyzer_deduplicates_placeholders_in_merged_cells(tmp_path: Path) -> None:
    template_path = tmp_path / "merged-template.docx"

    document = Document()
    table = document.add_table(rows=1, cols=3)
    merged = table.cell(0, 0).merge(table.cell(0, 2))
    merged.text = "{责任单位}"
    document.save(template_path)

    model = analyze_template(template_path)

    assert [(slot.raw_name, slot.address.row_index, slot.address.column_index) for slot in model.slots] == [
        ("责任单位", 0, 0),
    ]


def test_docx_analyzer_uses_neighbor_cells_as_context_for_table_slots(tmp_path: Path) -> None:
    template_path = tmp_path / "context-template.docx"

    document = Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "签发人"
    table.cell(0, 1).text = "{人员姓名}"
    document.save(template_path)

    model = analyze_template(template_path)

    assert [(slot.raw_name, slot.context_before, slot.context_after) for slot in model.slots] == [
        ("人员姓名", "签发人", None),
    ]


def test_docx_analyzer_tracks_paragraph_index_inside_table_cell(tmp_path: Path) -> None:
    template_path = tmp_path / "multi-paragraph-cell-template.docx"

    document = Document()
    table = document.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    cell.paragraphs[0].add_run("项目：{项目名称}")
    cell.add_paragraph("单位：{责任单位}")
    document.save(template_path)

    model = analyze_template(template_path)

    assert [(slot.raw_name, slot.address.cell_paragraph_index) for slot in model.slots] == [
        ("项目名称", 0),
        ("责任单位", 1),
    ]


def test_docx_analyzer_marks_numbered_list_placeholders_as_multi_value_slots(tmp_path: Path) -> None:
    template_path = tmp_path / "numbered-list-template.docx"

    document = Document()
    table = document.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    cell.paragraphs[0].text = "安全问题（隐患）内容："
    cell.add_paragraph("{隐患描述}", style="List Number")
    document.save(template_path)

    model = analyze_template(template_path)

    slot = next(item for item in model.slots if item.raw_name == "隐患描述")

    assert slot.placement_constraints == {
        "list_item": True,
        "list_style": "numbered",
        "multi_value_allowed": True,
    }


def test_docx_analyzer_ignores_static_notice_body_paragraphs(tmp_path: Path) -> None:
    template_path = tmp_path / "notice-template.docx"

    document = Document()
    document.add_paragraph("安全隐患整改通知单")
    document.add_paragraph("经检查发现，你单位施工现场存在安全隐患，请按要求整改。")
    document.add_paragraph("Picture 1")
    document.add_paragraph("{隐患照片}")
    document.add_paragraph("{隐患描述}", style="List Number")
    document.save(template_path)

    model = analyze_template(template_path)

    assert [(slot.raw_name, slot.slot_kind, slot.address.paragraph_index) for slot in model.slots] == [
        ("隐患照片", "image", 3),
        ("隐患描述", "text", 4),
    ]
    assert all("安全隐患整改通知单" not in slot.raw_name for slot in model.slots)
    assert all("Picture 1" not in slot.raw_name for slot in model.slots)
    assert model.slots[1].placement_constraints == {
        "list_item": True,
        "list_style": "numbered",
        "multi_value_allowed": True,
    }


def test_docx_analyzer_treats_photo_description_placeholder_as_text(tmp_path: Path) -> None:
    template_path = tmp_path / "photo-description-template.docx"

    document = Document()
    document.add_paragraph("{整改照片}")
    document.add_paragraph("{整改照片说明}")
    document.save(template_path)

    model = analyze_template(template_path)
    slots = {slot.raw_name: slot for slot in model.slots}

    assert slots["整改照片"].slot_kind == "image"
    assert slots["整改照片说明"].slot_kind == "text"


def test_docx_analyzer_marks_table_cell_media_area_as_repeatable(tmp_path: Path) -> None:
    template_path = tmp_path / "table-cell-media-area-template.docx"

    document = Document()
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "一、存在问题\n{存在问题}\n\n{整改照片}\n{整改照片说明}"
    document.save(template_path)

    model = analyze_template(template_path)
    slots = {slot.raw_name: slot for slot in model.slots}

    assert slots["整改照片"].placement_constraints["multi_value_allowed"] is True
    assert slots["整改照片"].placement_constraints["media_group_role"] == "image"
    assert slots["整改照片说明"].placement_constraints["media_group_role"] == "caption"
    assert slots["整改照片说明"].placement_constraints["paired_image_slot_id"] == slots["整改照片"].slot_id


def test_docx_analyzer_detects_underlined_fill_blanks_as_slots(tmp_path: Path) -> None:
    template_path = tmp_path / "underlined-blank-template.docx"

    document = Document()
    table = document.add_table(rows=1, cols=1)
    paragraph = table.cell(0, 0).paragraphs[0]
    paragraph.add_run("项目安全管理部 于")
    blank = paragraph.add_run("        ")
    blank.underline = True
    paragraph.add_run("对你劳务队进行安全检查，现要求你劳务队于")
    deadline = paragraph.add_run("       ")
    deadline.underline = True
    paragraph.add_run("前整改完毕。")
    document.save(template_path)

    model = analyze_template(template_path)

    implicit_slots = [slot for slot in model.slots if slot.mode == "implicit_blank"]

    assert [(slot.raw_name, slot.address.run_index, slot.address.run_end_index) for slot in implicit_slots] == [
        ("datetime_blank_1", 1, 1),
        ("datetime_deadline_blank_2", 3, 3),
    ]
    assert implicit_slots[0].context_before.endswith("于")
    assert implicit_slots[0].context_after.startswith("对你劳务队")
    assert implicit_slots[0].placement_constraints == {
        "inferred_value_type": "datetime",
        "temporal_granularity": "date_or_datetime",
    }
    assert implicit_slots[1].placement_constraints == {
        "inferred_value_type": "datetime",
        "temporal_granularity": "deadline_phrase",
    }


def test_docx_analyzer_names_generic_underlined_blanks_from_nearby_label(tmp_path: Path) -> None:
    template_path = tmp_path / "signature-blank-template.docx"

    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("项目监理机构（章）：")
    blank = paragraph.add_run("        ")
    blank.underline = True
    paragraph.add_run("    总监理工程师：")
    signature = paragraph.add_run("        ")
    signature.underline = True
    document.save(template_path)

    model = analyze_template(template_path)

    implicit_slots = [slot for slot in model.slots if slot.mode == "implicit_blank"]

    assert [(slot.raw_name, slot.canonical_name) for slot in implicit_slots] == [
        ("项目监理机构", "项目监理机构"),
        ("总监理工程师", "总监理工程师"),
    ]
    assert [slot.placement_constraints["label_source"] for slot in implicit_slots] == [
        "context_before",
        "context_before",
    ]


def test_docx_analyzer_treats_empty_cell_after_label_as_writable_slot(tmp_path: Path) -> None:
    template_path = tmp_path / "label-blank-cell-template.docx"

    document = Document()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "责任单位："
    table.cell(0, 1).text = ""
    table.cell(1, 0).text = "整改期限"
    table.cell(1, 1).text = ""
    document.save(template_path)

    model = analyze_template(template_path)

    blank_slots = [slot for slot in model.slots if slot.mode == "table_cell_blank"]

    assert [(slot.raw_name, slot.address.address_kind, slot.address.row_index, slot.address.column_index) for slot in blank_slots] == [
        ("责任单位", "table_cell_blank", 0, 1),
        ("整改期限", "table_cell_blank", 1, 1),
    ]
    assert [slot.context_before for slot in blank_slots] == ["责任单位", "整改期限"]
    assert blank_slots[0].placement_constraints == {
        "inferred_value_type": "text",
        "label_source": "left_cell",
    }
    assert blank_slots[1].placement_constraints == {
        "inferred_value_type": "datetime",
        "label_source": "left_cell",
        "temporal_granularity": "deadline_phrase",
    }


def test_docx_analyzer_treats_blank_row_after_headers_as_writable_slots(tmp_path: Path) -> None:
    template_path = tmp_path / "header-blank-row-template.docx"

    document = Document()
    table = document.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "姓名"
    table.cell(0, 1).text = "联系电话"
    table.cell(0, 2).text = "照片"
    for column_index in range(3):
        table.cell(1, column_index).text = ""
    document.save(template_path)

    model = analyze_template(template_path)

    blank_slots = [slot for slot in model.slots if slot.mode == "table_cell_blank"]

    assert [(slot.raw_name, slot.slot_kind, slot.address.row_index, slot.address.column_index) for slot in blank_slots] == [
        ("姓名", "text", 1, 0),
        ("联系电话", "text", 1, 1),
        ("照片", "image", 1, 2),
    ]
    assert [slot.context_before for slot in blank_slots] == ["姓名", "联系电话", "照片"]
    assert blank_slots[0].placement_constraints == {
        "header_name": "姓名",
        "inferred_value_type": "person_name",
        "label_source": "header_cell",
    }
    assert blank_slots[1].placement_constraints == {
        "header_name": "联系电话",
        "inferred_value_type": "phone",
        "label_source": "header_cell",
    }
    assert blank_slots[2].placement_constraints == {
        "header_name": "照片",
        "inferred_value_type": "image",
        "label_source": "header_cell",
    }


def test_docx_analyzer_treats_instruction_cell_after_label_as_writable_slot(tmp_path: Path) -> None:
    template_path = tmp_path / "instruction-cell-template.docx"

    document = Document()
    table = document.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "成果简介"
    table.cell(0, 1).text = "（500字以内，简要说明研究背景、主要创新点、应用场景及成效）"
    table.cell(1, 0).text = "创新点"
    table.cell(1, 1).text = "（详细说明成果在技术、工艺、材料、理念等方面的创新之处）"
    table.cell(2, 0).text = "所属领域"
    table.cell(2, 1).text = "□智能建造□建筑节能□其他（注明：__________）"
    document.save(template_path)

    model = analyze_template(template_path)

    instruction_slots = [slot for slot in model.slots if slot.mode == "table_cell_instruction"]
    choice_slots = [slot for slot in model.slots if slot.mode == "table_cell_choice"]

    assert [(slot.raw_name, slot.address.address_kind, slot.address.row_index, slot.address.column_index) for slot in instruction_slots] == [
        ("成果简介", "table_cell_instruction", 0, 1),
        ("创新点", "table_cell_instruction", 1, 1),
    ]
    assert instruction_slots[0].placement_constraints == {
        "inferred_value_type": "long_text",
        "instruction_text": "（500字以内，简要说明研究背景、主要创新点、应用场景及成效）",
        "label_source": "left_cell",
    }
    assert [(slot.raw_name, slot.address.address_kind, slot.address.row_index, slot.address.column_index) for slot in choice_slots] == [
        ("所属领域", "table_cell_choice", 2, 1),
    ]
    choice_constraints = choice_slots[0].placement_constraints
    assert choice_constraints["inferred_value_type"] == "choice"
    assert choice_constraints["label_source"] == "left_cell"
    assert choice_constraints["choices"] == ["智能建造", "建筑节能", "其他"]
    assert choice_constraints["choice_options"] == [
        {
            "label": "智能建造",
            "raw_text": "智能建造",
        },
        {
            "label": "建筑节能",
            "raw_text": "建筑节能",
        },
        {
            "label": "其他",
            "raw_text": "其他（注明：__________）",
            "has_detail_blank": True,
            "detail_prompt": "注明",
        },
    ]


def test_docx_analyzer_keeps_all_instruction_rows_in_merged_table_cells(tmp_path: Path) -> None:
    template_path = tmp_path / "scitech-instruction-template.docx"

    document = Document()
    table = document.add_table(rows=12, cols=4)

    table.cell(0, 0).merge(table.cell(0, 3)).text = "一、基本信息"
    table.cell(1, 0).text = "成果名称"
    table.cell(1, 1).merge(table.cell(1, 3)).text = ""
    table.cell(2, 0).text = "单位名称"
    table.cell(2, 1).merge(table.cell(2, 3)).text = ""
    table.cell(3, 0).text = "成果完成时间"
    table.cell(3, 1).text = ""
    table.cell(3, 2).text = "成果应用时间"
    table.cell(3, 3).text = ""
    table.cell(4, 0).text = "获奖情况"
    table.cell(4, 1).merge(table.cell(4, 3)).text = "（奖项名称、级别、颁奖单位、时间）"
    table.cell(5, 0).text = "成果简介"
    table.cell(5, 1).merge(table.cell(5, 3)).text = "（500字以内，简要说明研究背景、主要创新点、应用场景及成效）"
    table.cell(6, 0).merge(table.cell(6, 3)).text = "二、成果详细情况"
    table.cell(7, 0).text = "创新点"
    table.cell(7, 1).merge(table.cell(7, 3)).text = "（详细说明成果在技术、工艺、材料、理念等方面的创新之处）"
    table.cell(8, 0).text = "落地应用情况"
    table.cell(8, 1).merge(table.cell(8, 3)).text = "（说明应用项目名称、地点、规模、应用效果，经济、社会、生态效益数据，推广前景分析）"
    table.cell(9, 0).text = "知识产权情况"
    table.cell(9, 1).merge(table.cell(9, 3)).text = "（专利、软件著作权、工法、标准等名称、编号、授权/发布单位、时间）"
    table.cell(10, 0).merge(table.cell(10, 3)).text = "三、单位意见"
    table.cell(11, 0).text = "单位意见"
    table.cell(11, 1).merge(table.cell(11, 3)).text = "本单位确认，所申报成果材料真实、准确、完整。"
    document.save(template_path)

    expected_instruction_names = {"获奖情况", "成果简介", "创新点", "落地应用情况", "知识产权情况"}

    for _ in range(10):
        model = analyze_template(template_path)
        instruction_names = {slot.raw_name for slot in model.slots if slot.mode == "table_cell_instruction"}

        assert expected_instruction_names.issubset(instruction_names)


def test_docx_analyzer_marks_paragraph_image_and_following_text_as_repeat_region(tmp_path: Path) -> None:
    template_path = tmp_path / "media-repeat-template.docx"

    document = Document()
    document.add_paragraph("附件：")
    document.add_paragraph("{隐患照片}")
    document.add_paragraph("{隐患描述}")
    document.add_paragraph("后续说明")
    document.save(template_path)

    model = analyze_template(template_path)

    assert len(model.repeat_regions) == 1
    region = model.repeat_regions[0]
    assert region.region_kind == "docx_paragraph_media_region"
    assert region.address.paragraph_index == 1

    slots_by_name = {slot.raw_name: slot for slot in model.slots}
    assert slots_by_name["隐患照片"].repeat_region_id == region.region_id
    assert slots_by_name["隐患描述"].repeat_region_id == region.region_id


def test_xlsx_analyzer_detects_header_region_and_photo_column(tmp_path: Path) -> None:
    template_path = tmp_path / "roster-template.xlsx"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "人员信息"
    worksheet.append(["姓名", "照片", "部门"])
    worksheet.append(["{姓名}", "", "{部门}"])
    workbook.save(template_path)

    model = analyze_template(template_path)

    assert model.format_key == "xlsx"
    assert model.analyzer_key == "xlsx_template"
    assert len(model.header_regions) == 1

    region = model.header_regions[0]
    assert region.sheet_name == "人员信息"
    assert region.header_row_index == 0
    assert region.sample_row_index == 1
    assert region.column_names == ["姓名", "照片", "部门"]

    text_slots = {slot.raw_name: slot for slot in model.slots if slot.slot_kind == "text"}
    assert text_slots["姓名"].repeat_region_id == region.region_id
    assert text_slots["姓名"].address.cell_ref == "A2"
    assert text_slots["部门"].address.cell_ref == "C2"

    image_slots = [slot for slot in model.slots if slot.slot_kind == "image"]
    assert len(image_slots) == 1
    assert image_slots[0].raw_name == "照片"
    assert image_slots[0].mode == "header_column"
    assert image_slots[0].repeat_region_id == region.region_id
    assert image_slots[0].address.sheet_name == "人员信息"
    assert image_slots[0].address.cell_ref == "B2"


def test_xlsx_analyzer_treats_blank_row_after_headers_as_writable_region(tmp_path: Path) -> None:
    template_path = tmp_path / "ledger-template.xlsx"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "台账"
    worksheet.append(["序号", "项目名称", "隐患描述", "隐患照片", "整改要求"])
    worksheet.append([None, None, None, None, None])
    workbook.save(template_path)

    model = analyze_template(template_path)

    assert len(model.header_regions) == 1
    region = model.header_regions[0]
    assert region.header_row_index == 0
    assert region.sample_row_index == 1

    text_slots = {slot.raw_name: slot for slot in model.slots if slot.slot_kind == "text"}
    assert {"序号", "项目名称", "隐患描述", "整改要求"}.issubset(text_slots)
    assert text_slots["项目名称"].mode == "header_column"
    assert text_slots["项目名称"].address.cell_ref == "B2"

    image_slots = [slot for slot in model.slots if slot.slot_kind == "image"]
    assert len(image_slots) == 1
    assert image_slots[0].raw_name == "隐患照片"
    assert image_slots[0].address.cell_ref == "D2"


def test_pdf_analyzer_extracts_acroform_fields_without_guessing_other_slots(tmp_path: Path) -> None:
    template_path = tmp_path / "fillable-template.pdf"
    template_path.write_bytes(
        b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /AcroForm 2 0 R >>
endobj
2 0 obj
<< /Fields [3 0 R 4 0 R] >>
endobj
3 0 obj
<< /FT /Tx /T (ProjectName) >>
endobj
4 0 obj
<< /FT /Tx /T (Owner) >>
endobj
trailer
<< /Root 1 0 R >>
%%EOF
""",
    )

    model = analyze_template(template_path)

    assert model.format_key == "pdf"
    assert model.analyzer_key == "pdf_template"
    assert [slot.raw_name for slot in model.slots] == ["ProjectName", "Owner"]
    assert all(slot.address.address_kind == "form_field" for slot in model.slots)
    assert [slot.address.form_field_name for slot in model.slots] == ["ProjectName", "Owner"]


def test_pdf_analyzer_reports_conservative_diagnostic_when_no_form_fields_exist(tmp_path: Path) -> None:
    template_path = tmp_path / "static-template.pdf"
    template_path.write_bytes(
        b"""%PDF-1.4
1 0 obj
<< /Type /Catalog >>
endobj
2 0 obj
<< /Type /Page >>
endobj
%%EOF
""",
    )

    model = analyze_template(template_path)

    assert model.slots == []
    assert [(item.severity, item.code) for item in model.diagnostics] == [
        ("info", "pdf_analysis_limited"),
    ]
