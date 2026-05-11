#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

PID_FILE="$PROJECT_DIR/.finally.pid"
LOG_FILE="$PROJECT_DIR/.finally.log"
PORT="${PORT:-8000}"

# ── 1. Check / install uv ────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
fi

# ── 2. Install Python dependencies ───────────────────────────────────────────
echo "Installing Python dependencies..."
cd "$PROJECT_DIR/backend"
uv sync --no-dev

# ── 3. Build frontend if out/ is missing ─────────────────────────────────────
if [ ! -d "$PROJECT_DIR/frontend/out" ]; then
    echo "Building frontend..."
    if ! command -v node &>/dev/null; then
        echo "ERROR: Node.js is required to build the frontend."
        echo "  Install it with: sudo apt install nodejs npm"
        echo "  Or use nvm: https://github.com/nvm-sh/nvm"
        exit 1
    fi
    cd "$PROJECT_DIR/frontend"
    npm install
    npm run build
fi

cd "$PROJECT_DIR"

# ── 4. Stop any existing instance ────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping existing FinAlly instance (PID $OLD_PID)..."
        kill "$OLD_PID"
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

# ── 5. Ensure db/ directory exists ───────────────────────────────────────────
mkdir -p "$PROJECT_DIR/db"

# ── 6. Load .env ─────────────────────────────────────────────────────────────
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
else
    echo "WARNING: .env file not found. Copy .env.example to .env and add your API keys."
fi

# ── 7. Start the backend ──────────────────────────────────────────────────────
echo "Starting FinAlly..."
cd "$PROJECT_DIR/backend"
DB_PATH="$PROJECT_DIR/db/finally.db" \
    uv run uvicorn app.main:app \
        --host 127.0.0.1 \
        --port "$PORT" \
        --log-level warning \
        >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

# ── 8. Wait for server to be ready ───────────────────────────────────────────
echo -n "Waiting for server"
for i in $(seq 1 20); do
    if curl -sf "http://127.0.0.1:$PORT/api/health" &>/dev/null; then
        echo " ready."
        break
    fi
    echo -n "."
    sleep 0.5
    if [ "$i" -eq 20 ]; then
        echo ""
        echo "ERROR: Server did not start in time. Check logs: $LOG_FILE"
        exit 1
    fi
done

echo ""
echo "FinAlly is running at: http://127.0.0.1:$PORT"
echo "  To stop:      ./scripts/stop_ubuntu.sh"
echo "  To view logs: tail -f $LOG_FILE"
echo "  PID:          $(cat "$PID_FILE")"
echo ""

# Open browser if available
if command -v xdg-open &>/dev/null; then
    xdg-open "http://127.0.0.1:$PORT" &>/dev/null &
elif command -v gnome-open &>/dev/null; then
    gnome-open "http://127.0.0.1:$PORT" &>/dev/null &
fi
