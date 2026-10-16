#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
trap 'status=$?; if [ "$status" -ne 0 ]; then echo "Setup failed. Read the error above."; fi; read -r -p "Press Enter to close..." _; exit "$status"' EXIT
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if command -v uv >/dev/null 2>&1; then UV_BIN="$(command -v uv)"; else
  UV_BIN="$PWD/runtime/uv/uv"
  if [ ! -x "$UV_BIN" ]; then
    mkdir -p runtime/uv
    curl --fail --location --connect-timeout 15 --max-time 60 https://astral.sh/uv/0.12.19/install.sh -o runtime/uv/install.sh
    UV_UNMANAGED_INSTALL="$PWD/runtime/uv" sh runtime/uv/install.sh
  fi
fi
"$UV_BIN" python install 3.12.13
"$UV_BIN" sync --locked --python 3.12.13
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
.venv/bin/python -m doctransai.doctor --env-file .env --render-check "outputs/setup-check-$(date +%Y%m%d-%H%M%S)"
echo 'Fill .env and inspect the Chinese PNG previews. Then double-click start-macos.command.'
