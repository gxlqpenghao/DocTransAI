"""Structural variations rather than sample-specific output expectations."""
import zipfile
import pytest
from docx import Document
from doctransai.documents.docx import DocxEditor


def editor(tmp_path, doc):
    path = tmp_path / 'template.docx'
    doc.save(path)
    return DocxEditor(path, tmp_path / 'result.docx', lambda _: None)


def node(e, kind, text):
    return next(n['id'] for n in e.inspect()['nodes'] if n['kind'] == kind and n['text'] == text)


@pytest.mark.parametrize('label,value', [('Date', '2030'), ('日期', '二〇三〇'), ('🧭', '北')])
def test_ranges_disambiguate_repeated_blanks_and_preserve_style(tmp_path, label, value):
    doc = Document(); p = doc.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0]
    p.add_run(label + ': '); p.add_run('____').underline = True; p.add_run(' / ____')
    e = editor(tmp_path, doc); target = node(e, 'paragraph', p.text)
    start = len(label) + 2
    e.apply(batch_id='a', version=0, edits=[dict(op='replace_range', target=target, start=start,
        end=start+4, expected='____', text=value, style_run_index=1)])
    p = Document(e.output).tables[0].cell(0, 0).paragraphs[0]
    assert p.text == label + ': ' + value + ' / ____'
    assert next(r for r in p.runs if r.text == value).underline
    with pytest.raises(ValueError, match='mismatch'):
        e.apply(batch_id='b', version=1, edits=[dict(op='replace_range', target=target, start=start,
            end=start+4, expected='____', text='wrong')])


@pytest.mark.parametrize('in_cell', [False, True])
@pytest.mark.parametrize('style', ['decimal', 'bullet'])
def test_lists_are_real_isolated_numbering_and_deleted_ids_expire(tmp_path, in_cell, style):
    doc = Document()
    p = doc.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0] if in_cell else doc.add_paragraph()
    p.text = 'prototype'
    e = editor(tmp_path, doc); target = node(e, 'paragraph', 'prototype')
    e.apply(batch_id='list', version=0, edits=[dict(op='set_list', target=target, items=['alpha', 'beta'], style=style)])
    result = Document(e.output)
    paragraphs = result.tables[0].cell(0, 0).paragraphs if in_cell else result.paragraphs
    assert [p.text for p in paragraphs] == ['alpha', 'beta']
    assert paragraphs[0]._p.pPr.numPr.numId.val == paragraphs[1]._p.pPr.numPr.numId.val
    assert target not in e.nodes
    with zipfile.ZipFile(e.output) as z:
        assert ('w:val="' + style + '"').encode() in z.read('word/numbering.xml')
    # Reopening must preserve usable numbering definitions, not merely paragraph IDs.
    nums = result.part.numbering_part.element
    used = paragraphs[0]._p.pPr.numPr.numId.val
    num = nums.num_having_numId(used)
    assert nums.xpath(f'./w:abstractNum[@w:abstractNumId="{num.abstractNumId.val}"]')


def test_repeat_rows_preserves_header_horizontal_merges_and_invalidates_children(tmp_path):
    doc = Document(); table = doc.add_table(rows=2, cols=3)
    table.cell(0, 0).text = 'header'
    table.cell(1, 0).merge(table.cell(1, 1)).text = 'merged'
    table.cell(1, 2).text = 'value'
    e = editor(tmp_path, doc)
    target = next(n['id'] for n in e.inspect()['nodes'] if n['kind'] == 'row' and n['where'].endswith('row 1'))
    child = node(e, 'paragraph', 'merged')
    e.apply(batch_id='rows', version=0, edits=[dict(op='repeat_rows', targets=[target], items=[
        dict(contents=[dict(text='A'), dict(text='10')]), dict(contents=[dict(text='B'), dict(text='20')])])])
    table = Document(e.output).tables[0]
    assert len(table.rows) == 3 and table.cell(0, 0).text == 'header'
    assert table.cell(1, 0).text == table.cell(1, 1).text == 'A'
    assert table.cell(2, 2).text == '20'
    assert child not in e.nodes and target not in e.nodes


def test_vertical_merge_group_must_be_complete_and_rolls_back(tmp_path):
    doc = Document(); table = doc.add_table(rows=3, cols=2)
    table.cell(1, 0).merge(table.cell(2, 0)).text = 'group'
    e = editor(tmp_path, doc)
    ids = [n['id'] for n in e.inspect()['nodes'] if n['kind'] == 'row']
    before = e.output.read_bytes()
    with pytest.raises(ValueError, match='vertical merge'):
        e.apply(batch_id='bad', version=0, edits=[dict(op='repeat_rows', targets=[ids[1]], items=[dict(contents=[])])])
    assert e.output.read_bytes() == before
    e.apply(batch_id='ok', version=0, edits=[dict(op='repeat_rows', targets=ids[1:], items=[
        dict(contents=[dict(text='group1'), dict(text='a'), dict(text='b')]),
        dict(contents=[dict(text='group2'), dict(text='c'), dict(text='d')])])])
    table = Document(e.output).tables[0]
    assert len(table.rows) == 5
    assert table.cell(1, 0).text == table.cell(2, 0).text == 'group1'
    assert table.cell(3, 0).text == table.cell(4, 0).text == 'group2'


