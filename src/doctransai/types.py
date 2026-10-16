from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskSpec:
    bundle_path: Path
    template_path: Path
    output_dir: Path
    instruction: str | None = None
    source_file: Path | None = None
    document_id: str | None = None
    source_refs: tuple[str, ...] = ()


@dataclass
class ConversionResult:
    execution_status: str
    review_status: str
    output_path: str | None
    report_path: str
    issues: list[dict[str, Any]] = field(default_factory=list)
