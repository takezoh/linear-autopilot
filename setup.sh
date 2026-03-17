#!/usr/bin/env bash
set -euo pipefail

cd "$(cd "$(dirname "$0")" && pwd)"

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
