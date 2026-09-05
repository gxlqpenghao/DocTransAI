from __future__ import annotations

from docx import Document

from doctransai.agentic_mapping.visual_targets import resolve_visual_target_mapping
from doctransai.templates import analyze_template


def test_resolve_docx_visual_text_anchor_uses_later_match_for_later_page_hint(tmp_path) -> None:
    template_path = tmp_path / "date-visual-target.docx"

    document = Document()
    document.add_paragraph("接收日期：    年   月   日   时     编号：")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "（公章）"
    table.cell(0, 0).add_paragraph("                                       年    月    日")
    document.save(template_path)

    template_model = analyze_template(template_path)

    resolved = resolve_visual_target_mapping(
        {
            "format_key": "docx",
            "target_kind": "visual_text_anchor",
            "label_or_nearby_text": "年 月 日",
            "page_index": 1,
            "approx_location": "center-right",
        },
        template_model,
    )

    assert resolved["table_index"] == 0
    assert resolved["row_index"] == 0
    assert resolved["column_index"] == 0
    assert resolved["cell_paragraph_index"] == 1
