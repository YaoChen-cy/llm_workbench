#!/usr/bin/env bash
# Build the frontend if needed, then serve everything at http://localhost:8000
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --only-binary=pymupdf -r requirements.txt
fi
if [ ! -d frontend/dist ] || [ -n "$(find frontend/src -newer frontend/dist -print -quit)" ]; then
  (cd frontend && { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build)
fi
[ -f .env ] && set -a && . ./.env && set +a
echo "Open http://localhost:8000"
exec .venv/bin/uvicorn backend.app:app --port "${PORT:-8000}"
