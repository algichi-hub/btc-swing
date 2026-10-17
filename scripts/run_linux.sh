#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
app_host="${APP_HOST:-${HOST:-0.0.0.0}}"
app_port="${APP_PORT:-${PORT:-8005}}"
workers="${UVICORN_WORKERS:-1}"

if [ "${workers}" != "1" ]; then
	echo "UVICORN_WORKERS must be 1 to avoid duplicated schedulers." >&2
	exit 1
fi

exec python -m uvicorn app.main:app --host "${app_host}" --port "${app_port}"
