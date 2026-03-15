#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Activate venv
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate
PYTHON_BIN="$DIR/.venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="$DIR/.venv/bin/python"
fi

# Install httpx if missing
"$PYTHON_BIN" -c "import httpx" 2>/dev/null || "$PYTHON_BIN" -m pip install httpx

# Required env vars
: "${PB_URL:=http://127.0.0.1:8090}"
: "${PB_ADMIN_EMAIL:=admin@admin.com}"
: "${PB_ADMIN_PASSWORD:=1234567890}"

export PB_URL PB_ADMIN_EMAIL PB_ADMIN_PASSWORD

# Optional env vars (with defaults)
export MAX_WORKERS="${MAX_WORKERS:-0}"         # 0 = auto-detect (2-3)
export POLL_INTERVAL="${POLL_INTERVAL:-5}"     # seconds
export LEASE_SECONDS="${LEASE_SECONDS:-600}"   # 10 min lease
export BASE_TMP="${BASE_TMP:-/tmp/video-jobs}"

echo "--- Starting Video Worker ---"
echo "PB_URL=$PB_URL  MAX_WORKERS=$MAX_WORKERS  POLL=$POLL_INTERVAL"
exec "$PYTHON_BIN" pb_worker.py
