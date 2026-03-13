#!/usr/bin/env bash
set -euo pipefail

INTERVAL=${FORGE_POLL_INTERVAL:-300}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

while true; do
    python3 "$SCRIPT_DIR/forge.py" || true
    sleep "$INTERVAL"
done
