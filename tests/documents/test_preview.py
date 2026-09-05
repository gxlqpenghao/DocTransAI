from types import SimpleNamespace
from pathlib import Path

from PIL import Image
import pytest

from doctransai.config import RuntimeConfig
from doctransai.documents.preview import Previewer


def test_preview_cache_tracks_bytes_and_numerical_page_order(tmp_path, monkeypatch):
    script = tmp_path / "renderer.py"; script.write_text("renderer v1")
    doc = tmp_path / "document.docx"; doc.write_bytes(b"first")
    calls = []

    def render(cmd, **kwargs):
        out = Path(cmd[cmd.index("--output_dir") + 1])
        calls.append(out)
        for n in (10, 2, 1):
            Image.new("RGB", (5, 5)).save(out / f"page-{n}.png")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("doctransai.documents.preview.subprocess.run", render)
    p = Previewer(tmp_path / "cache", RuntimeConfig(render_script=script))
    pages = p.render(doc)
    assert [x.name for x in pages] == ["page-1.png", "page-2.png", "page-10.png"]
    assert p.render(doc) == pages and len(calls) == 1
    doc.write_bytes(b"other")  # same length, different content
    assert p.render(doc) != pages and len(calls) == 2


def test_failed_render_is_not_a_cache_hit(tmp_path, monkeypatch):
    script = tmp_path / "renderer.py"; script.write_text("renderer")
    doc = tmp_path / "document.docx"; doc.write_bytes(b"doc")
    calls = []

    def render(cmd, **kwargs):
        out = Path(cmd[cmd.index("--output_dir") + 1]); calls.append(out)
        Image.new("RGB", (5, 5)).save(out / "page-1.png")
        return SimpleNamespace(returncode=1, stderr="failed", stdout="")

    monkeypatch.setattr("doctransai.documents.preview.subprocess.run", render)
    p = Previewer(tmp_path / "cache", RuntimeConfig(render_script=script))
    for _ in range(2):
        with pytest.raises(ValueError, match="Preview failed"):
            p.render(doc)
    assert len(calls) == 2
