from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from doctransai.models.diagnostics import Severity


@dataclass(slots=True, frozen=True)
class ImageSize:
    width: float
    height: float


@dataclass(slots=True)
class RenderDiagnostic:
    severity: Severity
    code: str
    message: str
    slot_id: str | None = None
    asset_id: str | None = None
    source_ref: str | None = None


@dataclass(slots=True)
class ResolvedImagePlacement:
    slot_id: str
    asset_id: str
    source_ref: str | None
    asset_path: Path | None
    intrinsic_size: ImageSize | None = None
    render_size: ImageSize | None = None
    diagnostics: list[RenderDiagnostic] = field(default_factory=list)

    @property
    def is_missing(self) -> bool:
        return self.asset_path is None


@dataclass(slots=True)
class RenderResult:
    output_path: str
    applied_text_slots: list[str] = field(default_factory=list)
    applied_image_slots: list[str] = field(default_factory=list)
    diagnostics: list[RenderDiagnostic] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)
