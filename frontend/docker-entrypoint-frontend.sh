#!/bin/sh
set -e

# Only clean cache if VITE_FORCE_OPTIMIZE is set (for fresh starts)
if [ "$VITE_FORCE_OPTIMIZE" = "true" ]; then
    echo "Force optimize requested - cleaning Vite cache..."
    rm -rf node_modules/.vite node_modules/.cache .react-router
fi

echo "Starting dev server..."
# Vite 7+ handles dependency optimization automatically
exec npx react-router dev --port 3000 --host 0.0.0.0
