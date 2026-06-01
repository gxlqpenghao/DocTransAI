from __future__ import annotations

from pathlib import Path

from doctransai.models.render_plan import OutputRef, RenderPlan, TargetRef, TemplateRef, TextFill
from doctransai.renderers.models import RenderDiagnostic
from doctransai.renderers.pdf import PdfRenderer


def _build_plan(*, template_path: Path, output_path: Path, text_fills: list[TextFill]) -> RenderPlan:
    return RenderPlan(
        plan_id="pdf-plan-1",
        source_bundle_path=str(template_path.parent / "parsed_document_bundle.json"),
        template=TemplateRef(template_path=str(template_path), format_key="pdf"),
        output=OutputRef(output_path=str(output_path), output_format="pdf"),
        text_fills=text_fills,
    )


def test_pdf_renderer_reports_clear_diagnostic_for_unsupported_target_kind(tmp_path: Path) -> None:
    template_path = tmp_path / "template.pdf"
    template_bytes = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog >>
endobj
%%EOF
"""
    template_path.write_bytes(template_bytes)
    output_path = tmp_path / "out" / "result.pdf"

    result = PdfRenderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-project",
                    target=TargetRef(format_key="pdf", target_kind="placeholder", page_index=0),
                    value="Alpha",
                )
            ],
        )
    )

    assert output_path.read_bytes() == template_bytes
    assert result.output_path == str(output_path.resolve())
    assert result.applied_text_slots == []
    assert result.diagnostics == [
        RenderDiagnostic(
            severity="error",
            code="unsupported_pdf_target",
            message="PDF renderer V1 only supports text fills that target a named form_field; slot slot-project uses target_kind='placeholder'.",
            slot_id="slot-project",
        )
    ]


def test_pdf_renderer_fills_simple_form_field_target_with_utf16_hex_value(tmp_path: Path) -> None:
    template_path = tmp_path / "template.pdf"
    template_path.write_bytes(
        b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /AcroForm 2 0 R >>
endobj
2 0 obj
<< /Fields [3 0 R] >>
endobj
3 0 obj
<< /FT /Tx /T (ProjectName) >>
endobj
trailer
<< /Root 1 0 R >>
%%EOF
""",
    )
    output_path = tmp_path / "out" / "result.pdf"

    result = PdfRenderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-project",
                    target=TargetRef(format_key="pdf", target_kind="form_field", form_field_name="ProjectName"),
                    value="项目 Alpha",
                )
            ],
        )
    )

    expected_hex = "FEFF" + "项目 Alpha".encode("utf-16-be").hex().upper()

    assert result.applied_text_slots == ["slot-project"]
    assert result.diagnostics == []
    assert f"/V <{expected_hex}>".encode("ascii") in output_path.read_bytes()


def test_pdf_renderer_reports_missing_form_field_and_leaves_pdf_unchanged(tmp_path: Path) -> None:
    template_path = tmp_path / "template.pdf"
    template_bytes = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /AcroForm 2 0 R >>
endobj
2 0 obj
<< /Fields [3 0 R] >>
endobj
3 0 obj
<< /FT /Tx /T (Owner) >>
endobj
trailer
<< /Root 1 0 R >>
%%EOF
"""
    template_path.write_bytes(template_bytes)
    output_path = tmp_path / "out" / "result.pdf"

    result = PdfRenderer().render(
        _build_plan(
            template_path=template_path,
            output_path=output_path,
            text_fills=[
                TextFill(
                    slot_id="slot-project",
                    target=TargetRef(format_key="pdf", target_kind="form_field", form_field_name="ProjectName"),
                    value="Alpha",
                )
            ],
        )
    )

    assert output_path.read_bytes() == template_bytes
    assert result.applied_text_slots == []
    assert result.diagnostics == [
        RenderDiagnostic(
            severity="error",
            code="pdf_form_field_not_found",
            message="PDF renderer could not find a unique AcroForm field named 'ProjectName' for slot slot-project; leaving the template unchanged.",
            slot_id="slot-project",
        )
    ]
