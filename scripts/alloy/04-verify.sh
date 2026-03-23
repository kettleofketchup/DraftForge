#!/usr/bin/env bash
# Verify Alloy is running and exporting metrics.
# Run as: bash 04-verify.sh
set -euo pipefail

echo "==> Service status:"
systemctl is-active alloy && echo "  alloy is running" || echo "  ERROR: alloy is not running"

echo ""
echo "==> Recent logs (last 20 lines):"
journalctl -u alloy --no-pager -n 20

echo ""
echo "==> Checking for export errors..."
if journalctl -u alloy --no-pager -n 100 | grep -qi "error"; then
    echo "  WARNING: Found errors in recent logs. Check with:"
    echo "    sudo journalctl -u alloy -f"
else
    echo "  No errors found in recent logs."
fi

echo ""
echo "==> Alloy should now be shipping metrics to Grafana Cloud."
echo "    Check your Grafana Cloud dashboards for node_* metrics."
echo "    Alloy UI available at http://localhost:12345 (if accessible)."
