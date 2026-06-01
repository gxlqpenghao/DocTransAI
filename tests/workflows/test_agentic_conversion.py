from __future__ import annotations

import json
from pathlib import Path

import doctransai.workflows.agentic_conversion as workflow_module
from docx import Document

from doctransai.workflows.agentic_conversion import run_agentic_conversion


def test_run_agentic_conversion_builds_channel_and_renders_docx(tmp_path: Path, monkeypatch) -> None:
    bundle_path = Path("artifacts/dataproxy_fresh_probe_20260521/parsed_document_bundle.json").resolve()
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("项目：{项目名称}")
    document.add_paragraph("隐患：{隐患描述}")
    document.save(template_path)

    monkeypatch.setattr(
        workflow_module,
        "render_template_visual_pages",
        lambda *args, **kwargs: [tmp_path / "source-page-1.png"],
    )

    def fake_client(*, system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:", 1)[1])
        slots = payload["evidence_package"]["template"]["structured"]["slots"]
        slot_by_name = {slot["raw_name"]: slot["slot_id"] for slot in slots}
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": slot_by_name["项目名称"],
                        "decision": "text_fill",
                        "value": "西香TJ3标",
                        "source_refs": ["source_value:ev_951ab1a48f52:0"],
                        "target_ref": f"template_slot:{slot_by_name['项目名称']}",
                        "confidence": 0.9,
                        "reason": "source structured row contains 项目名称=西香TJ3标",
                    },
                    {
                        "slot_id": slot_by_name["隐患描述"],
                        "decision": "text_fill",
                        "value": "电线杂乱",
                        "source_refs": ["source_value:ev_951ab1a48f52:0"],
                        "target_ref": f"template_slot:{slot_by_name['隐患描述']}",
                        "confidence": 0.9,
                        "reason": "source structured row contains 隐患描述=电线杂乱",
                    },
                ]
            },
            ensure_ascii=False,
        )

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=fake_client,
        template_page_images=[{"image_ref": "/tmp/template-page-1.png", "page_index": 0}],
    )

    rendered = Document(output_path)
    report = json.loads(output_path.with_suffix(".agentic_report.json").read_text(encoding="utf-8"))

    assert rendered.paragraphs[0].text == "项目：西香TJ3标"
    assert rendered.paragraphs[1].text == "隐患：电线杂乱"
    assert result.render_result.applied_text_slots == ["docx-paragraph-0", "docx-paragraph-1"]
    assert report["status"]["render_successful"] is True
    assert report["counts"]["accepted_decisions"] == 2
    assert report["counts"]["rejected_decisions"] == 0
    assert report["counts"]["source_page_images"] >= 1
    assert report["counts"]["template_page_images"] == 1
    assert report["input_gaps"]["source"] == []
    assert report["input_gaps"]["template"] == []
