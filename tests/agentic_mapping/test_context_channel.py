from __future__ import annotations

import ast
import inspect
from pathlib import Path

from doctransai.models.source import (
    ProvenanceRef,
    SourceDocument,
    SourceImageAsset,
    SourceModel,
    SourceRecord,
    SourceValue,
)
from doctransai.models.template import (
    HeaderDrivenRegion,
    RepeatRegion,
    SlotAddress,
    TemplateDiagnostic,
    TemplateModel,
    TemplateSlot,
)
from doctransai.agentic_mapping import context as context_module
from doctransai.agentic_mapping.context import build_evidence_package


def test_builds_evidence_package_with_structured_source_and_template_views() -> None:
    source_model = SourceModel(
        documents=[
            SourceDocument(
                document_id="source-doc",
                source_path="/tmp/source.docx",
                doc_type="docx",
                document_title="Source",
                parser_name="dataproxy",
            )
        ],
        records=[
            SourceRecord(
                record_id="record-1",
                document_id="source-doc",
                source_path="/tmp/source.docx",
                values=[
                    SourceValue(
                        canonical_key="project_name",
                        raw_label="项目名称",
                        value="桥梁检测项目",
                        value_type="text",
                        confidence_base=0.82,
                        provenance=[
                            ProvenanceRef(
                                source_kind="paragraph",
                                document_id="source-doc",
                                evidence_id="ev-1",
                                locator={"page": 1, "block_id": "b1"},
                            )
                        ],
                    )
                ],
                locator={"page": 1, "block_id": "b1"},
            )
        ],
        image_assets=[
            SourceImageAsset(
                asset_id="img-1",
                document_id="source-doc",
                asset_path="/tmp/source-page-1-image.png",
                page_anchor="1",
                bbox=[10, 20, 30, 40],
                nearby_text_before=["现场照片"],
                nearby_text_after=["照片说明"],
            )
        ],
        diagnostics=[{"severity": "warning", "code": "source_note", "message": "kept"}],
    )
    template_model = TemplateModel(
        template_id="template-doc",
        template_path="/tmp/template.docx",
        format_key="docx",
        analyzer_key="p1b",
        slots=[
            TemplateSlot(
                slot_id="slot-1",
                raw_name="项目名称",
                canonical_name="project_name",
                slot_kind="text",
                address=SlotAddress(
                    format_key="docx",
                    address_kind="paragraph",
                    paragraph_index=2,
                    run_index=1,
                ),
                context_before="项目：",
            )
        ],
        repeat_regions=[
            RepeatRegion(
                region_id="repeat-1",
                format_key="docx",
                region_kind="image_caption_block",
                address=SlotAddress(format_key="docx", address_kind="paragraph", paragraph_index=5),
            )
        ],
        header_regions=[
            HeaderDrivenRegion(
                region_id="header-1",
                format_key="xlsx",
                sheet_name="Sheet1",
                header_row_index=1,
                column_names=["项目名称"],
                sample_row_index=2,
            )
        ],
        diagnostics=[
            TemplateDiagnostic(
                severity="info",
                code="template_note",
                message="kept",
                field="项目名称",
            )
        ],
    )

    package = build_evidence_package(
        source_model,
        template_model,
        source_page_images=[
            {"page_index": 0, "image_path": "/tmp/source-page-1.png", "source": "dataproxy"}
        ],
        template_page_images=[Path("/tmp/template-page-1.png")],
    )

    assert package["schema_name"] == "agentic_mapping_evidence_package"
    assert package["source"]["page_images"] == [
        {"image_ref": "/tmp/source-page-1.png", "page_index": 0, "source": "dataproxy"}
    ]
    assert package["source"]["input_gaps"] == []
    assert package["source"]["structured"]["documents"][0]["document_id"] == "source-doc"
    assert package["source"]["structured"]["records"][0]["values"][0]["value"] == "桥梁检测项目"
    assert package["source"]["structured"]["records"][0]["values"][0]["provenance"][0]["locator"] == {
        "page": 1,
        "block_id": "b1",
    }
    assert package["source"]["structured"]["image_assets"][0]["nearby_text_after"] == ["照片说明"]
    assert package["source"]["structured"]["diagnostics"][0]["code"] == "source_note"
    assert set(package["source"]["structured"]["object_index"]) >= {
        "record:record-1",
        "source_value:record-1:0",
        "image_asset:img-1",
        "diagnostic:0",
    }

    assert package["template"]["page_images"] == [{"image_ref": "/tmp/template-page-1.png"}]
    assert package["template"]["input_gaps"] == []
    assert package["template"]["structured"]["slots"][0]["slot_id"] == "slot-1"
    assert package["template"]["structured"]["slots"][0]["address"]["paragraph_index"] == 2
    assert package["template"]["structured"]["repeat_regions"][0]["region_id"] == "repeat-1"
    assert package["template"]["structured"]["header_regions"][0]["column_names"] == ["项目名称"]
    assert package["template"]["structured"]["diagnostics"][0]["code"] == "template_note"
    assert "template_slot:slot-1" in package["template"]["structured"]["object_index"]
    assert "diagnostic:0" in package["template"]["structured"]["object_index"]


def test_missing_page_images_are_reported_as_input_gaps_without_failing() -> None:
    package = build_evidence_package(
        SourceModel(),
        TemplateModel(
            template_id="template-doc",
            template_path="/tmp/template.docx",
            format_key="docx",
            analyzer_key="p1b",
        ),
    )

    assert package["source"]["page_images"] == []
    assert package["template"]["page_images"] == []
    assert package["source"]["input_gaps"] == [
        {"code": "missing_source_page_images", "message": "Source page render images were not provided."}
    ]
    assert package["template"]["input_gaps"] == [
        {
            "code": "missing_template_page_images",
            "message": "Template page render images were not provided.",
        }
    ]


def test_context_channel_does_not_import_legacy_mapping_modules() -> None:
    forbidden_imports = {
        "doctransai.mapping.candidate_builder",
        "doctransai.mapping.structural_candidates",
        "doctransai.mapping.resolver",
        "doctransai.mapping.planner",
        "doctransai.source_model.instances",
        "doctransai.mapping.cluster_planner",
    }
    tree = ast.parse(inspect.getsource(context_module))
    imported_modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    assert imported_modules.isdisjoint(forbidden_imports)
