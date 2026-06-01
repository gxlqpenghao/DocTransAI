from __future__ import annotations

from pathlib import Path
import zipfile

from docx import Document

import doctransai.workflows.v1_conversion as workflow_module
from doctransai.models.mapping import UnresolvedSlot
from doctransai.models.render_plan import ImagePlacement, OutputRef, PlanDiagnostic, RenderPlan, TargetRef, TemplateRef, TextFill
from doctransai.validation.output_checker import OutputArtifactSnapshot, check_output


def _build_plan(*, source_ref: str | None = "final_images/photo-1.jpg") -> RenderPlan:
    return RenderPlan(
        plan_id="plan-1",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/template.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/result.docx", output_format="docx"),
        text_fills=[
            TextFill(
                slot_id="slot-desc",
                target=TargetRef(format_key="docx", target_kind="placeholder", paragraph_index=0),
                value="配电箱未加锁",
            )
        ],
        image_placements=[
            ImagePlacement(
                slot_id="slot-photo",
                asset_id="asset-1",
                source_ref=source_ref,
                target=TargetRef(format_key="docx", target_kind="image_placeholder", paragraph_index=1),
            )
        ],
        unresolved_slots=[
            UnresolvedSlot(
                slot_id="slot-owner",
                canonical_key="责任单位负责人",
                reason_code="missing_value",
                message="没有找到负责人字段",
            )
        ],
    )


def test_output_checker_reports_placeholder_residue_in_text_fragments() -> None:
    result = check_output(
        _build_plan(),
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=["隐患描述：{隐患描述}"],
                applied_text_slots={"slot-desc"},
                applied_image_slots={"slot-photo"},
            )
        ],
    )

    codes = {issue.code for issue in result.issues}

    assert "placeholder_residue" in codes


def test_output_checker_reports_missing_assets_and_unapplied_operations(tmp_path: Path) -> None:
    asset_base_dir = tmp_path / "bundle"
    asset_base_dir.mkdir()
    plan = _build_plan(source_ref="final_images/photo-404.jpg")

    result = check_output(
        plan,
        [OutputArtifactSnapshot(name="result.docx", text_fragments=["隐患描述：配电箱未加锁"])],
        asset_base_dir=asset_base_dir,
    )

    codes = {issue.code for issue in result.issues}

    assert "missing_asset" in codes
    assert "unapplied_text_fill" in codes
    assert "unapplied_image_placement" in codes


def test_output_checker_reports_unresolved_slots_from_plan() -> None:
    result = check_output(
        _build_plan(),
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=["隐患描述：配电箱未加锁"],
                applied_text_slots={"slot-desc"},
                applied_image_slots={"slot-photo"},
            )
        ],
    )

    unresolved_issues = [issue for issue in result.issues if issue.code == "unresolved_slot"]

    assert len(unresolved_issues) == 1
    assert unresolved_issues[0].slot_id == "slot-owner"


def test_output_checker_is_clean_when_operations_apply_and_assets_exist(tmp_path: Path) -> None:
    asset_base_dir = tmp_path / "bundle"
    asset_path = asset_base_dir / "final_images" / "photo-1.jpg"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"fixture")

    result = check_output(
        _build_plan(),
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=["隐患描述：配电箱未加锁"],
                applied_text_slots={"slot-desc"},
                applied_image_slots={"slot-photo"},
            )
        ],
        asset_base_dir=asset_base_dir,
        include_unresolved_slots=False,
    )

    assert result.is_clean is True
    assert result.issues == []


def test_output_checker_finds_asset_under_parsed_checksum_subdirectory(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    asset_path = bundle_dir / "parsed" / "abc123" / "final_images" / "photo-1.jpg"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"fixture")

    result = check_output(
        _build_plan(),
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=["隐患描述：配电箱未加锁"],
                applied_text_slots={"slot-desc"},
                applied_image_slots={"slot-photo"},
            )
        ],
        asset_base_dir=bundle_dir,
        include_unresolved_slots=False,
    )

    assert result.is_clean is True
    assert result.issues == []


