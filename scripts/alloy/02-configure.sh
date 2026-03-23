#!/usr/bin/env bash
# Configure Grafana Alloy for host metrics → Grafana Cloud.
# Run as: sudo bash 02-configure.sh
#
# BEFORE RUNNING: Set your Grafana Cloud API token below.
set -euo pipefail

# ============================================================
# EDIT THIS: Your Grafana Cloud API token (the decoded base64
# value from your OTEL_EXPORTER_OTLP_HEADERS Authorization).
# ============================================================
GRAFANA_CLOUD_API_KEY="CHANGE_ME"

if [ "$GRAFANA_CLOUD_API_KEY" = "CHANGE_ME" ]; then
    echo "ERROR: Edit this script and set GRAFANA_CLOUD_API_KEY first."
    exit 1
fi

echo "==> Writing Alloy config to /etc/alloy/config.alloy..."
cat > /etc/alloy/config.alloy << 'ALLOY_CONFIG'
// ============================================================
// Grafana Alloy — Host Metrics for Digital Ocean Droplet
// ============================================================

// Collect host metrics (CPU, memory, disk, network, filesystem)
// Uses node_exporter under the hood.
prometheus.exporter.unix "host" {}

prometheus.scrape "host_metrics" {
  targets         = prometheus.exporter.unix.host.targets
  forward_to      = [otelcol.receiver.prometheus.default.receiver]
  scrape_interval = "60s"
}

// Convert Prometheus metrics to OTLP and export
otelcol.receiver.prometheus "default" {
  output {
    metrics = [otelcol.exporter.otlphttp.grafana_cloud.input]
  }
}

otelcol.exporter.otlphttp "grafana_cloud" {
  client {
    endpoint = "https://otlp-gateway-prod-us-east-3.grafana.net/otlp"
    auth     = otelcol.auth.basic.grafana_cloud.handler
  }
}

otelcol.auth.basic "grafana_cloud" {
  username = "1500365"
  password = env("GRAFANA_CLOUD_API_KEY")
}
ALLOY_CONFIG

echo "==> Setting API key in systemd environment..."
mkdir -p /etc/systemd/system/alloy.service.d
cat > /etc/systemd/system/alloy.service.d/env.conf << EOF
[Service]
Environment="GRAFANA_CLOUD_API_KEY=${GRAFANA_CLOUD_API_KEY}"
EOF

# Restrict permissions on the env file (contains secret)
chmod 600 /etc/systemd/system/alloy.service.d/env.conf

echo "==> Reloading systemd..."
systemctl daemon-reload

echo "Done. Run 03-start.sh next."
