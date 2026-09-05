from copy import copy
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from PIL import Image
import pytest

from doctransai.documents.xlsx import XlsxEditor


def editor(tmp_path, setup=lambda w: None):
    w=Workbook();setup(w)
    p=tmp_path/'template.xlsx';w.save(p)
    Image.new('RGB',(100,50),'blue').save(tmp_path/'photo.png')
    return XlsxEditor(p,tmp_path/'result.xlsx',lambda _:tmp_path/'photo.png')


def test_typed_values_literal_formula_and_merge_protection(tmp_path):
    e=editor(tmp_path,lambda w:w.active.merge_cells('A1:B1'))
    e.apply(batch_id='a',version=0,edits=[dict(op='set_cells',target='s0!A2:D2',values=[[3,True,{'date':'2030-01-02'},'=1+1']])])
    s=load_workbook(e.output).active
    assert s['A2'].value==3 and s['B2'].value is True and isinstance(s['C2'].value,datetime)
    assert s['C2'].number_format == 'yyyy-mm-dd'
    assert s['D2'].data_type=='s' and s['D2'].value=='=1+1'
    before=e.output.read_bytes()
    with pytest.raises(ValueError,match='top-left'):
        e.apply(batch_id='b',version=1,edits=[dict(op='set_cells',target='s0!B1',values=[['bad']])])
    assert e.output.read_bytes()==before


def test_copy_rows_translates_mixed_refs_without_moving_other_formulas(tmp_path):
    def setup(w):
        s=w.active;s.title='Data';s.append([2,3,'=A1*$B$1']);s['C10']="=SUM('Data'!C1:C2)"
        s['A1'].fill=PatternFill('solid',fgColor='123456');s.row_dimensions[1].height=40
        w.create_sheet('Other')['A1']="='Data'!C10"
    e=editor(tmp_path,setup)
    e.apply(batch_id='copy',version=0,edits=[dict(op='copy_rows',target='s0!A1:C1',destination_rows=[2,3])])
    w=load_workbook(e.output);s=w.active
    assert s['C2'].value=='=A2*$B$1' and s['C3'].value=='=A3*$B$1'
    assert s['C10'].value=="=SUM('Data'!C1:C2)" and w['Other']['A1'].value=="='Data'!C10"
    assert copy(s['A3'].fill)==copy(s['A1'].fill) and s.row_dimensions[3].height==40
    before=e.output.read_bytes()
    with pytest.raises(ValueError,match='empty'):
        e.apply(batch_id='bad',version=1,edits=[dict(op='copy_rows',target='s0!A1:C1',destination_rows=[2])])
    assert before==e.output.read_bytes()


def test_formulas_require_explicit_edit_and_rollback_is_atomic(tmp_path):
    e=editor(tmp_path,lambda w:setattr(w.active['A1'],'value','=2*3'))
    with pytest.raises(ValueError,match='Formula cell'):
        e.apply(batch_id='bad',version=0,edits=[dict(op='set_cells',target='s0!A1',values=[[0]])])
    edits=[dict(op='set_formula',target='s0!A1',formula='=3*3',expected_formula='=2*3')]
    e.apply(batch_id='ok',version=0,edits=edits)
    assert e.apply(batch_id='ok',version=0,edits=edits)['already_applied']
    before=e.output.read_bytes()
    with pytest.raises(ValueError):
        e.apply(batch_id='rollback',version=1,edits=[dict(op='set_cells',target='s0!B1',values=[[5]]),dict(op='set_formula',target='s0!A1',formula='=4',expected_formula='wrong')])
    assert before==e.output.read_bytes() and e.book.active['B1'].value is None


def test_images_survive_multiple_saves_and_remove_only_selected_anchor(tmp_path):
    e=editor(tmp_path)
    e.apply(batch_id='images',version=0,edits=[dict(op='format_cells',target='s0!A1:B1',format={'row_height':80,'column_width':25}),
        dict(op='set_cell_images',target='s0!A1',asset_ids=['a','b']),dict(op='set_cell_images',target='s0!B1',asset_ids=['c'])])
    e.apply(batch_id='text',version=1,edits=[dict(op='set_cells',target='s0!C1',values=[['new']])])
    assert len(load_workbook(e.output).active._images)==3
    e.apply(batch_id='clear',version=2,edits=[dict(op='set_cell_images',target='s0!A1',asset_ids=[])])
    assert [e._image_cell(im) for im in load_workbook(e.output).active._images]==['B1']


def test_rows_copy_complete_merges_and_refuse_partial_selection(tmp_path):
    def setup(w):
        s=w.active;s.merge_cells('A1:B2');s['A1']='group';s['C1']='one';s['C2']='two'
    e=editor(tmp_path,setup)
    with pytest.raises(ValueError,match='entire merged'):
        e.apply(batch_id='partial',version=0,edits=[dict(op='copy_rows',target='s0!A1:C1',destination_rows=[4])])
    e.apply(batch_id='group',version=0,edits=[dict(op='copy_rows',target='s0!A1:C2',destination_rows=[4])])
    s=load_workbook(e.output).active
    assert 'A4:B5' in str(s.merged_cells) and s['A4'].value=='group' and s['C5'].value=='two'


