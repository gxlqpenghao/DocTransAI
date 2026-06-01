from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class TemplateMaterializationResult:
    template_path: Path
    analysis_template_path: Path
    output_path: Path
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def materialize_target_template(
    template_path: str | Path,
    output_path: str | Path,
    *,
    cache_root: str | Path | None = None,
) -> TemplateMaterializationResult:
    resolved_template_path = Path(template_path).expanduser().resolve()
    resolved_output_path = Path(output_path).expanduser().resolve()

    if resolved_template_path.suffix.lower() != ".doc":
        return TemplateMaterializationResult(
            template_path=resolved_template_path,
            analysis_template_path=resolved_template_path,
            output_path=resolved_output_path,
            metadata={
                "strategy": "native_template",
                "requested_template_format": resolved_template_path.suffix.lower().lstrip("."),
                "analysis_template_format": resolved_template_path.suffix.lower().lstrip("."),
                "original_template_path": str(resolved_template_path),
                "materialized_template_path": str(resolved_template_path),
                "original_output_path": str(resolved_output_path),
                "materialized_output_path": str(resolved_output_path),
            },
        )

    converter = _find_soffice()
    if converter is None:
        raise RuntimeError(
            "Legacy DOC target templates require LibreOffice/soffice conversion to DOCX before "
            f"analysis/rendering. Install LibreOffice/soffice or provide a .docx target template: {resolved_template_path}"
        )

    materialized_root = (
        Path(cache_root).expanduser().resolve()
        if cache_root is not None
        else (resolved_output_path.parent / ".doctransai_template_materialization").resolve()
    )
    cache_dir = materialized_root / _cache_key(resolved_template_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    analysis_template_path = _convert_doc_to_docx(resolved_template_path, converter=converter, output_dir=cache_dir)
    materialized_output_path = _docx_output_path(resolved_output_path)

    diagnostic = {
        "severity": "info",
        "code": "doc_template_converted_to_docx",
        "message": (
            "Converted legacy DOC target template to DOCX for analysis/rendering: "
            f"{resolved_template_path} -> {analysis_template_path}"
        ),
        "field": None,
    }
    metadata = {
        "strategy": "libreoffice_doc_to_docx",
        "requested_template_format": "doc",
        "analysis_template_format": "docx",
        "original_template_path": str(resolved_template_path),
        "materialized_template_path": str(analysis_template_path),
        "original_output_path": str(resolved_output_path),
        "materialized_output_path": str(materialized_output_path),
        "converter": converter,
    }
    return TemplateMaterializationResult(
        template_path=resolved_template_path,
        analysis_template_path=analysis_template_path,
        output_path=materialized_output_path,
        diagnostics=[diagnostic],
        metadata=metadata,
    )


def _find_soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def _convert_doc_to_docx(template_path: Path, *, converter: str, output_dir: Path) -> Path:
    profile_dir = output_dir / "lo_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    expected_path = output_dir / f"{template_path.stem}.docx"

    try:
        completed = subprocess.run(
            [
                converter,
                f"-env:UserInstallation={profile_dir.as_uri()}",
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                str(output_dir),
                str(template_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Failed to convert legacy DOC target template to DOCX with LibreOffice/soffice: "
            f"{template_path}. stdout={exc.stdout or ''} stderr={exc.stderr or ''}"
        ) from exc

    if expected_path.exists():
        return expected_path.resolve()

    converted_candidates = sorted(path for path in output_dir.glob("*.docx") if path.is_file())
    if len(converted_candidates) == 1:
        return converted_candidates[0].resolve()

    raise RuntimeError(
        "LibreOffice/soffice reported success but did not produce a DOCX target template: "
        f"{template_path}. stdout={completed.stdout or ''} stderr={completed.stderr or ''}"
    )


def _docx_output_path(output_path: Path) -> Path:
    if output_path.suffix.lower() in {"", ".doc"}:
        return output_path.with_suffix(".docx")
    return output_path


def _cache_key(template_path: Path) -> str:
    stat = template_path.stat()
    payload = f"{template_path}|{stat.st_mtime_ns}|{stat.st_size}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
