#!/bin/bash
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if [ ! -x .venv/bin/python ]; then
  echo 'Run setup-macos.command first.'
  read -r -p 'Press Enter to close...' _
  exit 1
fi
.venv/bin/python -m doctransai.desktop --env-file "$PWD/.env" "$@"
status=$?
if [ "$status" -ne 0 ]; then read -r -p 'Press Enter to close...' _; fi
exit "$status"
