"""Loopback-only test UI. Files and credentials stay in the local backend."""
from __future__ import annotations

import argparse
from dataclasses import replace
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import quote, urlsplit
import uuid
import zipfile

from . import __version__
from .config import RuntimeConfig
from .settings import env_values, setting
from .upstream.dataproxy.service import save_receipt

SOURCE_TYPES = {'.pdf','.doc','.docx','.ppt','.pptx','.xlsx','.xlsm','.txt','.md','.markdown','.html','.htm','.png','.jpg','.jpeg'}
TEMPLATE_TYPES = {'.docx','.xlsx'}
MAX_SOURCE = 100 * 1024**2
MAX_TEMPLATE = 20 * 1024**2
MAX_REQUEST = MAX_SOURCE + MAX_TEMPLATE + 1024**2
FILES = {'result.docx':'conversion/result.docx', 'result.xlsx':'conversion/result.xlsx',
         'audit.html':'conversion/audit.html', 'audit.json':'conversion/audit.json',
         'review.json':'conversion/review.json', 'integration.json':'integration.json',
         'workspace-export.zip':'workspace-export.zip'}
TERMINAL = {'completed','failed','interrupted'}


def read_json(path, fallback=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return fallback


def safe_message(value, values):
    text = str(value)
    combined = {**values, **os.environ}
    for k, v in combined.items():
        if ('KEY' in k or 'TOKEN' in k or 'SECRET' in k) and isinstance(v, str) and v:
            text = text.replace(v, '<已隐藏>')
    return text[:1000]


def settings_config(settings, env_file):
    if not isinstance(settings, dict):
        raise ValueError('高级设置格式错误。')
    allowed = {'model','max_output_tokens','reasoning_effort','mode','allow_degraded'}
    if set(settings) - allowed:
        raise ValueError('包含不支持的设置；密钥和服务地址应在后端配置。')
    if settings.get('mode', 'zip') not in {'zip','workspace'}:
        raise ValueError('请选择ZIP或工作区方式。')
    if not isinstance(settings.get('allow_degraded', False), bool):
        raise ValueError('降级解析设置必须为布尔值。')
    config = RuntimeConfig.from_environment(env_file=env_file, _default_output_tokens=16000)
    overrides = {}
    for field in ('model','reasoning_effort'):
        value = settings.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > 256):
            raise ValueError('模型或思考强度设置不合法。')
        if value:
            overrides[field] = value.strip()
    if settings.get('model') and settings['model'] != config.model and not settings.get('reasoning_effort'):
        overrides['reasoning_effort'] = None
    if 'max_output_tokens' in settings:
        value = settings['max_output_tokens']
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1000000:
            raise ValueError('输出token上限应为1至1000000之间的整数。')
        overrides['max_output_tokens'] = value
    return replace(config, **overrides)


