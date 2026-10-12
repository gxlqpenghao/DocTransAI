import hashlib
import json
from pathlib import Path
import zipfile

import httpx
import pytest

from doctransai.data_layer.artifact import read_artifact, unpack_artifact, package_path
from doctransai.data_layer.view import SourceView
from doctransai.upstream.dataproxy.client import fetch_parse_artifact


def make_package(tmp_path):
    # Generic empty-evidence package: tests transport and identity, not semantic quality.
    root = tmp_path / 'original'
    (root/'content').mkdir(parents=True)
    (root/'schema').mkdir()
    (root/'source').mkdir()
    (root/'source/input.txt').write_text('Original /opt/data text')
    schema_dir = Path(__file__).resolve().parents[2]/'src/doctransai/data_layer/contracts'
    (root/'schema/data_assets').mkdir()
    schemas = {}
    for file in schema_dir.glob('*.json'):
        relative = ('schema/' if file.name == 'parse_artifact_manifest.schema.json' else 'schema/data_assets/') + file.name
        (root/relative).write_bytes(file.read_bytes())
        if file.name != 'parse_artifact_manifest.schema.json':
            schemas[file.name.removesuffix('.schema.json')] = relative
    digest = hashlib.sha256((root/'source/input.txt').read_bytes()).hexdigest()
    bundle = dict(bundle_type='ParsedDocumentBundle',contract_version='data_asset_pack',database_writes=False,
                  generated_at='2026-09-09',capabilities={},components={},summary={},reports={},issue_buckets={},
                  documents=[dict(document_id='doc-generic',source_path='source/input.txt',source_checksum=digest)],parse_errors=[])
    (root/'content/parsed_document_bundle.json').write_text(json.dumps(bundle))
    files=[dict(path=p.relative_to(root).as_posix(),size_bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.rglob('*') if p.is_file()]
    manifest=dict(artifact_type='DataProxyParseArtifact',contract_version='parse_artifact',job_id='job',project_id='project',created_at='2026-09-09T00:00:00Z',reference_base='package_root',
        entrypoints={'parsed_document_bundle':dict(path='content/parsed_document_bundle.json',contract_version='data_asset_pack',schema_path='schema/data_assets/parsed_document_bundle.schema.json',reference_base='package_root')},
        schemas=schemas,task=dict(status='succeeded',success=True,failure=None),quality=dict(status='complete',complete=True,summary={},warnings=[],missing_components=[],parse_errors=[]),
        source=[dict(path='source/input.txt',original_filename='input.txt',sha256=digest,size_bytes=(root/'source/input.txt').stat().st_size)],components={},integrity=dict(algorithm='sha256',files=files),capabilities={})
    (root/'manifest.json').write_text(json.dumps(manifest))
    archive=tmp_path/'package.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for p in root.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(root))
    return root,archive


def test_portable_root_and_original_source(tmp_path):
    root,archive=make_package(tmp_path)
    manifest=unpack_artifact(archive,tmp_path/'moved')
    corpus=read_artifact(manifest)
    source=SourceView(corpus)
    assert source.source_file.read_text()=='Original /opt/data text'
    assert source.source_file.parent.parent==tmp_path/'moved'


def test_tampered_source_rejected(tmp_path):
    root,_=make_package(tmp_path)
    (root/'source/input.txt').write_text('changed')
    with pytest.raises(ValueError,match='integrity'):read_artifact(root/'manifest.json')


@pytest.mark.parametrize('name',['../outside','/etc/passwd','C:/file','..\\file'])
def test_unsafe_path_rejected(tmp_path,name):
    with pytest.raises(ValueError):package_path(tmp_path,name)


def test_failed_quality_rejected(tmp_path):
    root,_=make_package(tmp_path);p=root/'manifest.json';m=json.loads(p.read_text());m['quality']['status']='failed';p.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='quality failed'):read_artifact(p)


def test_zip_traversal_not_extracted(tmp_path):
    p=tmp_path/'bad.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('../outside','bad')
    with pytest.raises(ValueError):unpack_artifact(p,tmp_path/'result')
    assert not (tmp_path/'outside').exists()
    assert not (tmp_path/'result').exists()


def test_service_upload_poll_download_and_receipt(tmp_path):
    root,archive=make_package(tmp_path);requests=[]
    def handle(request):
        requests.append(request)
        if request.method=='POST':
            assert request.headers['Idempotency-Key']=='same-logical-request'
            assert request.headers['X-API-Key']=='secret'
            return httpx.Response(202,json=dict(job_id='job',status='queued'))
        if request.url.path.endswith('/artifact'):return httpx.Response(200,content=archive.read_bytes())
        return httpx.Response(200,json=dict(job_id='job',status='succeeded',parse_quality='complete',artifact_available=True))
    dest=tmp_path/'download'
    p=fetch_parse_artifact(root/'source/input.txt',dest,base_url='https://example.test',api_key='secret',idempotency_key='same-logical-request',transport=httpx.MockTransport(handle),poll_interval=0)
    assert p.exists() and len(requests)==3
    assert 'secret' not in (dest/'parse-request.json').read_text()


@pytest.mark.parametrize('state',['failed','unknown'])
def test_service_stops_on_invalid_or_failed_state(tmp_path,state):
    source=tmp_path/'s.txt';source.write_text('test')
    def handle(request):return httpx.Response(202,json=dict(job_id='job',status=state))
    with pytest.raises(ValueError):fetch_parse_artifact(source,tmp_path/'job',base_url='https://example.test',api_key='secret',transport=httpx.MockTransport(handle),poll_interval=0)
    assert not (tmp_path/'job/artifact.zip').exists()
