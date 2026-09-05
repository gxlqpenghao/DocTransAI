from __future__ import annotations

import subprocess
from pathlib import Path

import doctransai.templates.visual_preview as visual_preview_module
from doctransai.templates.visual_preview import render_template_visual_pages


def test_render_visual_pages_converts_legacy_doc_to_pdf(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "source.doc"
    source_path.write_bytes(b"legacy word bytes")

    observed_commands: list[list[str]] = []

    def fake_run(command, *, check, stdout, stderr):
        observed_commands.append([str(item) for item in command])
        if "--convert-to" in command:
            outdir = Path(command[command.index("--outdir") + 1])
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / "source.pdf").write_bytes(b"%PDF")
        else:
            output_prefix = Path(command[-1])
            output_prefix.parent.mkdir(parents=True, exist_ok=True)
            (output_prefix.parent / f"{output_prefix.name}-1.png").write_bytes(b"png")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(visual_preview_module.subprocess, "run", fake_run)

    pages = render_template_visual_pages(source_path, format_key="doc", cache_root=tmp_path / "cache")

    assert [page.name for page in pages] == ["page-1.png"]
    assert observed_commands[0][observed_commands[0].index("--convert-to") + 1] == "pdf"
    assert observed_commands[0][-1] == str(source_path.resolve())
    assert observed_commands[1][0] == "pdftoppm"
