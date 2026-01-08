#!/bin/bash
# Start persistent Chrome browser for Chrome DevTools MCP
# Usage: ./start-chrome.sh [--headless]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENDPOINT_FILE="$SCRIPT_DIR/.browser-endpoint"
PORT=9222

# Check if Chrome is already running on the port
if curl -s "http://127.0.0.1:$PORT/json/version" > /dev/null 2>&1; then
    echo "Chrome is already running on port $PORT"
    curl -s "http://127.0.0.1:$PORT/json/version" | head -5
    exit 0
fi

# Parse arguments
HEADLESS_ARG=""
if [[ "$1" == "--headless" ]]; then
    HEADLESS_ARG="--headless=true"
fi

# Launch persistent browser
echo "Starting persistent Chrome browser on port $PORT..."
cd "$SCRIPT_DIR"

if [[ -n "$HEADLESS_ARG" ]]; then
    node launch-persistent.js "$HEADLESS_ARG" &
else
    node launch-persistent.js --headless=false &
fi

# Wait for browser to be ready
for i in {1..30}; do
    if curl -s "http://127.0.0.1:$PORT/json/version" > /dev/null 2>&1; then
        echo ""
        echo "Chrome is ready on port $PORT"
        echo "WebSocket endpoint: $(cat "$ENDPOINT_FILE" 2>/dev/null)"
        echo ""
        echo "Start Claude with: claude"
        echo "Stop Chrome with: $SCRIPT_DIR/stop-chrome.sh"
        exit 0
    fi
    sleep 0.5
    echo -n "."
done

echo ""
echo "ERROR: Chrome failed to start within 15 seconds"
exit 1
