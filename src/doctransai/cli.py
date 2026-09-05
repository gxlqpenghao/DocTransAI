from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

from doctransai import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="doctransai")
    parser.add_argument("--version", action="store_true", help="Print the DocTransAI version.")
    commands = parser.add_subparsers(dest="command")
    convert_parser = commands.add_parser("convert", help="Convert native DataProxy material to a DOCX or XLSX template with model tools.")
    convert_parser.add_argument("--bundle", type=Path, required=True)
    convert_parser.add_argument("--template", type=Path, required=True)
    convert_parser.add_argument("--output-dir", type=Path, required=True, help="A new, non-existing run directory")
    convert_parser.add_argument("--instruction", required=True)
    convert_parser.add_argument("--source-file", type=Path)
    convert_parser.add_argument("--document-id")
    convert_parser.add_argument("--source-ref", action="append", default=[])
    convert_parser.add_argument("--env-file", type=Path)
    convert_parser.add_argument("--model")
    convert_parser.add_argument("--max-steps", type=int, default=12)
    convert_parser.add_argument("--timeout-seconds", type=float, default=900)
    convert_parser.add_argument("--render-script", type=Path)
    convert_parser.add_argument("--render-python")
    args = parser.parse_args(argv)

    if args.version:
        print(f"doctransai {__version__}")
        return 0
    if args.command == "convert":
        from doctransai.config import RuntimeConfig
        from doctransai.conversion import convert
        from doctransai.types import TaskSpec
        try:
            config = RuntimeConfig.from_environment(env_file=args.env_file, model=args.model,
                    max_steps=args.max_steps, max_seconds=args.timeout_seconds,
                    render_script=args.render_script, render_python=args.render_python)
            task = TaskSpec(args.bundle, args.template, args.output_dir, args.instruction,
                            args.source_file, args.document_id, tuple(args.source_ref))
            result = convert(task, config=config, progress=lambda text: print(text, file=sys.stderr, flush=True))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return 0 if result.execution_status == "completed" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
