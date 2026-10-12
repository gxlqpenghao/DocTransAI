from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def render_template_visual_pages(
    template_path: str | Path,
    *,
    format_key: str,
    cache_root: str | Path | None = None,
) -> list[Path]:
    resolved_template_path = Path(template_path).expanduser().resolve()
    if not resolved_template_path.exists():
        return []

    target_root = (
        Path(cache_root).expanduser().resolve()
        if cache_root is not None
        else (Path.cwd() / "tmp" / "template_visual_previews").resolve()
    )
    target_root.mkdir(parents=True, exist_ok=True)
    cache_dir = target_root / _cache_key(resolved_template_path, format_key=format_key)
    cache_dir.mkdir(parents=True, exist_ok=True)

    existing_pages = sorted(cache_dir.glob("page-*.png"))
    if existing_pages:
        return existing_pages

    try:
        pdf_path = _materialize_pdf(resolved_template_path, format_key=format_key, output_dir=cache_dir)
        if pdf_path is None or not pdf_path.exists():
            return []
        _render_pdf_pages(pdf_path, cache_dir)
        return sorted(cache_dir.glob("page-*.png"))
    except Exception:  # noqa: BLE001
        return []


def _cache_key(template_path: Path, *, format_key: str) -> str:
    stat = template_path.stat()
    payload = f"{template_path}|{format_key}|{stat.st_mtime_ns}|{stat.st_size}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _materialize_pdf(template_path: Path, *, format_key: str, output_dir: Path) -> Path | None:
    if format_key == "pdf":
        return template_path
    if format_key not in {"doc", "docx", "xlsx"}:
        return None

    subprocess.run(
        [
            "soffice",
            "-env:UserInstallation=file:///tmp/lo_profile_doctransai_template_preview",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(template_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return output_dir / f"{template_path.stem}.pdf"


def _render_pdf_pages(pdf_path: Path, output_dir: Path) -> None:
    subprocess.run(
        [
            "pdftoppm",
            "-png",
            str(pdf_path),
            str(output_dir / "page"),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
