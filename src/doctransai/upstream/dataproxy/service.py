"""Project-key API. Secrets stay in memory; receipts belong to the caller."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import quote, urlsplit

import httpx

from doctransai.data_layer.artifact import package_path, read_artifact, unpack_artifact


def validate_origin(base_url, allowed_http_origin=None):
    url = urlsplit(base_url)
    if not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {'', '/'}:
        raise ValueError('DataProxy base URL must be an origin without /api')
    allowed = allowed_http_origin or os.environ.get('DOCTRANSAI_DATAPROXY_ALLOWED_HTTP_ORIGIN', '')
    local = url.hostname in {'localhost', '127.0.0.1', '::1'}
    if url.scheme != 'https' and not (url.scheme == 'http' and (local or base_url.rstrip('/') == allowed.rstrip('/'))):
        raise ValueError('DataProxy requires HTTPS; explicitly allow the exact HTTP origin in backend configuration')


class UploadOutcomeUnknown(TimeoutError):
    pass


class DataProxyError(ValueError):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code
        super().__init__(f"DataProxy HTTP {status}: {code}")


def save_receipt(path: Path, value: dict):
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    pending.replace(path)


class DataProxyClient:
    def __init__(self, base_url, api_key, *, timeout=1800, transport=None, allowed_http_origin=None):
        validate_origin(base_url, allowed_http_origin)
        if not api_key or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('API key and positive finite timeout required')
        self.deadline = time.monotonic() + timeout
        self.http = httpx.Client(base_url=base_url.rstrip('/'), headers={'X-API-Key': api_key},
                                 follow_redirects=False, transport=transport)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def budget(self):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError('DataProxy deadline exceeded; resume with the saved job/request/run ID')
        return min(120, left)

    @staticmethod
    def check(response):
        if response.status_code >= 300:
            # Never echo upstream bodies, which may contain credentials or private paths.
            raise DataProxyError(response.status_code, 'request_failed')
        return response

    def request(self, method, path, **kwargs):
        return self.check(self.http.request(method, path, timeout=self.budget(), **kwargs))

    def find_by_request_id(self, request_id):
        if not request_id or len(request_id) > 255:
            raise ValueError('A stable upload request ID is required')
        response = self.http.get('/api/v1/parse-jobs/by-idempotency-key',
            headers={'Idempotency-Key':request_id}, timeout=min(10, self.budget()))
        if response.status_code == 404:
            return None
        job = self.check(response).json()
        if not isinstance(job.get('job_id'), str) or not job['job_id']:
            raise ValueError('DataProxy response has no job_id')
        return job

    def upload(self, source: Path, *, request_id: str, progress=None, recovery_attempts=6, recovery_interval=2):
        if not request_id or len(request_id) > 255:
            raise ValueError('A stable upload request ID is required')
        try:
            with source.open('rb') as stream:
                job = self.request('POST', '/api/v1/parse-jobs',
                    headers={'Idempotency-Key': request_id}, files={'file': (source.name, stream)}).json()
            if not isinstance(job.get('job_id'), str) or not job['job_id']:
                raise ValueError('DataProxy response has no job_id')
            return job
        except httpx.TransportError as exc:
            if progress:
                progress('上传响应中断，正在用原请求编号找回任务；不会重复上传。')
            for attempt in range(recovery_attempts):
                try:
                    job = self.find_by_request_id(request_id)
                    if job:
                        if progress:progress('已找回原解析任务，继续查询进度。')
                        return job
                except httpx.TransportError:
                    pass
                if attempt + 1 < recovery_attempts:
                    time.sleep(min(recovery_interval, self.budget()))
            raise UploadOutcomeUnknown('上传结果尚未确认；已保留原请求编号，请稍后按原幂等键找回任务，不要创建新请求重复上传。') from exc

    @staticmethod
    def job_path(job_id):
        return '/api/v1/parse-jobs/' + quote(job_id, safe='')

    @staticmethod
    def workspace_path(workspace_id):
        return '/api/v1/workspaces/' + quote(workspace_id, safe='')

    def wait(self, job_id, *, allow_degraded=False, poll_seconds=2, progress=None):
        if not math.isfinite(poll_seconds) or poll_seconds < 0:
            raise ValueError('Invalid polling interval')
        while True:
            job = self.request('GET', self.job_path(job_id)).json()
            if progress:
                progress(job)
            status = job.get('status')
            if status == 'succeeded':
                accepted = {'complete', 'degraded'} if allow_degraded else {'complete'}
                if job.get('parse_quality') not in accepted:
                    raise ValueError('Parse quality rejected; inspect saved warnings or explicitly allow degraded')
                return job
            if status not in {'queued', 'running'}:
                raise ValueError(f'Parse task is not usable: {status}')
            time.sleep(min(poll_seconds, self.budget()))

    def download(self, method, endpoint, destination: Path, *, max_bytes=1024**3):
        if destination.exists():
            raise ValueError('Download destination already exists')
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + '.part')
        try:
            with self.http.stream(method, endpoint, timeout=self.budget()) as response:
                self.check(response)
                total = 0
                with partial.open('xb') as out:
                    for chunk in response.iter_bytes():
                        self.budget()
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError('DataProxy download exceeds limit')
                        out.write(chunk)
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
        return destination

    def artifact(self, job_id, destination):
        archive = self.download('GET', self.job_path(job_id) + '/artifact', destination / 'artifact.zip')
        manifest = unpack_artifact(archive, destination / 'package')
        if json.loads(manifest.read_text())['job_id'] != job_id:
            raise ValueError('Artifact job identity mismatch')
        return manifest

    def create_workspace(self, job_id, run_id):
        return self.request('POST', '/api/v1/workspaces',
                            json={'parse_job_id': job_id, 'run_id': run_id}).json()

    def entries(self, workspace_id, *, prefix='', limit=100):
        cursor, seen = None, set()
        while True:
            params = {'prefix': prefix, 'limit': limit}
            if cursor:
                params['cursor'] = cursor
            page = self.request('GET', self.workspace_path(workspace_id) + '/entries', params=params).json()
            yield from page['entries']
            cursor = page.get('next_cursor')
            if not cursor:
                return
            if cursor in seen:
                raise ValueError('Repeated workspace pagination cursor')
            seen.add(cursor)

    def read(self, workspace_id, path):
        endpoint = self.workspace_path(workspace_id) + '/files/' + quote(path, safe='/')
        # nginx gzip weakens ETag; If-Match requires the identity representation's strong validator.
        response = self.request('GET', endpoint, headers={'Accept-Encoding': 'identity'})
        return response.content, response.headers.get('etag')

    def write(self, workspace_id, path, data, *, etag=None, content_type='application/octet-stream'):
        package_path(Path('/workspace'), path)
        if path.split('/')[0] not in {'outputs', 'scratch', 'state'}:
            raise ValueError('Workspace path is read-only')
        headers = {'Content-Type': content_type}
        if etag is not None:
            headers['If-Match'] = etag
        return self.request('PUT', self.workspace_path(workspace_id) + '/files/' + quote(path, safe='/'),
                            headers=headers, content=data).json()

    def materialize(self, workspace_id, destination: Path, *, job_id):
        """Read the immutable source snapshot over file APIs; no artifact/export shortcut."""
        if destination.exists():
            raise ValueError('Workspace destination already exists')
        destination.mkdir(parents=True)
        count, total, seen = 0, 0, set()
        for entry in self.entries(workspace_id):
            name = entry['path']
            if name.split('/')[0] in {'outputs', 'scratch', 'state'}:
                continue
            target = package_path(destination, name)
            canonical = str(target.relative_to(destination)).casefold()
            if canonical in seen:
                raise ValueError('Duplicate workspace path')
            seen.add(canonical)
            size = entry['size_bytes']
            count += 1
            total += size
            if size < 0 or count > 20000 or total > 1024**3:
                raise ValueError('Workspace snapshot exceeds limits')
            self.download('GET', self.workspace_path(workspace_id) + '/files/' + quote(name, safe='/'),
                          target, max_bytes=size)
            with target.open('rb') as stream:
                sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            if target.stat().st_size != size or sha != entry['sha256']:
                raise ValueError('Workspace file integrity mismatch')
        manifest = destination / 'manifest.json'
        corpus = read_artifact(manifest)
        if corpus.artifact_manifest['job_id'] != job_id:
            raise ValueError('Workspace job identity mismatch')
        return manifest

    def export(self, workspace_id, destination):
        return self.download('POST', self.workspace_path(workspace_id) + '/export', destination)
