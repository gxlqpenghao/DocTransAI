from __future__ import annotations

from doctransai.formats import DocumentFamily, detect_format, ingest_format_keys, output_format_keys


def test_detects_docx_xlsx_and_pdf_as_first_class_formats() -> None:
    assert detect_format("target.docx").family is DocumentFamily.WORD
    assert detect_format("target.xlsx").family is DocumentFamily.SPREADSHEET
    assert detect_format("target.pdf").family is DocumentFamily.PDF
    assert set(output_format_keys()) == {"docx", "xlsx", "pdf"}
    assert set(ingest_format_keys()) == {"doc", "docx", "xlsx", "pdf"}


def test_routes_doc_docx_and_pdf_to_mineru_document_parser() -> None:
    doc = detect_format("legacy.doc")
    docx = detect_format("source.docx")
    pdf = detect_format("source.pdf")

    assert doc.parser_key == "mineru_document"
    assert docx.parser_key == "mineru_document"
    assert pdf.parser_key == "mineru_document"
    assert not doc.requires_conversion


def test_rejects_unknown_extensions_with_clear_error() -> None:
    for path in ("notes.txt", "slides.pptx"):
        try:
            detect_format(path)
        except ValueError as exc:
            assert "Unsupported document format" in str(exc)
        else:
            raise AssertionError(f"Expected unsupported extension to raise ValueError: {path}")