def test_output_checker_reports_docx_style_or_image_target_mismatch() -> None:
    plan = _build_plan()
    result = check_output(
        plan,
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=["隐患描述：配电箱未加锁"],
                applied_text_slots={"slot-desc"},
                applied_image_slots={"slot-photo"},
                metadata={
                    "format_key": "docx",
                    "paragraph_count": 2,
                    "table_count": 0,
                    "target_styles": {
                        "paragraph[0]": "Body Text",
                        "paragraph[1]": "Body Text",
                    },
                    "image_targets": [],
                },
            )
        ],
        include_unresolved_slots=False,
        template_artifact=OutputArtifactSnapshot(
            name="template.docx",
            metadata={
                "format_key": "docx",
                "paragraph_count": 2,
                "table_count": 0,
                "target_styles": {
                    "paragraph[0]": "Normal",
                    "paragraph[1]": "Normal",
                },
                "image_targets": ["paragraph[1]"],
            },
        ),
    )

    codes = {issue.code for issue in result.issues}

    assert "template_style_changed" in codes
    assert "image_target_mismatch" in codes


def test_output_checker_uses_cell_paragraph_target_key_for_docx() -> None:
    plan = RenderPlan(
        plan_id="plan-docx-cell-paragraph",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/template.docx", format_key="docx"),
        output=OutputRef(output_path="/outputs/result.docx", output_format="docx"),
        text_fills=[
            TextFill(
                slot_id="slot-owner",
                target=TargetRef(
                    format_key="docx",
                    target_kind="placeholder",
                    table_index=0,
                    row_index=0,
                    column_index=0,
                    cell_paragraph_index=1,
                ),
                value="华东分公司",
            )
        ],
        image_placements=[
            ImagePlacement(
                slot_id="slot-photo",
                asset_id="asset-1",
                source_ref="final_images/photo-1.jpg",
                target=TargetRef(
                    format_key="docx",
                    target_kind="image_placeholder",
                    table_index=0,
                    row_index=0,
                    column_index=0,
                    cell_paragraph_index=1,
                ),
            )
        ],
    )

    result = check_output(
        plan,
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=["项目：测试", "单位：华东分公司"],
                applied_text_slots={"slot-owner"},
                applied_image_slots={"slot-photo"},
                metadata={
                    "format_key": "docx",
                    "paragraph_count": 0,
                    "table_count": 1,
                    "target_styles": {
                        "table[0].cell[0,0].paragraph[1]": "Body Text",
                    },
                    "image_targets": [],
                },
            )
        ],
        include_unresolved_slots=False,
        template_artifact=OutputArtifactSnapshot(
            name="template.docx",
            metadata={
                "format_key": "docx",
                "paragraph_count": 0,
                "table_count": 1,
                "target_styles": {
                    "table[0].cell[0,0].paragraph[1]": "Normal",
                },
                "image_targets": ["table[0].cell[0,0].paragraph[1]"],
            },
        ),
    )

    codes = {issue.code for issue in result.issues}

    assert "template_style_changed" in codes
    assert "image_target_mismatch" in codes


def test_output_checker_reports_docx_table_cell_token_mismatch() -> None:
    plan = _build_plan()

    result = check_output(
        plan,
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=["隐患描述：配电箱未加锁"],
                applied_text_slots={"slot-desc"},
                applied_image_slots={"slot-photo"},
                metadata={
                    "format_key": "docx",
                    "paragraph_count": 2,
                    "table_count": 1,
                    "target_styles": {
                        "paragraph[0]": "Normal",
                        "paragraph[1]": "Normal",
                    },
                    "image_targets": ["paragraph[1]"],
                    "table_cell_tokens": [
                        {"table": 0, "row": 0, "cell": 0, "grid_span": 1, "v_merge": None},
                        {"table": 0, "row": 0, "cell": 1, "grid_span": 1, "v_merge": None},
                    ],
                },
            )
        ],
        include_unresolved_slots=False,
        template_artifact=OutputArtifactSnapshot(
            name="template.docx",
            metadata={
                "format_key": "docx",
                "paragraph_count": 2,
                "table_count": 1,
                "target_styles": {
                    "paragraph[0]": "Normal",
                    "paragraph[1]": "Normal",
                },
                "image_targets": ["paragraph[1]"],
                "table_cell_tokens": [
                    {"table": 0, "row": 0, "cell": 0, "grid_span": 2, "v_merge": None},
                ],
            },
        ),
    )

    structure_issues = [issue for issue in result.issues if issue.code == "template_structure_changed"]

    assert len(structure_issues) == 1
    assert structure_issues[0].message == "DOCX table cell structure changed after rendering."


