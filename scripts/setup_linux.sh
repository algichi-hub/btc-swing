#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
if [[ ! -f .env ]]; then cp .env.example .env; echo "Created .env from .env.example. Edit secrets locally."; fi
echo "Ready. Run: ./scripts/run_linux.sh"
