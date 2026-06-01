from __future__ import annotations

import json
from pathlib import Path

from docx import Document

from doctransai.workflows.agentic_conversion import run_agentic_conversion


def test_agentic_skeleton_fills_source_existing_text_from_word_table(tmp_path: Path) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260525_all_sources_latest/parsed_document_bundle.json").resolve()
    source_file_path = Path(
        "V1文档审核集/01_被转换文档_Source/02_Word表格源/环资公司安全检查记录表（2022.3.7 核心区纵二路东段、纵三路）.docx"
    ).resolve()
    template_path = Path("V1文档审核集/02_目标模板_Template/01_DOCX整改记录单/安全隐患整改记录单.docx").resolve()
    output_path = tmp_path / "word-table-skeleton.docx"

    def fake_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:", 1)[1])
        slots = payload["evidence_package"]["template"]["structured"]["slots"]
        slot_by_name = {slot["raw_name"]: slot["slot_id"] for slot in slots}
        return json.dumps(
            {
                "decisions": [
                    _text(slot_by_name["项目名称"], "核心区纵二路东段、纵三路、纵六路", "source_value:tblcell_dc87654b070f:0"),
                    _text(slot_by_name["责任单位"], "广西路桥", "source_value:tblcell_556464d8833e:0"),
                    _text(slot_by_name["隐患类型"], "临边防护", "source_value:tblcell_4e615afa9665:0"),
                    _text(
                        slot_by_name["隐患描述"],
                        "箱涵顶板钢筋绑扎作业，周边临边防护缺失，外架、防护未随作业面进度搭设，搭设滞后",
                        "source_value:tblcell_db2ff06c17e8:0",
                    ),
                    _text(
                        slot_by_name["整改要求"],
                        "要求立即完善临边防护搭设，防护随作业面进度搭设",
                        "source_value:tblcell_76a42f36e523:0",
                    ),
                    _text(slot_by_name["整改期限"], "2022.3.12", "source_value:tblcell_eb4794b3c346:0"),
                ]
            },
            ensure_ascii=False,
        )

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        source_file_path=source_file_path,
        decision_client=fake_client,
        source_page_images=[{"image_ref": "/tmp/source-word-table-page-1.png", "page_index": 0}],
        template_page_images=[{"image_ref": "/tmp/template-record-page-1.png", "page_index": 0}],
    )

    rendered_text = "\n".join(paragraph.text for paragraph in Document(output_path).paragraphs)
    for table in Document(output_path).tables:
        for row in table.rows:
            rendered_text += "\n" + "\t".join(cell.text for cell in row.cells)

    assert "核心区纵二路东段、纵三路、纵六路" in rendered_text
    assert "广西路桥" in rendered_text
    assert "临边防护" in rendered_text
    assert "箱涵顶板钢筋绑扎作业" in rendered_text
    assert "要求立即完善临边防护搭设" in rendered_text
    assert "2022.3.12" in rendered_text
    assert len(result.validation_result.rejected_decisions) == 0
    assert len(result.render_plan.text_fills) == 6


def _text(slot_id: str, value: str, source_ref: str) -> dict[str, object]:
    return {
        "slot_id": slot_id,
        "decision": "text_fill",
        "value": value,
        "source_refs": [source_ref],
        "target_ref": f"template_slot:{slot_id}",
        "confidence": 0.9,
        "reason": "source structured table cell supports this fill",
    }
