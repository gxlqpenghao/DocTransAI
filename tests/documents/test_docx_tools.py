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

def test_multiple_ranges_share_snapshot_and_style(tmp_path):
    outputs=[]
    for index, reverse in enumerate([False, True]):
        directory=tmp_path/str(index);directory.mkdir()
        e=make_editor(directory,['甲😀  乙   丙'])
        ranges=[dict(start=2,end=4,expected='  ',text='longer甲'),dict(start=5,end=8,expected='   ',text='Z')]
        if reverse:ranges.reverse()
        e.apply(batch_id='one',version=0,edits=[dict(op='replace_ranges',target='n0',replacements=ranges)])
        outputs.append(e.doc.paragraphs[0].text)
    assert outputs==['甲😀longer甲乙Z丙']*2


def test_multiple_range_failure_rolls_back_prior_operations(tmp_path):
    e=make_editor(tmp_path,['first','abc def ghi'])
    before=e.output.read_bytes()
    with pytest.raises(ValueError) as error:
        e.apply(batch_id='bad',version=0,edits=[dict(op='set_text',target='n0',text='changed'),
            dict(op='replace_ranges',target='n1',replacements=[dict(start=0,end=3,expected='abc',text='x'),dict(start=2,end=5,expected='c d',text='y')])])
    assert e.version==0 and e.output.read_bytes()==before
    assert error.value.edit_failure['failed_operation_index']==1
    assert error.value.edit_failure['rolled_back']
    assert e.nodes['n0'].text=='first'


def test_protection_summary_matches_bookmark_guard(tmp_path):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    e=make_editor(tmp_path,['prefix {value} suffix'])
    p=e.doc.paragraphs[0]
    a=OxmlElement('w:bookmarkStart');a.set(qn('w:id'),'123');a.set(qn('w:name'),'mark');p._p.insert(0,a)
    b=OxmlElement('w:bookmarkEnd');b.set(qn('w:id'),'123');p._p.append(b)
    n=e.inspect(detail=True)['nodes'][0]
    assert n['protected'] and not n['whole_text_replace_allowed']
    assert 'bookmarks' in n['protection_reason']


def test_multiple_ranges_styles_bound_to_base_runs(tmp_path):
    from docx.shared import Pt
    e=make_editor(tmp_path,[''])
    p=e.doc.paragraphs[0]
    p.add_run('A ').font.size=Pt(10)
    p.add_run('B ').font.size=Pt(18)
    p.add_run('C').font.size=Pt(24)
    e.apply(batch_id='styles',version=0,edits=[dict(op='replace_ranges',target='n0',replacements=[
        dict(start=0,end=1,expected='A',text='long',style_run_index=2),
        dict(start=2,end=3,expected='B',text='short',style_run_index=0)])])
    runs={r.text:r for r in e.doc.paragraphs[0].runs if r.text}
    assert runs['long'].font.size.pt==24
    assert runs['short'].font.size.pt==10
