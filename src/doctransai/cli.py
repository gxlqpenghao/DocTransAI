from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
import sys

from doctransai import __version__
from doctransai.settings import add_model_arguments, model_overrides, env_values, setting


def main(argv: list[str] | None = None) -> int:
    actual = sys.argv[1:] if argv is None else argv
    if actual and actual[0] == 'audit':
        from doctransai.audit import main as audit_main
        return audit_main(actual[1:])
    if actual and actual[0] == 'remote':
        from doctransai.upstream.dataproxy.command import main as remote_main
        return remote_main(actual[1:])
    parser = argparse.ArgumentParser(prog="doctransai")
    parser.add_argument("--version", action="store_true", help="Print the DocTransAI version.")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser('remote', help='Convert through DataProxy ZIP or workspace APIs (remote --help)')
    commands.add_parser('audit', help='Assess template positions in an existing conversion (audit --help)')
    parse_parser = commands.add_parser("parse", help="Upload a source to the DataProxy service and validate its package")
    parse_parser.add_argument("--source-file", type=Path, required=True)
    parse_parser.add_argument("--output-dir", type=Path, required=True)
    parse_parser.add_argument("--base-url", default=os.environ.get("DOCTRANSAI_DATAPROXY_BASE_URL"))
    parse_parser.add_argument("--idempotency-key")
    parse_parser.add_argument('--env-file', type=Path)
    parse_parser.add_argument("--timeout-seconds", type=float, default=900)
    for command in ("convert", "review"):
        convert_parser = commands.add_parser(command, help="Convert materials or independently review an existing output.")
        if command == "review":
            convert_parser.add_argument("--document", type=Path, required=True, help="Existing output; original template is still required")
        else:
            convert_parser.add_argument("--review", action="store_true", help="Run the explicit independent review and bounded repair phase")
            convert_parser.add_argument("--skip-review", action="store_true", help="Explicit baseline comparison only; result is not independently reviewed")
        convert_parser.add_argument("--bundle", type=Path, required=True)
        convert_parser.add_argument("--template", type=Path, required=True)
        convert_parser.add_argument("--output-dir", type=Path, required=True, help="New run directory")
        convert_parser.add_argument("--instruction", required=True)
        convert_parser.add_argument("--source-file", type=Path)
        convert_parser.add_argument("--document-id")
        convert_parser.add_argument("--source-ref", action="append", default=[])
        convert_parser.add_argument("--env-file", type=Path)
        add_model_arguments(convert_parser)
        convert_parser.add_argument("--max-steps", type=int, default=12)
        convert_parser.add_argument("--review-max-steps", type=int, default=6)
        convert_parser.add_argument("--repair-max-steps", type=int, default=4)
        convert_parser.add_argument("--max-repair-rounds", type=int, default=1)
        convert_parser.add_argument("--timeout-seconds", type=float, default=900, help="Total shared budget across all phases")
        convert_parser.add_argument("--render-script", type=Path)
        convert_parser.add_argument("--render-python")
    args = parser.parse_args(argv)

    if args.version:
        print(f"doctransai {__version__}")
        return 0
    if args.command == "parse":
        from doctransai.upstream.dataproxy.client import fetch_parse_artifact
        try:
            values = env_values(args.env_file)
            args.base_url = args.base_url or setting('DOCTRANSAI_DATAPROXY_BASE_URL', values)
            if not args.base_url:
                raise ValueError("Set --base-url or DOCTRANSAI_DATAPROXY_BASE_URL")
            manifest = fetch_parse_artifact(args.source_file, args.output_dir, base_url=args.base_url,
                api_key=setting('DOCTRANSAI_DATAPROXY_API_KEY', values, ''),
                idempotency_key=args.idempotency_key, timeout=args.timeout_seconds)
            print(json.dumps({"manifest": str(manifest)}, ensure_ascii=False))
            return 0
        except Exception as exc:
            secret = os.environ.get("DOCTRANSAI_DATAPROXY_API_KEY", "")
            message = str(exc).replace(secret, "<redacted>") if secret else str(exc)
            print(message, file=sys.stderr)
            return 1
    if args.command in ("convert", "review"):
        from doctransai.config import RuntimeConfig
        from doctransai.conversion import convert
        from doctransai.types import TaskSpec
        try:
            explicit_review = args.command == "review" or bool(getattr(args, "review", False))
            if explicit_review and getattr(args, "skip_review", False):
                raise ValueError("--review and --skip-review cannot be used together")
            config = RuntimeConfig.from_environment(env_file=args.env_file, **model_overrides(args),
                    review_enabled=explicit_review, review_max_steps=args.review_max_steps,
                    repair_max_steps=args.repair_max_steps, max_repair_rounds=args.max_repair_rounds,
                    max_steps=args.max_steps, max_seconds=args.timeout_seconds,
                    render_script=args.render_script, render_python=args.render_python)
            task = TaskSpec(args.bundle, args.template, args.output_dir, args.instruction,
                            args.source_file, args.document_id, tuple(args.source_ref))
            result = convert(task, config=config, existing_document=getattr(args,"document",None), progress=lambda text: print(text, file=sys.stderr, flush=True))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        if result.execution_status != "completed": return 1
        return 3 if config.review_enabled and result.review_status != "model_passed" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
