#!/usr/bin/env bash
# Simple helper to start the worker on an office Ubuntu machine
# Usage: sudo ./scripts/start_worker_office.sh  (expects /root/.env or use --env-file)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT/backend"

# Prefer /root/.env if present, otherwise look for backend/.env.office
ENV_FILE="/root/.env"
if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$REPO_ROOT/backend/.env.office" ]; then
    ENV_FILE="$REPO_ROOT/backend/.env.office"
  else
    echo "Warning: no /root/.env and no backend/.env.office found. Proceeding without --env-file." >&2
    ENV_FILE=""
  fi
fi

# Activate venv if present
if [ -f "$REPO_ROOT/.venv/bin/activate" ]; then
  # shellcheck source=/dev/null
  source "$REPO_ROOT/.venv/bin/activate"
fi

UVICORN_CMD="python -m uvicorn worker_service:app --host 0.0.0.0 --port 8081"
if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
  echo "Starting worker with env file: $ENV_FILE"
  exec $UVICORN_CMD --env-file "$ENV_FILE"
else
  echo "Starting worker without env-file (expect env in environment)"
  exec $UVICORN_CMD
fi
