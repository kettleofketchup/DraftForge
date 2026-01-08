#!/bin/bash
# Stop persistent Chrome browser
# Usage: ./stop-chrome.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=9222

# Check if Chrome is running
if ! curl -s "http://127.0.0.1:$PORT/json/version" > /dev/null 2>&1; then
    echo "Chrome is not running on port $PORT"
    exit 0
fi

echo "Stopping persistent Chrome browser..."

# Try graceful shutdown first
cd "$SCRIPT_DIR"
if [[ -f "close-persistent.js" ]]; then
    node close-persistent.js 2>/dev/null
fi

# Wait a moment then verify
sleep 1

if curl -s "http://127.0.0.1:$PORT/json/version" > /dev/null 2>&1; then
    # Force kill if still running
    pkill -f "remote-debugging-port=$PORT" 2>/dev/null
    sleep 1
fi

if curl -s "http://127.0.0.1:$PORT/json/version" > /dev/null 2>&1; then
    echo "WARNING: Chrome may still be running"
    exit 1
else
    echo "Chrome stopped successfully"
    # Clean up endpoint file
    rm -f "$SCRIPT_DIR/.browser-endpoint" 2>/dev/null
    exit 0
fi
