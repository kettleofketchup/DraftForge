#!/usr/bin/env bash
# Install Grafana Alloy from the official APT repository.
# Run as: sudo bash 01-install.sh
set -euo pipefail

echo "==> Adding Grafana APT repository..."
mkdir -p /etc/apt/keyrings/
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | tee /etc/apt/keyrings/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | tee /etc/apt/sources.list.d/grafana.list

echo "==> Installing alloy..."
apt-get update -qq
apt-get install -y alloy

echo "==> Alloy installed:"
alloy --version
echo "Done. Run 02-configure.sh next."
