from __future__ import annotations

from doctransai.renderers.pipeline import renderer_for_format
from doctransai.renderers.docx import DocxRenderer
from doctransai.renderers.pdf import PdfRenderer
from doctransai.renderers.xlsx import XlsxRenderer


def test_renderer_for_format_returns_expected_renderer_types() -> None:
    assert isinstance(renderer_for_format("docx"), DocxRenderer)
    assert isinstance(renderer_for_format("xlsx"), XlsxRenderer)
    assert isinstance(renderer_for_format("pdf"), PdfRenderer)


def test_renderer_for_format_rejects_unknown_output_format() -> None:
    try:
        renderer_for_format("pptx")
    except ValueError as exc:
        assert "Unsupported renderer format" in str(exc)
    else:
        raise AssertionError("Expected unsupported renderer format to raise ValueError")
