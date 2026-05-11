#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

IMAGE_NAME="finally"
CONTAINER_NAME="finally-app"

# Check for --build flag or if image doesn't exist
SHOULD_BUILD=false
if [[ "$1" == "--build" ]] || ! docker image inspect "$IMAGE_NAME" &>/dev/null 2>&1; then
    SHOULD_BUILD=true
fi

if $SHOULD_BUILD; then
    echo "Building FinAlly Docker image..."
    docker build -t "$IMAGE_NAME" .
fi

# Stop existing container gracefully
if docker ps -q -f name="^${CONTAINER_NAME}$" | grep -q .; then
    echo "Stopping existing container..."
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
elif docker ps -aq -f name="^${CONTAINER_NAME}$" | grep -q .; then
    docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
fi

# Ensure db directory exists
mkdir -p db

echo "Starting FinAlly..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -p 8000:8000 \
    -v "$(pwd)/db:/app/db" \
    --env-file .env \
    --restart unless-stopped \
    "$IMAGE_NAME"

echo ""
echo "FinAlly is starting at: http://localhost:8000"
echo "  To stop:      ./scripts/stop_mac.sh"
echo "  To view logs: docker logs -f $CONTAINER_NAME"
echo "  To rebuild:   ./scripts/start_mac.sh --build"
echo ""

# Optionally open browser on macOS
if command -v open &>/dev/null; then
    echo "Opening browser in 3 seconds..."
    (sleep 3 && open http://localhost:8000) &
fi
