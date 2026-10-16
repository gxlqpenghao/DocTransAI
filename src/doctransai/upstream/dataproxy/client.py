"""Thin HTTP client for DataProxy parse jobs; no SSH or parser dependency."""
from pathlib import Path
import json
import math
import time
from urllib.parse import quote, urlsplit
import uuid

import httpx

from doctransai.data_layer.artifact import unpack_artifact
from .service import validate_origin, DataProxyClient


def fetch_parse_artifact(source: Path, output_dir: Path, *, base_url: str, api_key: str,
                         idempotency_key: str | None = None, timeout: float = 900,
                         transport=None, poll_interval: float = 2, allowed_http_origin=None):
    validate_origin(base_url, allowed_http_origin)
    if not api_key or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('API key and positive finite timeout are required')
    if output_dir.exists():
        raise ValueError('Use a new DataProxy output directory')
    if not source.is_file():
        raise ValueError('Source file does not exist')
    output_dir.mkdir(parents=True)
    key = idempotency_key or str(uuid.uuid4())
    receipt = {'idempotency_key': key, 'status': 'submitting'}
    def save():
        (output_dir / 'parse-request.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    save()
    deadline = time.monotonic() + timeout
    def budget():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('DataProxy task deadline exceeded; retain request key for retry')
        return min(30, remaining)
    with httpx.Client(base_url=base_url.rstrip('/')+'/', headers={'X-API-Key': api_key},
                      transport=transport, follow_redirects=False) as client:
        def checked(response):
            if response.status_code >= 300:
                raise ValueError(f'DataProxy HTTP {response.status_code}; see parse-request.json for task identity')
            return response
        with DataProxyClient(base_url, api_key, timeout=max(0.001, deadline-time.monotonic()),
                             transport=transport, allowed_http_origin=allowed_http_origin) as dp:
            result = dp.upload(source, request_id=key)
        job = result.get('job_id')
        if not isinstance(job, str) or not job:
            raise ValueError('DataProxy response has no job_id')
        receipt['job_id'] = job
        endpoint = 'api/v1/parse-jobs/' + quote(job, safe='')
        while True:
            budget()
            state = result.get('status')
            receipt['status'] = state
            save()
            if state == 'failed':
                raise ValueError('DataProxy parse job failed')
            if state == 'succeeded':
                if result.get('parse_quality') not in {'complete', 'degraded'} or not result.get('artifact_available'):
                    raise ValueError('DataProxy has no usable parse artifact')
                break
            if state not in {'queued', 'running'}:
                raise ValueError('Unknown DataProxy task state')
            time.sleep(min(poll_interval, max(0, deadline-time.monotonic())))
            result = checked(client.get(endpoint, timeout=budget())).json()
        archive = output_dir / 'artifact.zip'
        partial = output_dir / 'artifact.zip.part'
        try:
            with client.stream('GET', endpoint+'/artifact', timeout=budget()) as response:
                checked(response)
                size = 0
                with partial.open('wb') as file:
                    for chunk in response.iter_bytes():
                        budget()
                        size += len(chunk)
                        if size > 1024**3:
                            raise ValueError('DataProxy download exceeds 1 GiB limit')
                        file.write(chunk)
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    manifest = unpack_artifact(archive, output_dir / 'package')
    receipt['manifest'] = str(manifest.resolve())
    save()
    return manifest
