#!/usr/bin/env bash
# Enable and start the Alloy service.
# Run as: sudo bash 03-start.sh
set -euo pipefail

echo "==> Enabling and starting alloy..."
systemctl enable --now alloy

echo "==> Service status:"
systemctl status alloy --no-pager

echo ""
echo "Done. Run 04-verify.sh to confirm metrics are flowing."
