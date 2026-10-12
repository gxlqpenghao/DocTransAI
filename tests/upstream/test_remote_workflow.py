from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import zipfile

import httpx
import pytest

from doctransai.upstream.dataproxy.workflow import publish_workspace


def test_publish_verifies_export_and_recovers_without_overwrite(tmp_path):
    conversion = tmp_path / 'conversion'
    conversion.mkdir()
    (conversion / 'result.docx').write_bytes(b'result-bytes')
    (conversion / 'review.json').write_bytes(b'{}')
    (conversion / 'audit.json').write_text(json.dumps({'status':'assessed','document_sha256':hashlib.sha256(b'result-bytes').hexdigest()}))
    (conversion / 'audit.html').write_text('<html>audit</html>')
    receipt = tmp_path / 'integration.json'
    receipt.write_text(json.dumps({'mode': 'workspace', 'workspace_id': 'ws',
                                   'conversion': {'execution_status': 'completed'}}))
    stored, writes = {}, []
    def handle(r):
        if r.url.path.endswith('/entries'):
            return httpx.Response(200, json={'entries': [{'path': p, 'sha256': hashlib.sha256(v).hexdigest()} for p,v in stored.items()], 'next_cursor': None})
        if '/files/' in r.url.path:
            name = r.url.path.split('/files/')[1]
            if r.method == 'PUT':
                if name in stored:
                    assert r.headers['if-match'] == '"version"'
                writes.append(name)
                stored[name] = r.content
                return httpx.Response(200, json={})
            return httpx.Response(200, content=stored[name], headers={'ETag': '"version"'})
        assert r.url.path.endswith('/export')
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as z:
            for k,v in stored.items():
                z.writestr(k, v)
        return httpx.Response(200, content=out.getvalue())
    kwargs = dict(base_url='https://example.test', api_key='secret', receipt_path=receipt,
                  transport=httpx.MockTransport(handle))
    assert publish_workspace(**kwargs)['status'] == 'completed'
    assert publish_workspace(**kwargs)['status'] == 'completed'
    assert writes.count('outputs/result.docx') == 1
    (conversion / 'audit.html').write_text('<html>revised audit</html>')
    assert publish_workspace(**kwargs, replace_audit=True)['status'] == 'completed'
    assert writes.count('outputs/result.docx') == 1
    assert writes.count('outputs/audit.html') == 2
    assert list(tmp_path.glob('workspace-export-previous-*.zip'))
    (conversion / 'result.docx').write_bytes(b'changed')
    with pytest.raises(ValueError, match='audit matching'):
        publish_workspace(**kwargs)


def test_failed_conversion_cannot_publish(tmp_path):
    receipt = tmp_path / 'integration.json'
    receipt.write_text(json.dumps({'mode': 'workspace', 'conversion': {'execution_status': 'failed'}}))
    with pytest.raises(ValueError, match='completed'):
        publish_workspace(base_url='https://example.test', api_key='secret', receipt_path=receipt)


def test_upload_failure_preserves_request_id_without_secret(tmp_path):
    from doctransai.upstream.dataproxy.workflow import run_remote
    from doctransai.config import RuntimeConfig
    source, template = tmp_path / 'source.txt', tmp_path / 'template.docx'
    source.write_text('source'); template.write_bytes(b'placeholder')
    def handle(r):
        raise httpx.ReadTimeout('unknown submit outcome')
    with pytest.raises(httpx.ReadTimeout):
        run_remote(base_url='https://example.test', api_key='private-key', template=template,
                   source=source, output_dir=tmp_path / 'run', instruction='fill', config=RuntimeConfig(),
                   request_id='stable-upload-id', transport=httpx.MockTransport(handle))
    text = (tmp_path / 'run/integration.json').read_text()
    assert 'stable-upload-id' in text and 'private-key' not in text
    assert json.loads(text)['status'] == 'failed'


def test_http_failure_receipt_keeps_status_without_body(tmp_path):
    from doctransai.upstream.dataproxy.workflow import run_remote
    from doctransai.config import RuntimeConfig
    template = tmp_path / 'template.docx'; template.write_bytes(b'placeholder')
    with pytest.raises(ValueError):
        run_remote(base_url='https://example.test', api_key='secret', template=template, job_id='job',
            output_dir=tmp_path/'run', instruction='fill', config=RuntimeConfig(),
            transport=httpx.MockTransport(lambda r: httpx.Response(429, text='private-server-detail')))
    text = (tmp_path/'run/integration.json').read_text()
    assert json.loads(text)['error_http_status'] == 429
    assert 'private-server-detail' not in text and 'secret' not in text


