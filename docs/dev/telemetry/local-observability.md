# Local Observability

This guide covers running observability tools locally for development.

## Production: Grafana Cloud Tempo

In production, traces are sent to **Grafana Cloud Tempo** via OTLP. No local infrastructure is needed for production tracing -- it is enabled by default in `docker/.env.prod`.

## Local Tracing Options

For local development, you can point the OTLP exporter at any compatible collector.

### Option 1: Grafana Cloud (Recommended)

Use the same Grafana Cloud instance as production:

```bash
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-<region>.grafana.net/otlp
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64-encoded>"
export OTEL_SERVICE_NAME=dtx-backend-dev
export OTEL_TRACES_SAMPLER_ARG=1.0  # 100% sampling for local dev
```

### Option 2: Local Grafana + Tempo

Run a local Grafana stack with Tempo for trace storage:

```bash
docker run -d --name tempo \
  -p 4317:4317 \
  -p 3200:3200 \
  grafana/tempo:latest \
  -config.file=/etc/tempo.yaml

docker run -d --name grafana \
  -p 3001:3000 \
  grafana/grafana:latest
```

Then configure Django:

```bash
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=dtx-backend-dev
export OTEL_TRACES_SAMPLER_ARG=1.0
```

View traces in Grafana at http://localhost:3001 (add Tempo as a data source).

### Option 3: Any OTLP-Compatible Collector

OpenTelemetry supports many backends. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to any OTLP-compatible collector:

| Backend | Endpoint Format |
|---------|-----------------|
| Grafana Cloud Tempo | `https://otlp-gateway-<region>.grafana.net/otlp` |
| Grafana Tempo (self-hosted) | `http://tempo:4317` |
| Honeycomb | `https://api.honeycomb.io` |
| Datadog | `http://datadog-agent:4317` |

## Configure Django

Set environment variables to enable tracing:

```bash
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=dtx-backend
export OTEL_TRACES_SAMPLER_ARG=1.0  # 100% sampling for local dev
```

Or add to your `.env` file:

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=dtx-backend
OTEL_TRACES_SAMPLER_ARG=1.0
```

### Start Django

```bash
cd backend
python manage.py runserver
```

## Viewing Structured Logs

### Pretty Console Output

In development, logs are automatically formatted for readability:

```bash
# Ensure you're in dev mode
export NODE_ENV=dev
export LOG_FORMAT=pretty  # optional, auto-detected from NODE_ENV

python manage.py runserver
```

Output:

```
2024-01-15 10:23:45 [info     ] request_completed [telemetry.middleware] ...
```

### JSON Output (for jq processing)

```bash
export LOG_FORMAT=json

python manage.py runserver 2>&1 | jq .
```

### Filtering Logs with jq

```bash
# Only show errors
python manage.py runserver 2>&1 | jq 'select(.level == "error")'

# Only show specific events
python manage.py runserver 2>&1 | jq 'select(.event == "request_completed")'

# Only show slow requests (>100ms)
python manage.py runserver 2>&1 | jq 'select(.duration_ms > 100)'

# Show specific fields
python manage.py runserver 2>&1 | jq '{event, duration_ms, "http.route"}'
```

## Troubleshooting

### No Traces Appearing

1. **Check OTEL_ENABLED**
   ```bash
   echo $OTEL_ENABLED  # Should be "true"
   ```

2. **Check endpoint connectivity**
   ```bash
   curl -v http://localhost:4317
   # Should connect (may return error page, but connection works)
   ```

3. **Verify Django initialization**
   Look for this log at startup:
   ```
   telemetry_initialized otel_enabled=True
   ```

4. **Check sample rate**
   ```bash
   echo $OTEL_TRACES_SAMPLER_ARG  # Should be > 0
   ```