def test_docx_snapshot_records_table_cell_tokens_without_text_content(tmp_path: Path) -> None:
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output.docx"

    for path, text in [(template_path, "{隐患描述}"), (output_path, "配电箱未加锁")]:
        document = Document()
        table = document.add_table(rows=1, cols=2)
        merged_cell = table.cell(0, 0).merge(table.cell(0, 1))
        merged_cell.text = text
        document.save(path)

    template_snapshot = workflow_module._snapshot_for_path(template_path, format_key="docx")
    output_snapshot = workflow_module._snapshot_for_path(output_path, format_key="docx")

    assert template_snapshot.metadata["table_cell_tokens"] == [
        {"table": 0, "row": 0, "cell": 0, "grid_span": 2, "v_merge": None}
    ]
    assert output_snapshot.metadata["table_cell_tokens"] == template_snapshot.metadata["table_cell_tokens"]


def test_docx_snapshot_distinguishes_visible_drawings_from_orphan_media(tmp_path: Path) -> None:
    output_path = tmp_path / "output.docx"

    document = Document()
    document.add_paragraph("无图片正文")
    document.save(output_path)
    with zipfile.ZipFile(output_path, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/media/orphan.png", b"orphaned-image")

    snapshot = workflow_module._snapshot_for_path(output_path, format_key="docx")

    assert snapshot.metadata["docx_drawing_count"] == 0
    assert snapshot.metadata["docx_media_part_count"] == 1
    assert snapshot.metadata["docx_referenced_media_part_count"] == 0
    assert snapshot.metadata["docx_orphan_media_part_count"] == 1


def test_output_checker_reports_xlsx_structure_or_style_mismatch() -> None:
    plan = RenderPlan(
        plan_id="plan-xlsx",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/template.xlsx", format_key="xlsx"),
        output=OutputRef(output_path="/outputs/result.xlsx", output_format="xlsx"),
        text_fills=[
            TextFill(
                slot_id="slot-name",
                target=TargetRef(format_key="xlsx", target_kind="cell", sheet_name="Sheet0", cell_ref="A2"),
                value="Alice",
            )
        ],
        image_placements=[
            ImagePlacement(
                slot_id="slot-photo",
                asset_id="asset-1",
                source_ref="final_images/photo-1.jpg",
                target=TargetRef(format_key="xlsx", target_kind="cell", sheet_name="Sheet0", cell_ref="B2"),
            )
        ],
    )
    result = check_output(
        plan,
        [
            OutputArtifactSnapshot(
                name="result.xlsx",
                text_fragments=["Alice"],
                applied_text_slots={"slot-name"},
                applied_image_slots={"slot-photo"},
                metadata={
                    "format_key": "xlsx",
                    "sheet_names": ["Sheet0"],
                    "merged_ranges": {"Sheet0": []},
                    "freeze_panes": {"Sheet0": None},
                    "cell_styles": {"Sheet0!A2": 3, "Sheet0!B2": 2},
                    "image_targets": [],
                },
            )
        ],
        include_unresolved_slots=False,
        template_artifact=OutputArtifactSnapshot(
            name="template.xlsx",
            metadata={
                "format_key": "xlsx",
                "sheet_names": ["Sheet0", "Sheet1"],
                "merged_ranges": {"Sheet0": ["A1:B1"]},
                "freeze_panes": {"Sheet0": "A2"},
                "cell_styles": {"Sheet0!A2": 1, "Sheet0!B2": 2},
                "image_targets": ["Sheet0!B2"],
            },
        ),
    )

    codes = {issue.code for issue in result.issues}

    assert "template_structure_changed" in codes
    assert "template_style_changed" in codes
    assert "image_target_mismatch" in codes


def test_output_checker_reports_no_op_when_expected_operations_apply_nothing() -> None:
    result = check_output(
        _build_plan(),
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=["隐患描述："],
                applied_text_slots=set(),
                applied_image_slots=set(),
            )
        ],
        include_unresolved_slots=False,
    )

    codes = {issue.code for issue in result.issues}

    assert "no_op_output" in codes
    assert result.is_clean is False


