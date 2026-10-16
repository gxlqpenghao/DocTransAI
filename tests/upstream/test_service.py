import hashlib
import json
from pathlib import Path

import httpx
import pytest

from doctransai.upstream.dataproxy.service import DataProxyClient, DataProxyError


def client(handler):
    return DataProxyClient('https://example.test', 'secret', transport=httpx.MockTransport(handler))


def test_pagination_preserves_filter_and_rejects_loop():
    requests = []
    def handle(r):
        requests.append(r)
        assert r.url.params['prefix'] == 'content'
        return httpx.Response(200, json={'entries': [{'path': 'content/a'}], 'next_cursor': 'same'})
    with client(handle) as dp:
        with pytest.raises(ValueError, match='Repeated'):
            list(dp.entries('ws', prefix='content'))
    assert len(requests) == 2


@pytest.mark.parametrize('quality,allow,accepted', [('complete', False, True), ('degraded', False, False), ('degraded', True, True), ('failed', True, False)])
def test_quality_policy(quality, allow, accepted):
    with client(lambda r: httpx.Response(200, json={'status': 'succeeded', 'parse_quality': quality})) as dp:
        if accepted:
            assert dp.wait('job', allow_degraded=allow)['parse_quality'] == quality
        else:
            with pytest.raises(ValueError, match='quality rejected'):
                dp.wait('job', allow_degraded=allow)


def test_conflict_and_no_blind_retry():
    calls = []
    def handle(r):
        calls.append(r)
        assert r.headers['If-Match'] == '"old"'
        assert r.content == b'new'
        return httpx.Response(409, json={'detail': 'secret must not be echoed'})
    with client(handle) as dp:
        with pytest.raises(DataProxyError) as error:
            dp.write('ws', 'state/progress.json', b'new', etag='"old"')
        assert 'secret' not in str(error.value)
        assert error.value.status == 409
    assert len(calls) == 1


def test_read_requests_identity_encoding_for_strong_etag():
    def handle(r):
        strong = r.headers.get('accept-encoding') == 'identity'
        return httpx.Response(200, content=b'{}', headers={'etag': '"hash"' if strong else 'W/"hash"'})
    with client(handle) as dp:
        _, etag = dp.read('ws', 'state/progress.json')
        assert etag == '"hash"'


@pytest.mark.parametrize('path', ['../escape', '/tmp/a', 'outputs/../../a', 'outputs\\a', 'content/a'])
def test_unsafe_or_readonly_write_rejected(path):
    with client(lambda r: pytest.fail('network must not be used')) as dp:
        with pytest.raises(ValueError):
            dp.write('ws', path, b'x')


def test_stream_limit_removes_partial(tmp_path):
    with client(lambda r: httpx.Response(200, content=b'abcd')) as dp:
        with pytest.raises(ValueError, match='limit'):
            dp.download('GET', '/file', tmp_path / 'out', max_bytes=3)
    assert not list(tmp_path.iterdir())


def test_snapshot_uses_file_api_with_hash_verification(tmp_path, monkeypatch):
    from doctransai.upstream.dataproxy import service
    from types import SimpleNamespace
    monkeypatch.setattr(service, 'read_artifact', lambda p: SimpleNamespace(artifact_manifest={'job_id': 'job'}))
    data = b'{}'
    entry = {'path': 'manifest.json', 'size_bytes': 2, 'sha256': hashlib.sha256(data).hexdigest()}
    urls = []
    def handle(r):
        urls.append(r.url.path)
        if r.url.path.endswith('/entries'):
            return httpx.Response(200, json={'entries': [entry], 'next_cursor': None})
        return httpx.Response(200, content=data)
    with client(handle) as dp:
        assert dp.materialize('ws', tmp_path / 'package', job_id='job').read_bytes() == data
    assert urls == ['/api/v1/workspaces/ws/entries', '/api/v1/workspaces/ws/files/manifest.json']
    entry['sha256'] = '0' * 64
    with client(handle) as dp:
        with pytest.raises(ValueError, match='integrity'):
            dp.materialize('ws', tmp_path / 'bad', job_id='job')


@pytest.mark.parametrize('url', ['http://example.test', 'https://user:pass@example.test', 'https://example.test/api', 'https://example.test/?key=secret'])
def test_url_validation(url):
    with pytest.raises(ValueError):
        DataProxyClient(url, 'secret')


def test_http_requires_exact_explicit_origin(monkeypatch):
    monkeypatch.delenv('DOCTRANSAI_DATAPROXY_ALLOWED_HTTP_ORIGIN',raising=False)
    with DataProxyClient('http://example.test:3006','secret',allowed_http_origin='http://example.test:3006'):
        pass
    for url in ['http://other.test:3006','http://example.test:3007','http://example.test:3006/api','http://user@example.test:3006']:
        with pytest.raises(ValueError):DataProxyClient(url,'secret',allowed_http_origin='http://example.test:3006')


def test_upload_timeout_recovers_after_404_without_reupload(tmp_path):
    source=tmp_path/'input.doc';source.write_bytes(b'fixture')
    calls=[]
    def handle(r):
        calls.append(r)
        assert r.headers['X-API-Key']=='secret'
        assert r.headers['Idempotency-Key']=='stable'
        if r.method=='POST':raise httpx.ReadTimeout('response lost',request=r)
        assert r.url.path=='/api/v1/parse-jobs/by-idempotency-key'
        return httpx.Response(404 if len(calls)==2 else 200,json={'job_id':'original','status':'running'})
    events=[]
    with client(handle) as dp:
        assert dp.upload(source,request_id='stable',progress=events.append,recovery_interval=0)['job_id']=='original'
    assert [r.method for r in calls]==['POST','GET','GET']
    assert len(events)==2


def test_unresolved_upload_preserves_unknown_outcome(tmp_path):
    from doctransai.upstream.dataproxy.service import UploadOutcomeUnknown
    source=tmp_path/'input.doc';source.write_bytes(b'fixture');methods=[]
    def handle(r):
        methods.append(r.method)
        if r.method=='POST':raise httpx.ReadTimeout('lost',request=r)
        return httpx.Response(404)
    with client(handle) as dp:
        with pytest.raises(UploadOutcomeUnknown):dp.upload(source,request_id='stable',recovery_attempts=2,recovery_interval=0)
    assert methods==['POST','GET','GET']


def test_lookup_authorization_error_is_not_retried():
    with client(lambda r:httpx.Response(403)) as dp:
        with pytest.raises(DataProxyError) as exc:dp.find_by_request_id('stable')
    assert exc.value.status==403
