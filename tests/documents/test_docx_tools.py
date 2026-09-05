import hashlib
import zipfile

from docx import Document
from docx.shared import RGBColor
from PIL import Image
import pytest

from doctransai.documents.docx import DocxEditor


def make_editor(tmp_path, paragraphs):
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    template = tmp_path / "template.docx"
    doc.save(template)
    for ref, color in [("a", "red"), ("b", "blue")]:
        Image.new("RGB", (100, 50), color).save(tmp_path / f"{ref}.png")
    return DocxEditor(template, tmp_path / "output.docx", lambda ref: tmp_path / f"{ref}.png")


def test_cross_run_replacement_keeps_unrelated_format_and_package(tmp_path):
    e = make_editor(tmp_path, [])
    doc = Document(e.template)
    p = doc.add_paragraph()
    p.add_run("Fixed ").bold = True
    p.add_run("{na").italic = True
    p.add_run("me} suffix").underline = True
    doc.save(e.template)
    e = DocxEditor(e.template, e.output, e.asset_path)
    e.apply(batch_id="1", version=0, edits=[dict(op="replace_text", target="n0", old="{name}", text="VALUE")])
    p = e.doc.paragraphs[0]
    assert p.text == "Fixed VALUE suffix"
    assert next(r for r in p.runs if r.text == "Fixed ").bold
    assert next(r for r in p.runs if r.text == "VALUE").italic
    assert next(r for r in p.runs if r.text == " suffix").underline
    with zipfile.ZipFile(e.template) as a, zipfile.ZipFile(e.output) as b:
        assert [n for n in a.namelist() if a.read(n) != b.read(n)] == ["word/document.xml"]
    assert e.doc.sections[0].header.is_linked_to_previous


def test_batch_failure_rolls_back_disk_memory_and_version(tmp_path):
    e = make_editor(tmp_path, ["original", "second"])
    before = e.output.read_bytes()
    with pytest.raises(KeyError):
        e.apply(batch_id="bad", version=0, edits=[dict(op="set_text", target="n0", text="changed"),
                                                dict(op="set_text", target="missing", text="bad")])
    assert e.output.read_bytes() == before
    assert e.doc.paragraphs[0].text == "original"
    assert e.version == 0
    assert not e.applied_batches
    assert [n["id"] for n in e.inspect()["nodes"]] == ["n0", "n1"]
    e.apply(batch_id="retry", version=0, edits=[dict(op="set_text", target="n0", text="correct")])
    assert Document(e.output).paragraphs[0].text == "correct"


def test_group_repeat_keeps_images_with_descriptions_and_is_idempotent(tmp_path):
    e = make_editor(tmp_path, ["{image}", "{description}", "fixed"])
    original = hashlib.sha256(e.template.read_bytes()).hexdigest()
    edits = [dict(op="repeat_paragraphs", targets=["n0", "n1"], items=[
        dict(contents=[dict(asset_ids=["a", "b"]), dict(text="first issue")]),
        dict(contents=[dict(asset_ids=["b"]), dict(text="second issue")]),
    ])]
    first = e.apply(batch_id="repeat", version=0, edits=edits)
    duplicate = e.apply(batch_id="repeat", version=0, edits=edits)
    assert duplicate["already_applied"]
    assert e.version == 1 and len(e.doc.inline_shapes) == 3
    assert [p.text for p in e.doc.paragraphs] == ["\n", "first issue", "", "second issue", "fixed"]
    assert e.doc.paragraphs[0].paragraph_format.keep_with_next
    assert e.doc.paragraphs[2].paragraph_format.keep_with_next
    assert len({n["id"] for n in first["nodes"]}) == len(first["nodes"])
    assert hashlib.sha256(e.template.read_bytes()).hexdigest() == original
    with pytest.raises(ValueError, match="Stale"):
        e.apply(batch_id="stale", version=0, edits=[dict(op="set_text", target="n2", text="x")])


def test_text_edit_refuses_to_destroy_picture(tmp_path):
    e = make_editor(tmp_path, ["image region"])
    e.apply(batch_id="image", version=0, edits=[dict(op="set_images", target="n0", asset_ids=["a"])])
    before = e.output.read_bytes()
    with pytest.raises(ValueError, match="image"):
        e.apply(batch_id="text", version=1, edits=[dict(op="set_text", target="n0", text="replacement")])
    assert e.output.read_bytes() == before


def test_layout_operation_changes_no_text_and_keeps_package_parts(tmp_path):
    e = make_editor(tmp_path, ["fixed text", ""])
    e.apply(batch_id="layout", version=0, edits=[dict(op="format_paragraph", target="n1",
        format=dict(font_size_pt=1, line_spacing_pt=1, space_before_pt=0, space_after_pt=0, page_break_before=False))])
    assert [p.text for p in e.doc.paragraphs] == ["fixed text", ""]
    assert e.doc.paragraphs[1].runs[0].font.size.pt == 1
    assert e.doc.paragraphs[1].paragraph_format.line_spacing.pt == 1
    with zipfile.ZipFile(e.template) as a, zipfile.ZipFile(e.output) as b:
        assert a.read("word/styles.xml") == b.read("word/styles.xml")


def test_replacement_does_not_inherit_invisible_leading_marker(tmp_path):
    e = make_editor(tmp_path, [])
    doc = Document(e.template)
    p = doc.add_paragraph()
    p.add_run("X").font.color.rgb = RGBColor(255, 255, 255)
    p.add_run("{name}").font.color.rgb = RGBColor(0, 0, 0)
    doc.save(e.template)
    e = DocxEditor(e.template, e.output, e.asset_path)
    e.apply(batch_id="visible", version=0, edits=[dict(op="replace_text", target="n0", old="X{name}", text="Readable")])
    run = next(r for r in Document(e.output).paragraphs[0].runs if r.text == "Readable")
    assert run.font.color.rgb == RGBColor(0, 0, 0)
