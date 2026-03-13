#!/usr/bin/env bash
set -euo pipefail

INTERVAL=${FORGE_POLL_INTERVAL:-300}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FORGE_ROOT="$(dirname "$SCRIPT_DIR")"

while true; do
    cd "$FORGE_ROOT" && python3 -m forge || true
    sleep "$INTERVAL"
done
