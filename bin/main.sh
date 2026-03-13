#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FORGE_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$FORGE_ROOT/.venv"

if [[ -d "$VENV_DIR" ]]; then
  source "$VENV_DIR/bin/activate"
fi

exec python3 -m forge "$@"
