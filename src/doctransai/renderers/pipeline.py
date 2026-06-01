from __future__ import annotations

from doctransai.renderers.docx import DocxRenderer
from doctransai.renderers.pdf import PdfRenderer
from doctransai.renderers.xlsx import XlsxRenderer


def renderer_for_format(format_key: str):
    if format_key == "docx":
        return DocxRenderer()
    if format_key == "xlsx":
        return XlsxRenderer()
    if format_key == "pdf":
        return PdfRenderer()
    raise ValueError(f"Unsupported renderer format: {format_key}")
