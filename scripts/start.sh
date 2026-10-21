#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$DIR/.portal.pid"
PORT=${PORT:-8000}
HOST=${HOST:-127.0.0.1}

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Sandbox portal is already running (PID $(cat "$PID_FILE")) on http://$HOST:$PORT"
  exit 0
fi

# Ensure venv if present
if [ -d "$DIR/.venv" ]; then
  source "$DIR/.venv/bin/activate"
fi

echo "Starting Driftless-Playwright sandbox portal on http://$HOST:$PORT..."
nohup python -m uvicorn sandbox_portal.server:app --host "$HOST" --port "$PORT" > "$DIR/.portal.log" 2>&1 &
echo $! > "$PID_FILE"

echo "Started successfully (PID $(cat "$PID_FILE"))."
echo "  - Bank Portal:          http://$HOST:$PORT/bank"
echo "  - Merchant Login:       http://$HOST:$PORT/merchant/login"
echo "  - Merchant Billing:     http://$HOST:$PORT/billing"
echo "  - Telemetry Dashboard:  http://$HOST:$PORT/dashboard"
echo "  - Health Check:         http://$HOST:$PORT/health"
echo "Logs: $DIR/.portal.log"