def upload_parts(body, content_type):
    if not content_type.startswith('multipart/form-data') or '\r' in content_type or '\n' in content_type:
        raise ValueError('请使用文件上传表单。')
    message = BytesParser(policy=email_policy).parsebytes(
        ('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode('ascii') + body)
    if not message.is_multipart():
        raise ValueError('上传内容不完整。')
    parts = {}
    for item in message.iter_parts():
        name = item.get_param('name', header='content-disposition')
        if name not in {'source','template','settings'} or name in parts:
            raise ValueError('上传表单包含重复或未知字段。')
        data = item.get_payload(decode=True)
        if not isinstance(data, bytes):
            raise ValueError('上传内容不完整。')
        if name in {'source','template'}:
            filename = (item.get_filename() or '').replace('\\','/').split('/')[-1]
            suffix = Path(filename).suffix.lower()
            if not filename or len(filename.encode('utf-8')) > 240 or any(ord(c)<32 for c in filename):
                raise ValueError('文件名无效或过长。')
            allowed = SOURCE_TYPES if name == 'source' else TEMPLATE_TYPES
            if suffix not in allowed:
                raise ValueError('目标模板仅支持DOCX、XLSX；DOC模板请先转为DOCX。' if name == 'template' else '当前不支持此源文档格式。')
            if not data or len(data) > (MAX_SOURCE if name=='source' else MAX_TEMPLATE):
                raise ValueError('文件不能为空，源文档上限100 MiB，模板上限20 MiB。')
            if name=='template':
                try:
                    with zipfile.ZipFile(io.BytesIO(data)) as archive:
                        required='word/document.xml' if suffix=='.docx' else 'xl/workbook.xml'
                        if required not in archive.namelist() or sum(i.file_size for i in archive.infolist())>200*1024**2:
                            raise ValueError('目标模板内容无效或解压大小超限。')
                except zipfile.BadZipFile as exc:
                    raise ValueError('目标模板不是有效的DOCX/XLSX文件，不能只修改扩展名。') from exc
            parts[name] = (filename, data)
        else:
            if len(data) > 32000:
                raise ValueError('设置内容过长。')
            parts[name] = data.decode('utf-8')
    if not {'source','template'} <= parts.keys():
        raise ValueError('请上传源文档和目标模板。')
    parts['settings'] = json.loads(parts.get('settings') or '{}')
    return parts


class LocalApp:
    def __init__(self, root, env_file=None, launcher=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.env_file = Path(env_file).resolve() if env_file else None
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.processes = {}
        self.stopping = False
        self.launcher = launcher or self.launch
        self.upload_gate = threading.Lock()
        for path in self.root.glob('*/web-job.json'):
            state = read_json(path, {})
            if state and state.get('status') not in TERMINAL:
                state.update(status='interrupted', message='本地服务已重启，此任务没有自动重跑。请查阅运行记录中的解析任务ID。')
                save_receipt(path, state)

    def configuration(self):
        checks = []
        thinking = {}
        defaults = {'model':'kimi-k3','max_output_tokens':16000,'reasoning_effort':'auto','mode':'zip','allow_degraded':False}
        try:
            values = env_values(self.env_file)
            cfg = settings_config({}, self.env_file)
            defaults.update(model=cfg.model, max_output_tokens=cfg.max_output_tokens, reasoning_effort=cfg.reasoning_effort)
            from .llm.client import DoctransaiLLMClient, DoctransaiLLMConfig
            def valid(v):
                return bool(v) and not any(x in v for x in ('replace-with','example.com','example/v1','<'))
            checks.append({'label':'DataProxy授权', 'ok': valid(setting('DOCTRANSAI_DATAPROXY_API_KEY',values)) and valid(setting('DOCTRANSAI_DATAPROXY_BASE_URL',values))})
            try:
                llm = DoctransaiLLMClient(DoctransaiLLMConfig(env_file=self.env_file,model_name=cfg.model,
                    reasoning_effort=cfg.reasoning_effort,temperature=cfg.temperature,token_parameter=cfg.token_parameter))
                from .settings import thinking_models
                thinking = thinking_models(llm.base_url)
                checks.append({'label':'LLM配置','ok':valid(llm.api_key) and valid(llm.base_url)})
            except ValueError:
                checks.append({'label':'LLM配置','ok':False})
            checks.append({'label':'文档渲染器','ok':bool(cfg.render_script and cfg.render_script.is_file() and shutil.which(cfg.render_python))})
        except (OSError, ValueError):
            checks.append({'label':'后端配置文件','ok':False})
        return {'version':__version__, 'token':self.token, 'defaults':defaults, 'checks':checks, 'thinking_models':thinking,
                'ready':bool(checks) and all(c['ok'] for c in checks), 'max_source_bytes':MAX_SOURCE,'max_template_bytes':MAX_TEMPLATE}

    def launch(self, job_dir):
        command = [sys.executable,'-m','doctransai.web','--worker',str(job_dir)]
        if self.env_file:
            command += ['--env-file',str(self.env_file)]
        with (job_dir/'worker.log').open('wb') as log:
            return subprocess.Popen(command, stdout=log, stderr=log, start_new_session=(os.name=='posix'))

    def submit(self, parts):
        settings_config(parts['settings'], self.env_file)
        if not self.configuration()['ready']:
            raise ValueError('后端配置尚未就绪。请配置DataProxy、LLM与文档渲染器后重启服务。')
        with self.lock:
            if self.stopping:
                raise RuntimeError('本地服务正在停止。')
            if any(p.poll() is None for p in self.processes.values()):
                raise RuntimeError('已有任务正在运行，请等待完成后再提交。')
            job_id = uuid.uuid4().hex
            job_dir = self.root/job_id
            job_dir.mkdir(mode=0o700)
            for kind in ('source','template'):
                filename, data = parts[kind]
                (job_dir/kind).mkdir()
                (job_dir/kind/filename).write_bytes(data)
            request = {'source':parts['source'][0], 'template':parts['template'][0], 'settings':parts['settings']}
            save_receipt(job_dir/'request.json', request)
            state = dict(id=job_id,status='queued',phase='queued',message='任务已创建，准备开始。',
                         source=request['source'],template=request['template'],mode=parts['settings'].get('mode','zip'),created_at=time.time(),events=[])
            save_receipt(job_dir/'web-job.json',state)
            try:
                self.processes[job_id] = self.launcher(job_dir)
            except Exception:
                state.update(status='failed',message='无法启动本地转换进程。请检查Python环境。')
                save_receipt(job_dir/'web-job.json',state)
                raise
            return self.status(job_id)

    def job_dir(self, job_id):
        if not re.fullmatch('[0-9a-f]{32}',job_id):
            raise FileNotFoundError
        path = self.root/job_id
        if not path.is_dir() or path.is_symlink():
            raise FileNotFoundError
        return path

    def status(self, job_id):
        path = self.job_dir(job_id)
        state = read_json(path/'web-job.json')
        if not state:
            raise FileNotFoundError
        process = self.processes.get(job_id)
        if process is not None and process.poll() is not None and state['status'] not in TERMINAL:
            state.update(status='failed',message='本地进程提前退出。请检查后端日志及运行记录。')
            save_receipt(path/'web-job.json',state)
        state['files'] = [{'name':name,'url':f'/api/jobs/{job_id}/files/{name}'} for name in FILES if (path/'run'/FILES[name]).is_file()]
        audit = read_json(path/'run/conversion/audit.json',{})
        state['audit'] = {'status':audit.get('status'),'counts':audit.get('counts',{})}
        receipt = read_json(path/'run/integration.json',{})
        state['parse_quality'] = receipt.get('parse_quality')
        state['job_id'] = receipt.get('job_id')
        state['workspace_id'] = receipt.get('workspace_id')
        state['warnings'] = receipt.get('warnings') or []
        return state

    def close(self):
        with self.lock:
            self.stopping=True
            processes=list(self.processes.items())
        for job_id, process in processes:
            if process.poll() is None:
                try:
                    if os.name == 'posix':os.killpg(process.pid, signal.SIGTERM)
                    else:process.terminate()
                except ProcessLookupError:continue
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if os.name=='posix':os.killpg(process.pid,signal.SIGKILL)
                    else:process.kill()
                path=self.root/job_id/'web-job.json';state=read_json(path,{})
                if state.get('status') not in TERMINAL:
                    state.update(status='interrupted',message='本地服务已停止；服务端解析任务可能仍在继续，记录已保留。')
                    save_receipt(path,state)


def run_worker(job_dir, env_file):
    from .upstream.dataproxy.workflow import run_remote
    path=Path(job_dir).resolve();request=read_json(path/'request.json');state=read_json(path/'web-job.json')
    values={}
    def update(phase=None,message=None,**extra):
        if phase:state['phase']=phase
        if message:
            state['message']=safe_message(message,values)
            if not state['events'] or state['events'][-1]['message'] != state['message']:
                state['events']=(state['events']+[{'at':time.time(),'message':state['message']}])[-100:]
        state.update(extra,updated_at=time.time());save_receipt(path/'web-job.json',state)
    try:
        values=env_values(env_file)
        update('parsing','开始解析源文档。',status='running')
        cfg=settings_config(request['settings'],env_file)
        result=run_remote(base_url=setting('DOCTRANSAI_DATAPROXY_BASE_URL',values),
            api_key=setting('DOCTRANSAI_DATAPROXY_API_KEY',values),
            source=path/'source'/request['source'],template=path/'template'/request['template'],
            output_dir=path/'run',instruction=request.get('instruction'),config=cfg,
            mode=request['settings'].get('mode','zip'),allow_degraded=request['settings'].get('allow_degraded',False),
            request_id='web-'+state['id'],run_id='web-'+state['id'],
            event_callback=lambda event:update(**event),progress=lambda message:update(message=message))
        if result['status']=='completed':
            update('completed','转换和审计已完成，可以下载成品。',status='completed')
        else:
            report=read_json(path/'run/conversion/review.json',{})
            audit=read_json(path/'run/conversion/audit.json',{})
            errors=[i.get('message') for i in report.get('issues',[]) if i.get('kind')=='execution_error']
            reason=(errors or [audit.get('error_message') or '请查阅诊断报告。'])[0]
            update(message=f"任务未完整完成（{result['status']}）：{reason}",status='failed')
    except Exception as exc:
        hints={401:'DataProxy授权无效或已失效，请核对后端项目Key。',403:'DataProxy拒绝访问，请检查项目授权及知识库绑定。',
               413:'文件大小或服务端存储配额超限。',429:'DataProxy并发请求超限，请稍后再试。',410:'远端资料已过期。'}
        receipt=read_json(path/'run/integration.json',{})
        reason=hints.get(getattr(exc,'status',None),f'{type(exc).__name__}：{safe_message(exc,values)}')
        if receipt.get('parse_quality') == 'degraded' and not request['settings'].get('allow_degraded',False):
            reason='DataProxy解析已完成，但质量为降级；当前设置不允许使用降级资料，已停止转换。请先核对解析警告。'
        if receipt.get('failure_reason'):reason+='；DataProxy原因：'+str(receipt['failure_reason'])
        update(message=reason,status='failed')


def make_server(app,port=8765):
    static=Path(__file__).parent/'web_static'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def send(self,status,data,content_type='application/json; charset=utf-8',headers=None):
            if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            for k,v in (headers or {}).items():self.send_header(k,v)
            self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass

        def permitted(self):
            port=self.server.server_port
            return self.headers.get('Host') in {f'127.0.0.1:{port}',f'localhost:{port}'}

        def send_file(self,file,content_type,headers):
            with file.open('rb') as stream:
                self.send_response(200)
                self.send_header('Content-Type',content_type)
                self.send_header('Content-Length',str(file.stat().st_size))
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Cache-Control','no-store')
                self.send_header('Referrer-Policy','no-referrer')
                for key,value in headers.items():self.send_header(key,value)
                self.end_headers()
                try:shutil.copyfileobj(stream,self.wfile,256*1024)
                except (BrokenPipeError,ConnectionResetError):pass

        def do_GET(self):
            if not self.permitted():return self.send(403,{'error':'仅允许本机访问。'})
            route=urlsplit(self.path).path
            try:
                if route in {'/','/app.js','/style.css'}:
                    name='index.html' if route=='/' else route[1:]
                    content_type={'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[name]
                    return self.send(200,(static/name).read_bytes(),content_type,{'Content-Security-Policy':"default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
                if route=='/api/config':return self.send(200,app.configuration())
                if route=='/api/jobs':
                    ids=[p.parent.name for p in sorted(app.root.glob('*/web-job.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30]]
                    return self.send(200,{'jobs':[app.status(i) for i in ids]})
                match=re.fullmatch(r'/api/jobs/([0-9a-f]{32})(?:/files/([a-z.-]+))?',route)
                if not match:raise FileNotFoundError
                job_id,name=match.groups()
                if not name:return self.send(200,app.status(job_id))
                if name not in FILES:raise FileNotFoundError
                root=app.job_dir(job_id)/'run';file=root/FILES[name]
                if not file.resolve().is_relative_to(root.resolve()) or not file.is_file():raise FileNotFoundError
                headers={'Content-Disposition':f"attachment; filename*=UTF-8''{quote(name)}"}
                if name=='audit.html':
                    headers={'Content-Security-Policy':"sandbox allow-scripts allow-downloads; default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"}
                return self.send_file(file,mimetypes.guess_type(name)[0] or 'application/octet-stream',headers)
            except (FileNotFoundError,KeyError):return self.send(404,{'error':'文件或任务不存在。'})

        def do_POST(self):
            origin=self.headers.get('Origin')
            if not self.permitted() or (origin and origin!='http://'+self.headers.get('Host','')) or not secrets.compare_digest(self.headers.get('X-DocTransAI-Token',''),app.token):
                return self.send(403,{'error':'请求校验失败，请刷新本地页面。'})
            if urlsplit(self.path).path!='/api/jobs':return self.send(404,{'error':'接口不存在。'})
            if not app.upload_gate.acquire(blocking=False):return self.send(409,{'error':'已有上传正在处理，请稍后重试。'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=MAX_REQUEST:return self.send(413,{'error':'上传大小超限或内容为空。'})
                self.connection.settimeout(60)
                body=self.rfile.read(length)
                if len(body)!=length:raise ValueError('上传中断，请重新选择文件。')
                parts=upload_parts(body,self.headers.get('Content-Type',''))
                return self.send(202,app.submit(parts))
            except (ValueError,UnicodeError,OSError) as exc:
                try:values=env_values(app.env_file)
                except OSError:values={}
                return self.send(400,{'error':safe_message(exc,values)})
            except RuntimeError as exc:return self.send(409,{'error':str(exc)})
            finally:app.upload_gate.release()
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main(argv=None):
    p=argparse.ArgumentParser(description='DocTransAI本地测试页面，仅监听127.0.0.1。')
    p.add_argument('--env-file',type=Path)
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--runs-dir',type=Path,default=Path('outputs/web'))
    p.add_argument('--worker',type=Path,help=argparse.SUPPRESS)
    a=p.parse_args(argv)
    if a.worker:
        run_worker(a.worker,a.env_file);return 0
    app=LocalApp(a.runs_dir,a.env_file)
    server=make_server(app,a.port)
    print(f'DocTransAI测试页：http://127.0.0.1:{server.server_port}',flush=True)
    print('仅源文档发送给DataProxy；模板和密钥保留在本地后端。按Ctrl+C停止。',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close();app.close()
    return 0


if __name__=='__main__':
    main()