def test_manifest_cannot_bypass_quality_policy(tmp_path, monkeypatch):
    from doctransai.upstream.dataproxy import workflow
    from doctransai.config import RuntimeConfig
    template = tmp_path / 'template.docx'
    template.write_bytes(b'placeholder')
    def artifact(self, job_id, destination):
        destination.mkdir(parents=True)
        manifest = destination / 'manifest.json'
        manifest.write_text(json.dumps({'quality': {'status': 'degraded'}}))
        return manifest
    monkeypatch.setattr(workflow.DataProxyClient, 'artifact', artifact)
    monkeypatch.setattr(workflow, 'convert', lambda *a, **k: pytest.fail('must not invoke model'))
    with pytest.raises(ValueError, match='Artifact quality rejected'):
        workflow.run_remote(base_url='https://example.test', api_key='secret', template=template,
            job_id='job', output_dir=tmp_path / 'run', instruction='fill', config=RuntimeConfig(),
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'status':'succeeded','parse_quality':'complete'})))


def test_existing_workspace_does_not_recreate_expired_zip(tmp_path, monkeypatch):
    from doctransai.upstream.dataproxy import workflow
    from doctransai.config import RuntimeConfig
    from doctransai.types import ConversionResult
    template = tmp_path / 'template.docx'; template.write_bytes(b'placeholder')
    def materialize(self, wsid, destination, *, job_id):
        destination.mkdir(parents=True)
        manifest = destination / 'manifest.json'
        manifest.write_text(json.dumps({'quality': {'status': 'complete'}}))
        return manifest
    monkeypatch.setattr(workflow.DataProxyClient, 'materialize', materialize)
    monkeypatch.setattr(workflow, 'convert', lambda *a, **k: ConversionResult('failed', 'not_run', None, 'review.json'))
    def handle(r):
        assert r.method == 'GET'
        if '/parse-jobs/' in r.url.path:
            return httpx.Response(200, json={'status': 'succeeded', 'parse_quality': 'complete', 'artifact_available': False})
        assert r.url.path == '/api/v1/workspaces/ws'
        return httpx.Response(200, json={'workspace_id':'ws','parse_job_id':'job','run_id':'original-run'})
    result = workflow.run_remote(base_url='https://example.test', api_key='secret', template=template,
        job_id='job', workspace_id='ws', mode='workspace', output_dir=tmp_path/'run', instruction='fill',
        config=RuntimeConfig(), transport=httpx.MockTransport(handle))
    assert result['run_id'] == 'original-run' and result['status'] == 'conversion_failed'


def test_remote_command_exposes_output_budget(monkeypatch):
    from doctransai.upstream.dataproxy import command
    monkeypatch.setenv('DOCTRANSAI_DATAPROXY_BASE_URL', 'https://example.test')
    monkeypatch.setenv('DOCTRANSAI_DATAPROXY_API_KEY', 'secret')
    captured = {}
    def run(**kwargs):
        captured.update(kwargs)
        return {'status': 'completed'}
    monkeypatch.setattr(command, 'run_remote', run)
    assert command.main(['--job-id','job','--template','template.docx','--output-dir','run',
                         '--instruction','fill','--max-output-tokens','12000']) == 0
    assert captured['config'].max_output_tokens == 12000
    assert captured['config'].reasoning_effort == 'high'


@pytest.mark.parametrize('audit_status,expected', [('assessed','completed'),('needs_manual_audit','audit_failed')])
def test_remote_requires_semantic_audit_after_conversion(tmp_path, monkeypatch, audit_status, expected):
    from doctransai.upstream.dataproxy import workflow
    from doctransai.config import RuntimeConfig
    from doctransai.types import ConversionResult
    import doctransai.audit
    template=tmp_path/'template.docx';template.write_bytes(b'template')
    def artifact(self, job, destination):
        destination.mkdir(parents=True)
        p=destination/'manifest.json';p.write_text(json.dumps({'quality':{'status':'complete'}}));return p
    monkeypatch.setattr(workflow.DataProxyClient,'artifact',artifact)
    monkeypatch.setattr(workflow,'convert',lambda *a,**k:ConversionResult('completed','not_run','result.docx','review.json'))
    monkeypatch.setattr(doctransai.audit,'audit_document',lambda *a,**k:{'status':audit_status})
    result=workflow.run_remote(base_url='https://example.test',api_key='secret',template=template,job_id='job',
        output_dir=tmp_path/'run',instruction='fill',config=RuntimeConfig(),
        transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'status':'succeeded','parse_quality':'complete'})))
    assert result['status']==expected