def test_output_checker_blocks_xlsx_no_template_regions_from_clean_pass() -> None:
    plan = RenderPlan(
        plan_id="plan-xlsx-no-regions",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/template.xlsx", format_key="xlsx"),
        output=OutputRef(output_path="/outputs/result.xlsx", output_format="xlsx"),
        diagnostics=[
            PlanDiagnostic(
                severity="warning",
                code="xlsx_no_template_regions",
                message="No template regions detected.",
            )
        ],
    )

    result = check_output(
        plan,
        [
            OutputArtifactSnapshot(
                name="result.xlsx",
                text_fragments=["原模板内容"],
                metadata={"format_key": "xlsx"},
            )
        ],
        include_unresolved_slots=False,
    )

    assert [issue.code for issue in result.issues] == ["no_template_regions"]
    assert result.is_clean is False


def test_output_checker_blocks_xlsx_no_template_regions_from_snapshot_metadata() -> None:
    plan = RenderPlan(
        plan_id="plan-xlsx-no-regions-snapshot",
        source_bundle_path="/bundle/parsed_document_bundle.json",
        template=TemplateRef(template_path="/templates/template.xlsx", format_key="xlsx"),
        output=OutputRef(output_path="/outputs/result.xlsx", output_format="xlsx"),
    )

    result = check_output(
        plan,
        [
            OutputArtifactSnapshot(
                name="result.xlsx",
                text_fragments=["原模板内容"],
                metadata={
                    "format_key": "xlsx",
                    "diagnostics": [{"code": "xlsx_no_template_regions", "severity": "warning"}],
                },
            )
        ],
        include_unresolved_slots=False,
    )

    assert [issue.code for issue in result.issues] == ["no_template_regions"]
    assert result.is_clean is False


def test_output_checker_reports_source_record_leakage() -> None:
    result = check_output(
        _build_plan(),
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=["Sheet=Sheet0 | Range=A8:U8 | 隐患描述=未佩戴安全帽 | 整改要求=立即整改"],
                applied_text_slots={"slot-desc"},
                applied_image_slots={"slot-photo"},
            )
        ],
        include_unresolved_slots=False,
    )

    leakage_issues = [issue for issue in result.issues if issue.code == "source_record_leakage"]

    assert len(leakage_issues) == 1
    assert leakage_issues[0].artifact_name == "result.docx"
    assert result.is_clean is False


def test_output_checker_reports_unsafe_empty_sentence_skeletons() -> None:
    result = check_output(
        _build_plan(),
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=[
                    "2022年X月X日，检查人员于X对项目检查发现；。",
                    "依据相关规定，拟对进行处罚。",
                    "年  月  日下午，检查发现；。",
                ],
                applied_text_slots={"slot-desc"},
                applied_image_slots={"slot-photo"},
            )
        ],
        include_unresolved_slots=False,
        quality_profile="zh_official",
    )

    skeleton_issues = [issue for issue in result.issues if issue.code == "unsafe_empty_sentence_skeleton"]

    assert len(skeleton_issues) >= 3
    assert result.is_clean is False


def test_output_checker_generic_profile_does_not_apply_zh_official_sentence_patterns() -> None:
    result = check_output(
        _build_plan(),
        [
            OutputArtifactSnapshot(
                name="result.docx",
                text_fragments=["2022年X月X日，检查人员于X对项目检查发现；。"],
                applied_text_slots={"slot-desc"},
                applied_image_slots={"slot-photo"},
            )
        ],
        include_unresolved_slots=False,
    )

    assert [issue.code for issue in result.issues if issue.code == "unsafe_empty_sentence_skeleton"] == []
