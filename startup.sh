#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -d "antenv" ]; then
  source antenv/bin/activate
elif [ -d "/home/site/wwwroot/antenv" ]; then
  source /home/site/wwwroot/antenv/bin/activate
elif [ -d "/opt/venv" ]; then
  source /opt/venv/bin/activate
fi

export PYTHONUNBUFFERED=1
export PORT="${PORT:-8000}"
export WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
export GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-180}"

exec python -m gunicorn backend.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "$WEB_CONCURRENCY" \
  --bind "0.0.0.0:${PORT}" \
  --timeout "$GUNICORN_TIMEOUT" \
  --access-logfile - \
  --error-logfile -
