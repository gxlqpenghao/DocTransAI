from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DocumentFamily(Enum):
    WORD = "word"
    SPREADSHEET = "spreadsheet"
    PDF = "pdf"


@dataclass(frozen=True, slots=True)
class FormatSpec:
    key: str
    extension: str
    family: DocumentFamily
    parser_key: str
    native_extension: str
    requires_conversion: bool = False
    template_analyzer_key: str | None = None
    renderer_key: str | None = None

    @property
    def can_ingest(self) -> bool:
        return bool(self.parser_key)

    @property
    def can_analyze_template(self) -> bool:
        return self.template_analyzer_key is not None

    @property
    def can_render_output(self) -> bool:
        return self.renderer_key is not None


_FORMATS: dict[str, FormatSpec] = {
    ".doc": FormatSpec(
        key="doc",
        extension=".doc",
        family=DocumentFamily.WORD,
        parser_key="mineru_document",
        native_extension=".doc",
    ),
    ".docx": FormatSpec(
        key="docx",
        extension=".docx",
        family=DocumentFamily.WORD,
        parser_key="mineru_document",
        native_extension=".docx",
        template_analyzer_key="docx_template",
        renderer_key="docx_renderer",
    ),
    ".xlsx": FormatSpec(
        key="xlsx",
        extension=".xlsx",
        family=DocumentFamily.SPREADSHEET,
        parser_key="xlsx_native",
        native_extension=".xlsx",
        template_analyzer_key="xlsx_template",
        renderer_key="xlsx_renderer",
    ),
    ".pdf": FormatSpec(
        key="pdf",
        extension=".pdf",
        family=DocumentFamily.PDF,
        parser_key="mineru_document",
        native_extension=".pdf",
        template_analyzer_key="pdf_template",
        renderer_key="pdf_renderer",
    ),
}


def detect_format(path: str | Path) -> FormatSpec:
    extension = Path(path).suffix.lower()
    spec = _FORMATS.get(extension)
    if spec is None:
        supported = ", ".join(sorted(_FORMATS))
        raise ValueError(f"Unsupported document format: {extension or '<none>'}. Supported: {supported}")
    return spec


def format_for_key(key: str) -> FormatSpec:
    for spec in _FORMATS.values():
        if spec.key == key:
            return spec
    raise ValueError(f"Unsupported document format key: {key}")


def ingest_format_keys() -> tuple[str, ...]:
    return tuple(spec.key for spec in _FORMATS.values() if spec.can_ingest)


def template_format_keys() -> tuple[str, ...]:
    return tuple(spec.key for spec in _FORMATS.values() if spec.can_analyze_template)


def output_format_keys() -> tuple[str, ...]:
    return tuple(spec.key for spec in _FORMATS.values() if spec.can_render_output)
