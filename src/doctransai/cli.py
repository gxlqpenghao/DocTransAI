from __future__ import annotations

import argparse

from doctransai import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="doctransai")
    parser.add_argument("--version", action="store_true", help="Print the DocTransAI version.")
    args = parser.parse_args(argv)

    if args.version:
        print(f"doctransai {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
