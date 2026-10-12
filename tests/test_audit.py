import json
from types import SimpleNamespace

import pytest

from doctransai.audit import ledger, validate_assessments, save_audit


def field(key='n1', after='value'):
    return dict(field_id=key,location='table 0 row 0 column 1',before='{field}',after=after,
                image_refs=[],operation_ids=[],field_label=key,category='filled_low',reason='pending',review_action='check',evidence=[])


class Source:
    objects = {'ev1': {'text':'Direct source value'}}
    def check_refs(self, refs):
        if any(ref not in self.objects for ref in refs):
            raise ValueError('unknown evidence')


def assessment(key='n1', quote='Direct source value'):
    return dict(field_id=key,field_label='Field',category='filled_high',reason='Direct correspondence',
                review_action='',evidence=[{'ref':'ev1','quote':quote}])


def test_reference_existence_is_not_high_confidence():
    a={'fields':[field()]}
    validate_assessments(a,[assessment(quote='Invented quote')],Source())
    assert a['fields'][0]['category']=='filled_low'
    assert a['fields'][0]['review_action']


def test_zero_is_filled_and_direct_quote_supports_high():
    a={'fields':[field(after=0)]}
    validate_assessments(a,[assessment()],Source())
    assert a['fields'][0]['category']=='filled_high'


def test_operation_evidence_is_valid_but_cannot_alone_support_high():
    a={'fields':[field()],'operations':[{'operation_id':'step-1-edit-0'}]}
    item=assessment();item['evidence']=[{'ref':'step-1-edit-0','quote':'write succeeded'}]
    validate_assessments(a,[item],Source())
    assert a['fields'][0]['category']=='filled_low'
    assert a['fields'][0]['evidence'][0]['kind']=='operation_log'


def test_partial_coverage_and_unknown_ref_never_partially_promote():
    a={'fields':[field(),field('n2')]}
    with pytest.raises(ValueError,match='coverage'):
        validate_assessments(a,[assessment()],Source())
    bad=assessment('n2');bad['evidence'][0]['ref']='missing'
    with pytest.raises(ValueError,match='unknown'):
        validate_assessments(a,[assessment(),bad],Source())
    assert all(f['category']=='filled_low' for f in a['fields'])


def test_ledger_preserves_failed_edits_but_does_not_apply_them(tmp_path):
    (tmp_path/'review.json').write_text(json.dumps({'execution_status':'completed'}))
    (tmp_path/'input.json').write_text(json.dumps({'document':{'nodes':[
        {'id':'n1','kind':'cell','text':'original','where':'table 0 row 0 column 0'},
        {'id':'n2','kind':'paragraph','cell_id':'n1','text':'original'}]}}))
    event={'kind':'tool','step':1,'success':False,'arguments':{'edits':[{'op':'set_text','target':'n2','text':'wrong'}]},
           'result':{'rolled_back':True,'message':'rejected','nodes':[{'id':'n1','kind':'cell','text':'wrong'}]}}
    (tmp_path/'trace.jsonl').write_text(json.dumps(event)+'\n')
    audit=ledger(tmp_path)
    assert audit['fields'][0]['after']=='original'
    assert audit['operations'][0]['rolled_back'] is True
    assert audit['fields'][0]['operation_ids']==['step-1-edit-0']


def test_html_escapes_document_content(tmp_path):
    a={'fields':[field(after='<script>bad</script>')],'operations':[], 'status':'pending','document_sha256':'hash'}
    save_audit(tmp_path,a)
    html=(tmp_path/'audit.html').read_text()
    assert '<script>bad</script>' not in html and '&lt;script&gt;' in html
