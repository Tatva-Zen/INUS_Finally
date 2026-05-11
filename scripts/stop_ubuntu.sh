#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/.finally.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "FinAlly is not running (no PID file found)."
    exit 0
fi

PID=$(cat "$PID_FILE")

if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping FinAlly (PID $PID)..."
    kill "$PID"
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID"
    fi
    echo "FinAlly stopped. Database preserved at $PROJECT_DIR/db/finally.db"
else
    echo "FinAlly process (PID $PID) was not running."
fi

rm -f "$PID_FILE"
