"""Complete project integration, keeping conversion and remote publication distinct."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import uuid

from doctransai.config import RuntimeConfig
from doctransai.settings import env_values, setting
from doctransai.conversion import convert
from doctransai.types import TaskSpec
from .service import DataProxyClient, save_receipt


def run_remote(*, base_url: str, api_key: str, template: Path, output_dir: Path,
               instruction: str | None = None, config: RuntimeConfig, source: Path | None = None,
               job_id: str | None = None, mode='zip', request_id=None, run_id=None,
               allow_degraded=True, timeout=1800, transport=None, progress=None,
               workspace_id=None, event_callback=None, allowed_http_origin=None):
    allowed_http_origin = allowed_http_origin or setting('DOCTRANSAI_DATAPROXY_ALLOWED_HTTP_ORIGIN', env_values(config.env_file))
    def event(phase, message):
        if event_callback:
            event_callback({'phase': phase, 'message': message})
    if mode not in {'zip', 'workspace'}:
        raise ValueError('Mode must be zip or workspace')
    if bool(source) == bool(job_id):
        raise ValueError('Provide exactly one of source or existing job ID')
    if workspace_id and (mode != 'workspace' or source is not None):
        raise ValueError('An existing workspace requires workspace mode and a job ID')
    if not template.is_file() or (source is not None and not source.is_file()):
        raise ValueError('Input file does not exist')
    if output_dir.exists():
        raise ValueError('Use a new output directory; recover using saved identities')
    output_dir.mkdir(parents=True)
    receipt_path = output_dir / 'integration.json'
    receipt = dict(mode=mode, request_id=request_id or str(uuid.uuid4()),
                   run_id=run_id or str(uuid.uuid4()), job_id=job_id,
                   base_url=base_url, workspace_id=workspace_id, status='preparing')
    def save(**updates):
        receipt.update(updates)
        save_receipt(receipt_path, receipt)
    save()
    try:
        with DataProxyClient(base_url, api_key, timeout=timeout, transport=transport, allowed_http_origin=allowed_http_origin) as dp:
            if source is not None:
                event('parsing', '正在上传源文档并请求解析；目标模板保留在本地。')
                job = dp.upload(source, request_id=receipt['request_id'], progress=lambda message:event('parsing', message))
                job_id = job['job_id']
                save(job_id=job_id, status='parsing')
            def record(job):
                event('parsing', 'DataProxy：' + str(job.get('stage') or job.get('status')))
                save(job_status=job.get('status'), stage=job.get('stage'),
                     parse_quality=job.get('parse_quality'), warnings=job.get('warnings'),
                     failure_reason=job.get('failure_reason'),
                     knowledge_base_id=job.get('knowledge_base_id'), document_ids=job.get('document_ids'))
            dp.wait(job_id, allow_degraded=allow_degraded, progress=record)
            event('reading', '正在读取并校验解析资料。')
            if mode == 'zip':
                manifest = dp.artifact(job_id, output_dir / 'input')
            else:
                if workspace_id:
                    ws = dp.request('GET', dp.workspace_path(workspace_id)).json()
                    if ws['parse_job_id'] != job_id:
                        raise ValueError('Existing workspace belongs to a different parse task')
                    save(run_id=ws['run_id'])
                else:
                    ws = dp.create_workspace(job_id, receipt['run_id'])
                save(workspace_id=ws['workspace_id'])
                manifest = dp.materialize(ws['workspace_id'], output_dir / 'input' / 'package', job_id=job_id)
            quality = json.loads(manifest.read_text())['quality']
            if quality['status'] != 'complete' and not (allow_degraded and quality['status'] == 'degraded'):
                raise ValueError('Artifact quality rejected')
            save(status='input_validated', manifest=str(manifest))
        # Conversion has its own model budget. DataProxy polling budget never includes LLM time.
        event('converting', '正在依据源材料填写模板并渲染检查。')
        result = convert(TaskSpec(manifest, template, output_dir / 'conversion', instruction),
                         config=config, progress=progress)
        save(conversion=asdict(result), status='converted' if result.execution_status == 'completed' else 'conversion_failed')
        if result.execution_status != 'completed':
            return receipt
        from doctransai.audit import audit_document
        event('auditing', '正在生成字段审计，核对填写依据与未填写原因。')
        audit = audit_document(output_dir / 'conversion', config=config, **({'progress':progress} if progress else {}))
        save(audit_status=audit['status'])
        if audit['status'] != 'assessed':
            save(status='audit_failed')
            return receipt
        if mode == 'workspace':
            event('publishing', '正在回写工作区并校验导出文件。')
            publish_workspace(base_url=base_url, api_key=api_key, receipt_path=receipt_path,
                              timeout=timeout, transport=transport, allowed_http_origin=allowed_http_origin)
            receipt = json.loads(receipt_path.read_text())
        else:
            save(status='completed')
        event('completed', '转换与字段审计已完成。')
        return receipt
    except Exception as exc:
        # Preserve local output and stable IDs for recovery, without copying provider messages.
        save(status='publication_failed' if receipt.get('status') == 'converted' else 'failed',
             error_type=type(exc).__name__, error_http_status=getattr(exc, 'status', None))
        raise


def publish_workspace(*, base_url, api_key, receipt_path: Path, timeout=1800, transport=None, replace_audit=False, allowed_http_origin=None):
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('mode') != 'workspace' or receipt.get('conversion', {}).get('execution_status') != 'completed':
        raise ValueError('Only a completed workspace conversion may be published')
    root = receipt_path.parent
    files = [root / 'conversion' / ('result' + suffix) for suffix in ('.docx', '.xlsx')]
    files = [p for p in files if p.is_file()] + [root / 'conversion' / 'review.json']
    if len(files) != 2 or not all(p.is_file() for p in files):
        raise ValueError('Completed conversion result or review report missing')
    audit_path = root / 'conversion' / 'audit.json'
    audit = json.loads(audit_path.read_text())
    if audit['status'] != 'assessed' or audit['document_sha256'] != hashlib.sha256(files[0].read_bytes()).hexdigest():
        raise ValueError('Completed field audit matching the output is required')
    files += [audit_path, root / 'conversion' / 'audit.html']
    receipt.update(status='publishing', audit_status='assessed')
    save_receipt(receipt_path, receipt)
    wsid = receipt['workspace_id']
    published = []
    with DataProxyClient(base_url, api_key, timeout=timeout, transport=transport, allowed_http_origin=allowed_http_origin) as dp:
        entries = {e['path']: e for e in dp.entries(wsid)}
        for file in files:
            target = 'outputs/' + file.name
            data = file.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            existing = entries.get(target)
            if existing:
                if existing['sha256'] != sha:
                    if replace_audit and file.name in {'audit.json', 'audit.html'}:
                        _, etag = dp.read(wsid, target)
                        if not etag:
                            raise ValueError('Audit replacement requires ETag')
                        dp.write(wsid, target, data, etag=etag)
                    else:
                        raise ValueError('Workspace result differs; use a new run ID instead of overwriting')
            else:
                dp.write(wsid, target, data)
            actual, _ = dp.read(wsid, target)
            if hashlib.sha256(actual).hexdigest() != sha:
                raise ValueError('Published output verification failed')
            published.append({'path': target, 'sha256': sha})
        state_path = 'state/doctransai.json'
        etag = None
        if state_path in entries:
            _, etag = dp.read(wsid, state_path)
        dp.write(wsid, state_path, json.dumps({'status': 'completed', 'files': published}).encode(),
                 content_type='application/json', etag=etag)
        archive = root / 'workspace-export.zip'
        if archive.exists():
            import zipfile
            with zipfile.ZipFile(archive) as z:
                complete = all(item['path'] in z.namelist() and hashlib.sha256(z.read(item['path'])).hexdigest() == item['sha256'] for item in published)
            if not complete:
                archive.rename(root / ('workspace-export-previous-' + uuid.uuid4().hex[:8] + '.zip'))
        if not archive.exists():
            dp.export(wsid, archive)
        import zipfile
        with zipfile.ZipFile(archive) as z:
            for item in published:
                if hashlib.sha256(z.read(item['path'])).hexdigest() != item['sha256']:
                    raise ValueError('Workspace export does not match published results')
    receipt.update(status='completed', published=published, workspace_export=str(archive))
    save_receipt(receipt_path, receipt)
    return receipt