def test_unrelated_validation_hidden_sheet_and_style_are_preserved(tmp_path):
    def setup(w):
        s=w.active;s['A1']='keep';s.freeze_panes='B2';s.auto_filter.ref='A1:C4'
        v=DataValidation(type='list',formula1='"yes,no"');s.add_data_validation(v);v.add('C2:C4')
        other=w.create_sheet('hidden');other.sheet_state='hidden';other['A1']='untouched'
    e=editor(tmp_path,setup)
    e.apply(batch_id='write',version=0,edits=[dict(op='set_cells',target='s0!B2',values=[['value']]),dict(op='set_print_area',target='s0!A1:C4',orientation='landscape',repeat_rows='1:1')])
    w=load_workbook(e.output);s=w.active
    assert str(s.data_validations.dataValidation[0].sqref)=='C2:C4' and s.freeze_panes=='B2'
    assert w['hidden'].sheet_state=='hidden' and w['hidden']['A1'].value=='untouched'
    assert s.auto_filter.ref=='A1:C4' and s.print_title_rows=='$1:$1'


def test_inspection_can_read_beyond_initial_window(tmp_path):
    e=editor(tmp_path,lambda w:setattr(w.active['A30'],'value','later'))
    assert e.inspect()['sheets'][0]['view_truncated']
    result=e.inspect(node_ids=['s0!A30:B30'],detail=True)
    assert result['nodes'][0]['value']=='later' and len(result['nodes'])==2


def test_default_inspection_does_not_expand_blank_cells(tmp_path):
    e=editor(tmp_path,lambda w:(setattr(w.active['A1'],'value','header'), setattr(w.active['A30'],'value','tail')))
    result=e.inspect()
    assert [node['id'] for node in result['nodes']] == ['s0!A1']
    assert result['sheets'][0]['used_range'] == 'A1:A30'
    assert result['sheets'][0]['default_view_note'].startswith('Only non-empty cells')


def test_custom_xml_payload_and_relationship_survive_multiple_batches(tmp_path):
    from zipfile import ZipFile, ZIP_DEFLATED
    from lxml import etree
    e=editor(tmp_path)
    with ZipFile(e.template) as z:parts={n:z.read(n) for n in z.namelist()}
    name='customXml/item1.xml';parts[name]=b'<metadata><key>keep verbatim</key></metadata>'
    rels=etree.fromstring(parts['xl/_rels/workbook.xml.rels'])
    etree.SubElement(rels,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',Id='rId99',Target='../customXml/item1.xml',Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml')
    parts['xl/_rels/workbook.xml.rels']=etree.tostring(rels)
    with ZipFile(e.template,'w',ZIP_DEFLATED) as z:
        for n,data in parts.items():z.writestr(n,data)
    e=XlsxEditor(e.template,e.output,e.asset_path)
    for version in range(2):
        e.apply(batch_id=str(version),version=version,edits=[dict(op='set_cells',target='s0!A1',values=[[version]])])
    with ZipFile(e.output) as z:
        assert z.read(name)==parts[name]
        rels=etree.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        assert len([r for r in rels if r.get('Type').endswith('/customXml')])==1


def test_inspection_does_not_materialize_default_column_dimensions(tmp_path):
    e=editor(tmp_path,lambda w:setattr(w.active['D5'],'value','x'))
    before=dict(e.book.active.column_dimensions)
    e.inspect(detail=True,node_ids=['s0!A1:D5'])
    assert dict(e.book.active.column_dimensions)==before
    e.apply(batch_id='a',version=0,edits=[dict(op='set_cells',target='s0!A1',values=[['new']])])
    assert dict(load_workbook(e.output).active.column_dimensions)==before


def test_oversized_text_is_not_silently_truncated(tmp_path):
    e=editor(tmp_path);before=e.output.read_bytes()
    with pytest.raises(ValueError,match='Excel limit'):
        e.apply(batch_id='too-long',version=0,edits=[dict(op='set_cells',target='s0!A1',values=[['x'*32768]])])
    assert e.output.read_bytes()==before


def test_horizontal_pagination_can_repeat_identity_columns(tmp_path):
    e=editor(tmp_path)
    e.apply(batch_id='print',version=0,edits=[dict(op='set_print_area',target='s0!A1:Y8',repeat_rows='1:2',repeat_columns='A:B',fit_to_width=0)])
    s=load_workbook(e.output).active
    assert s.print_title_cols=='$A:$B' and s.print_title_rows=='$1:$2' and s.page_setup.fitToWidth==0


def test_print_area_cannot_hide_existing_content(tmp_path):
    e=editor(tmp_path,lambda w:(setattr(w.active['A1'],'value','keep'), setattr(w.active['C1'],'value','also keep')))
    with pytest.raises(ValueError,match='hide existing content'):
        e.apply(batch_id='print',version=0,edits=[dict(op='set_print_area',target='s0!A1:B1',source_refs=[],reason='too narrow')])


def test_inspecting_empty_future_rows_does_not_expand_used_range(tmp_path):
    e=editor(tmp_path,lambda w:setattr(w.active['A1'],'value','existing'))
    before=set(e.book.active._cells)
    result=e.inspect(node_ids=['s0!A100:C101'],detail=True)
    assert len(result['nodes'])==6 and all(n['value'] is None for n in result['nodes'])
    assert set(e.book.active._cells)==before and e.book.active.max_row==1


def test_image_bounds_inspection_does_not_create_cells(tmp_path):
    from openpyxl.drawing.image import Image as WorksheetImage

    photo = tmp_path / "photo.png"
    Image.new("RGB", (10, 10), "blue").save(photo)
    sheet = Workbook().active
    sheet.add_image(WorksheetImage(photo), "Z100")
    before = dict(sheet._cells)
    assert XlsxEditor._used_bounds(sheet) == (26, 100, 26, 100)
    assert sheet._cells == before
