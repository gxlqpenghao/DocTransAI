"""Explicit backend dotenv loading without evaluating shell code or mutating os.environ."""
import os
from pathlib import Path


def env_values(path=None):
    path = path or os.environ.get('DOCTRANSAI_ENV_FILE')
    if path is None:
        return {}
    values = {}
    for line in Path(path).expanduser().read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.removeprefix('export ').partition('=')
        if sep:
            values[key.strip()] = value.strip().strip('\"').strip("'")
    return values


def setting(name, values, default=None):
    return os.environ.get(name) or values.get(name) or default


def reasoning_for_model(model, effort=None):
    kimi = model.split('/')[-1] == 'kimi-k3'
    if effort in (None, '', 'auto'):
        return 'high' if kimi else 'omit'
    if kimi and effort not in ('low', 'high', 'max'):
        raise ValueError('Kimi K3 reasoning_effort must be one of: low, high, max')
    if not isinstance(effort, str) or len(effort) > 64 or not all(c.isalnum() or c in '_-' for c in effort):
        raise ValueError('Invalid reasoning_effort')
    return effort


def add_model_arguments(parser):
    parser.add_argument('--model', help='Provider model ID; must support images and function tools')
    parser.add_argument('--reasoning-effort', help='auto, omit, or an effort supported by your provider')
    parser.add_argument('--max-output-tokens', type=int, help='Per-request output budget; environment/config may override defaults')
    parser.add_argument('--temperature', help='Nonnegative number, or omit to exclude this request field')
    parser.add_argument('--llm-timeout-seconds', type=float, help='Maximum wait per network I/O, also bounded by phase budget')
    parser.add_argument('--token-parameter', choices=['max_tokens', 'max_completion_tokens'])


def model_overrides(args):
    return dict(model=args.model, reasoning_effort=args.reasoning_effort,
                max_output_tokens=args.max_output_tokens, temperature=args.temperature,
                llm_timeout_seconds=args.llm_timeout_seconds, token_parameter=args.token_parameter)
