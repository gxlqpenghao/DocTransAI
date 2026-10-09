import argparse
import json
import os
from pathlib import Path

from doctransai.config import RuntimeConfig
from doctransai.settings import add_model_arguments, model_overrides, env_values, setting
from .workflow import run_remote, publish_workspace


def main(argv):
    p = argparse.ArgumentParser(prog='doctransai remote')
    p.add_argument('--base-url', default=os.environ.get('DOCTRANSAI_DATAPROXY_BASE_URL'))
    p.add_argument('--mode', choices=['zip', 'workspace'], default='zip')
    sources = p.add_mutually_exclusive_group()
    sources.add_argument('--source-file', type=Path)
    sources.add_argument('--job-id')
    p.add_argument('--request-id')
    p.add_argument('--run-id')
    p.add_argument('--workspace-id', help='Reuse a known snapshot even after its original parse ZIP expires')
    p.add_argument('--allow-degraded', action='store_true')
    p.add_argument('--template', type=Path)
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--instruction')
    p.add_argument('--publish-receipt', type=Path, help='Retry publication without rerunning the model')
    p.add_argument('--replace-audit', action='store_true', help='Explicitly update only audit files with ETag; result document stays immutable')
    p.add_argument('--env-file', type=Path)
    p.add_argument('--timeout-seconds', type=float, default=1800, help='DataProxy stage budget')
    p.add_argument('--conversion-timeout', type=float, default=900)
    p.add_argument('--max-steps', type=int, default=12)
    p.add_argument('--render-script', type=Path)
    p.add_argument('--render-python')
    add_model_arguments(p)
    a = p.parse_args(argv)
    try:
        values = env_values(a.env_file)
        key = setting('DOCTRANSAI_DATAPROXY_API_KEY', values, '')
        a.base_url = a.base_url or setting('DOCTRANSAI_DATAPROXY_BASE_URL', values)
        if not a.base_url or not key:
            raise ValueError('Configure DOCTRANSAI_DATAPROXY_BASE_URL and DOCTRANSAI_DATAPROXY_API_KEY')
        common = dict(base_url=a.base_url, api_key=key, timeout=a.timeout_seconds)
        if a.publish_receipt:
            result = publish_workspace(receipt_path=a.publish_receipt, replace_audit=a.replace_audit, **common)
        else:
            if not a.template or not a.output_dir or not a.instruction:
                raise ValueError('Template, output directory and instruction are required')
            config = RuntimeConfig.from_environment(env_file=a.env_file, render_script=a.render_script,
                render_python=a.render_python, max_seconds=a.conversion_timeout, max_steps=a.max_steps,
                _default_output_tokens=16000, **model_overrides(a))
            result = run_remote(source=a.source_file, job_id=a.job_id, mode=a.mode,
                request_id=a.request_id, run_id=a.run_id, template=a.template, output_dir=a.output_dir,
                workspace_id=a.workspace_id,
                instruction=a.instruction, config=config, allow_degraded=a.allow_degraded, **common)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'completed' else 1
    except Exception as exc:
        # Exception text from a remote provider must not leak credentials.
        import sys
        status = f' HTTP {exc.status}' if hasattr(exc, 'status') else ''
        print(f'{type(exc).__name__}{status}: remote workflow failed; inspect integration.json and conversion reports', file=sys.stderr)
        return 1
