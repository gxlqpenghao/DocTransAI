from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from PIL import Image

from doctransai.config import RuntimeConfig


# sha256(re-encoded image bytes sent to the model) -> resolved source file path.
IMAGE_CONTENT_REGISTRY: dict[str, str] = {}


def image_part(path: Path) -> dict:
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((1500, 1800))
        out = BytesIO()
        img.save(out, format="JPEG", quality=85)
    content = out.getvalue()
    # Provenance only: lets optional diagnostics map a request image hash back
    # to its source file. Pure bookkeeping; never affects the produced part.
    try:
        IMAGE_CONTENT_REGISTRY.setdefault(hashlib.sha256(content).hexdigest(), str(Path(path).resolve()))
    except Exception:
        pass
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(content).decode()}}


class Previewer:
    def __init__(self, cache: Path, config: RuntimeConfig, *, deadline: float | None = None):
        self.cache, self.config, self.deadline = cache, config, deadline

    def render(self, path: Path, *, page_number: int | None = None) -> list[Path]:
        if not path.is_file():
            raise ValueError(f"Preview input missing: {path}")
        if page_number is not None and page_number < 1:
            raise ValueError("page_number is one-based")
        script = self.config.render_script
        if path.suffix.lower() != ".pdf" and (script is None or not script.is_file()):
            raise ValueError("Set DOCTRANSAI_DOCX_RENDERER to a working render_docx.py; source/template previews are not optional silently")
        builtin = script == Path(__file__).resolve().parents[1] / "render_document.py"
        fontconfig = os.environ.get("FONTCONFIG_FILE")
        signature = dict(content=hashlib.sha256(path.read_bytes()).hexdigest(),
                         script=hashlib.sha256(script.read_bytes()).hexdigest() if script and script.is_file() else None,
                         python=self.config.render_python, pdftoppm=self.config.pdftoppm,
                         revision=self.config.render_revision, soffice=self.config.soffice,
                         fontconfig=fontconfig,
                         fontconfig_sha256=hashlib.sha256(Path(fontconfig).read_bytes()).hexdigest()
                         if fontconfig and Path(fontconfig).is_file() else None,
                         page=page_number if path.suffix.lower() == ".pdf" else None)
        key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:24]
        target = self.cache / key
        manifest = target / "pages.json"
        if not manifest.exists():
            # A failed render never becomes a cache hit, nor leaves stale extra pages.
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True)
            if path.suffix.lower() == ".pdf" and not builtin:
                cmd = [self.config.pdftoppm, "-png", "-scale-to", "1800"]
                if page_number:
                    cmd += ["-f", str(page_number), "-l", str(page_number)]
                cmd += [str(path), str(target / "page")]
            else:
                cmd = [self.config.render_python, str(script), str(path), "--output_dir", str(target), "--emit_pdf"]
            timeout = self.config.render_timeout
            if self.deadline is not None:
                timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError("Conversion time budget exhausted before preview")
            if builtin:
                cmd = [self.config.render_python, "-m", "doctransai.render_document", str(path), "--output_dir", str(target), "--emit_pdf"]
                cmd += ['--timeout-seconds',str(max(1,timeout-5))]
                if self.config.soffice:cmd += ['--soffice',self.config.soffice]
                if page_number and path.suffix.lower()=='.pdf':cmd += ['--page-number',str(page_number)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode:
                raise ValueError("Preview failed: " + (result.stderr + result.stdout)[-1200:])
            pages = sorted(target.glob("page-*.png"), key=lambda p: int(re.search(r"(\d+)$", p.stem).group()))
            if not pages:
                raise ValueError("Preview returned no page images")
            manifest.write_text(json.dumps([p.name for p in pages]))
        pages = [target / name for name in json.loads(manifest.read_text())]
        if not all(p.is_file() for p in pages):
            manifest.unlink()
            raise ValueError("Preview cache incomplete; render again")
        if page_number is not None and path.suffix.lower() != ".pdf":
            if page_number > len(pages):
                raise ValueError(f"Page {page_number} exceeds rendered page count {len(pages)}")
            return [pages[page_number - 1]]
        return pages

    def source_page(self, source, page_number: int) -> tuple[dict, Path]:
        anchor = f"page_{page_number}"
        native = [ref for ref, row in source.assets.items()
                  if row.get("asset_type") == "scanned_page" and row.get("page_anchor") == anchor]
        if len(native) > 1:
            raise ValueError(f"Multiple native scanned-page assets for {anchor}; inspect asset IDs explicitly")
        if native:
            return dict(origin="dataproxy_scanned_page", page_number=page_number, native_anchor=anchor,
                        asset_id=native[0]), source.asset_path(native[0])
        path = source.source_file
        expected = source.document.get("source_checksum")
        if expected and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Source file changed since DataProxy parsing; cannot use it as matching visual evidence")
        pages = self.render(path, page_number=page_number)
        return dict(origin="local_render", page_number=page_number, native_anchor=None,
                    mapping="Rendered page only; correspondence with DataProxy anchors is unverified, especially after DOC/DOCX/XLSX repagination."), pages[0]