def test_structure_change_followed_by_stale_child_rolls_back_numbering(tmp_path):
    doc = Document(); doc.add_paragraph('prototype')
    e = editor(tmp_path, doc); before = e.output.read_bytes()
    with pytest.raises(KeyError):
        e.apply(batch_id='bad', version=0, edits=[
            dict(op='set_list', target='n0', items=['a', 'b'], style='decimal'),
            dict(op='set_text', target='n0', text='stale')])
    assert e.output.read_bytes() == before and e.version == 0
    e.apply(batch_id='retry', version=0, edits=[dict(op='set_list', target='n0', items=['c', 'd'], style='bullet')])
    assert [p.text for p in Document(e.output).paragraphs] == ['c', 'd']


def test_nested_and_header_table_paragraphs_have_exact_addresses(tmp_path):
    doc = Document(); outer = doc.add_table(rows=1, cols=1)
    outer.cell(0, 0).add_table(rows=1, cols=1).cell(0, 0).text = 'nested'
    header = doc.sections[0].header
    from docx.shared import Inches
    header.add_table(rows=1, cols=1, width=Inches(5)).cell(0, 0).text = 'heading'
    e = editor(tmp_path, doc)
    edits = [dict(op='replace_text', target=node(e, 'paragraph', text), old=text, text=text+' changed')
             for text in ('nested', 'heading')]
    e.apply(batch_id='parts', version=0, edits=edits)
    result = Document(e.output)
    assert result.tables[0].cell(0, 0).tables[0].cell(0, 0).text == 'nested changed'
    assert result.sections[0].header.tables[0].cell(0, 0).text == 'heading changed'


def test_cloned_paragraph_session_ids_are_not_duplicated(tmp_path):
    doc = Document(); p = doc.add_paragraph('prototype')
    key = '{http://schemas.microsoft.com/office/word/2010/wordml}paraId'
    p._p.set(key, '12345678')
    e = editor(tmp_path, doc)
    e.apply(batch_id='list', version=0, edits=[dict(op='set_list', target='n0', style='decimal', items=['a', 'b'])])
    assert all(key not in p._p.attrib for p in Document(e.output).paragraphs)


def test_fixed_row_height_can_be_released_without_changing_content(tmp_path):
    from docx.enum.table import WD_ROW_HEIGHT_RULE
    from docx.shared import Pt
    doc = Document(); table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = 'long content'
    table.rows[0].height_rule = WD_ROW_HEIGHT_RULE.EXACTLY; table.rows[0].height = Pt(5)
    e = editor(tmp_path, doc); target = next(n['id'] for n in e.inspect()['nodes'] if n['kind'] == 'row')
    e.apply(batch_id='height', version=0, edits=[dict(op='format_row', target=target, format=dict(height_rule='auto', allow_split=False))])
    row = Document(e.output).tables[0].rows[0]
    assert row.cells[0].text == 'long content' and row.height is None
    assert row._tr.xpath('./w:trPr/w:cantSplit')


def test_repetition_cannot_duplicate_section_boundaries(tmp_path):
    from docx.oxml import OxmlElement
    doc = Document(); p = doc.add_paragraph('section end')
    p._p.get_or_add_pPr().append(OxmlElement('w:sectPr'))
    e = editor(tmp_path, doc); before = e.output.read_bytes()
    with pytest.raises(ValueError, match='section boundaries'):
        e.apply(batch_id='bad', version=0, edits=[dict(op='set_list', target='n0', items=['a', 'b'], style='decimal')])
    assert e.output.read_bytes() == before


def test_local_text_replacement_preserves_surrounding_bookmarks(tmp_path):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc = Document(); p = doc.add_paragraph()
    start = OxmlElement('w:bookmarkStart'); start.set(qn('w:id'), '1'); start.set(qn('w:name'), 'field')
    end = OxmlElement('w:bookmarkEnd'); end.set(qn('w:id'), '1')
    p._p.append(start); p.add_run('old'); p._p.append(end); p.add_run(' fixed')
    e = editor(tmp_path, doc)
    e.apply(batch_id='local', version=0, edits=[dict(op='replace_text', target='n0', old='old', text='new')])
    p = Document(e.output).paragraphs[0]
    assert p.text == 'new fixed' and len(p._p.xpath('./w:bookmarkStart | ./w:bookmarkEnd')) == 2
    with pytest.raises(ValueError, match='boundary'):
        e.apply(batch_id='cross', version=1, edits=[dict(op='replace_text', target='n0', old='new fixed', text='bad')])
    assert Document(e.output).paragraphs[0].text == 'new fixed'


def test_zero_width_bookmark_survives_cross_run_replacement(tmp_path):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc = Document(); p = doc.add_paragraph('ab')
    for tag in ('bookmarkStart', 'bookmarkEnd'):
        element = OxmlElement('w:'+tag); element.set(qn('w:id'), '7')
        if tag == 'bookmarkStart':element.set(qn('w:name'), 'arbitrary_point')
        p._p.append(element)
    p.add_run('cd')
    e = editor(tmp_path, doc)
    e.apply(batch_id='point', version=0, edits=[dict(op='replace_text', target='n0', old='abcd', text='new')])
    p = Document(e.output).paragraphs[0]
    assert p.text == 'new' and len(p._p.xpath('./w:bookmarkStart | ./w:bookmarkEnd')) == 2
