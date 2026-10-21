#!/usr/bin/env bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$DIR/.portal.pid"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping Driftless-Playwright sandbox portal (PID $PID)..."
    kill "$PID" || true
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" || true
    fi
    rm -f "$PID_FILE"
    echo "Sandbox portal stopped."
  else
    echo "Process $PID not running. Cleaning up stale PID file."
    rm -f "$PID_FILE"
  fi
else
  # Fallback: check any running uvicorn process for sandbox_portal
  PIDS="$(pgrep -f "sandbox_portal.server:app" || true)"
  if [ -n "$PIDS" ]; then
    echo "Found sandbox portal process(es): $PIDS. Stopping..."
    kill $PIDS || true
    echo "Stopped."
  else
    echo "No sandbox portal process is currently running."
  fi
fi
