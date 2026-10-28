#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo 'Instale primeiro: python -m venv .venv && .venv/bin/pip install -r requirements.lock' >&2
  exit 1
fi
exec .venv/bin/uvicorn app:app --host 127.0.0.1 --port "${MONITOR_PORT:-8000}"
