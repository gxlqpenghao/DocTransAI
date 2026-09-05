from __future__ import annotations

import json
from pathlib import Path

from docx import Document

from doctransai.workflows.agentic_conversion import run_agentic_conversion


def test_agentic_skeleton_places_existing_source_image_in_docx_template(tmp_path: Path) -> None:
    bundle_path = Path(
        "artifacts/dataproxy_fresh_probe_20260526_expanded_candidates_after_xlsx_fix/parsed_document_bundle.json"
    ).resolve()
    source_file_path = Path(
        "V1文档审核集/06_扩展样本候选_文件类型汇总/01_候选源文档_Source/"
        "S01_DOCX冬季专项检查通报/关于11月份冬季施工专项检查情况的通报.docx"
    ).resolve()
    template_path = Path(
        "V1文档审核集/06_扩展样本候选_文件类型汇总/02_候选模板_Template/"
        "T02_DOCX安全隐患整改通知单/安全隐患整改通单（项目）.docx"
    ).resolve()
    output_path = tmp_path / "image-fill.docx"

    def fake_client(*, user_prompt: str, **kwargs) -> str:
        payload = json.loads(user_prompt.split("INPUT_JSON:", 1)[1])
        evidence_package = payload["evidence_package"]
        image_asset = next(
            item
            for item in evidence_package["source"]["structured"]["image_assets"]
            if item.get("asset_id") and item.get("source_ref")
        )
        image_slot = next(
            slot
            for slot in evidence_package["template"]["structured"]["slots"]
            if slot.get("slot_kind") == "image"
        )
        return json.dumps(
            {
                "decisions": [
                    {
                        "slot_id": image_slot["slot_id"],
                        "decision": "image_placement",
                        "asset_id": image_asset["asset_id"],
                        "source_ref": image_asset["source_ref"],
                        "source_refs": [f"image_asset:{image_asset['asset_id']}"],
                        "target_ref": f"template_slot:{image_slot['slot_id']}",
                        "reason": "source image asset directly supports the template image slot",
                    }
                ]
            },
            ensure_ascii=False,
        )

    result = run_agentic_conversion(
        bundle_path=bundle_path,
        source_file_path=source_file_path,
        template_path=template_path,
        output_path=output_path,
        decision_client=fake_client,
        source_page_images=[],
        template_page_images=[],
    )

    rendered = Document(output_path)
    image_relationships = [
        relationship
        for relationship in rendered.part.rels.values()
        if "image" in relationship.reltype
    ]

    assert result.render_result.applied_image_slots == ["docx-paragraph-0"]
    assert result.render_result.diagnostics == []
    assert result.audit_report["counts"]["image_placements"] == 1
    assert result.audit_report["counts"]["unresolved_slots"] == 12
    assert len(image_relationships) == 1
