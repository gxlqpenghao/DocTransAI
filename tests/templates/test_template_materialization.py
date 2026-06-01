from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from docx import Document

import doctransai.templates.template_materialization as materialization_module
from doctransai.templates.template_materialization import materialize_target_template


def test_materialize_target_template_converts_doc_template_with_soffice(tmp_path: Path, monkeypatch) -> None:
    template_path = tmp_path / "legacy-template.doc"
    output_path = tmp_path / "outputs" / "result.doc"
    template_path.write_bytes(b"legacy word bytes")

    observed_command: list[str] = []

    def fake_which(name: str) -> str | None:
        return "/opt/homebrew/bin/soffice" if name == "soffice" else None

    def fake_run(command, *, check, stdout, stderr, text):
        observed_command.extend(str(item) for item in command)
        outdir = Path(command[command.index("--outdir") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        document = Document()
        document.add_paragraph("项目：{项目名称}")
        document.save(outdir / "legacy-template.docx")
        return subprocess.CompletedProcess(command, 0, stdout="convert ok", stderr="")

    monkeypatch.setattr(materialization_module.shutil, "which", fake_which)
    monkeypatch.setattr(materialization_module.subprocess, "run", fake_run)

    result = materialize_target_template(template_path, output_path)

    assert result.template_path == template_path.resolve()
    assert result.analysis_template_path.name == "legacy-template.docx"
    assert result.output_path == output_path.resolve().with_suffix(".docx")
    assert Document(result.analysis_template_path).paragraphs[0].text == "项目：{项目名称}"
    assert "--headless" in observed_command
    assert observed_command[observed_command.index("--convert-to") + 1] == "docx"
    assert result.diagnostics == [
        {
            "severity": "info",
            "code": "doc_template_converted_to_docx",
            "message": (
                "Converted legacy DOC target template to DOCX for analysis/rendering: "
                f"{template_path.resolve()} -> {result.analysis_template_path}"
            ),
            "field": None,
        }
    ]
    assert result.metadata["strategy"] == "libreoffice_doc_to_docx"
    assert result.metadata["requested_template_format"] == "doc"
    assert result.metadata["analysis_template_format"] == "docx"


def test_materialize_target_template_raises_clear_error_when_doc_converter_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    template_path = tmp_path / "legacy-template.doc"
    output_path = tmp_path / "outputs" / "result.docx"
    template_path.write_bytes(b"legacy word bytes")

    monkeypatch.setattr(materialization_module.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match=r"LibreOffice|soffice|\\.docx"):
        materialize_target_template(template_path, output_path)
