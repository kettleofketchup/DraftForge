# Grafana Alloy - Host Metrics Setup

Collects host-level metrics (CPU, memory, disk, network) from the Digital Ocean
droplet and ships them to Grafana Cloud via OTLP.

## Why not from the app container?

System metrics from inside Docker containers are inaccurate and Grafana Cloud
Mimir rejects the temporality/type combos that the Python OTel SDK produces.
Alloy runs on the host and uses node_exporter under the hood.

## Setup

Copy this folder to your server:

```bash
scp -r scripts/alloy/ user@your-server:/tmp/alloy-setup/
```

Then run each step in order on the server:

### Step 1: Install Alloy

```bash
sudo bash /tmp/alloy-setup/01-install.sh
```

### Step 2: Configure

Edit the API key in the script first, then:

```bash
sudo bash /tmp/alloy-setup/02-configure.sh
```

### Step 3: Start the service

```bash
sudo bash /tmp/alloy-setup/03-start.sh
```

### Step 4: Verify

```bash
bash /tmp/alloy-setup/04-verify.sh
```

## Grafana Cloud Dashboards

Once metrics are flowing, you can:

- Import the **Linux Node** integration dashboard in Grafana Cloud
- Query metrics like:
  - `node_cpu_seconds_total` - CPU usage
  - `node_memory_MemAvailable_bytes` - Available memory
  - `node_disk_io_time_seconds_total` - Disk I/O
  - `node_network_receive_bytes_total` - Network traffic
  - `node_filesystem_avail_bytes` - Disk space

## Troubleshooting

```bash
# Check logs
sudo journalctl -u alloy -f

# Test config syntax
alloy fmt /etc/alloy/config.alloy

# Alloy UI (if enabled)
# http://localhost:12345
```
