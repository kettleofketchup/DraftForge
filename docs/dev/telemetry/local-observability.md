# Local Observability

This guide covers running observability tools locally for development.

## Running Jaeger

Jaeger is an open-source distributed tracing platform. It provides a UI to visualize traces.

### Quick Start with Docker

```bash
# Start Jaeger all-in-one container
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/jaeger:latest
```

Ports:

| Port | Service |
|------|---------|
| 16686 | Jaeger UI |
| 4317 | OTLP gRPC receiver |

### Configure Django

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

### View Traces

1. Open http://localhost:16686
2. Select "dtx-backend" from the Service dropdown
3. Click "Find Traces"

### Stopping Jaeger

```bash
docker stop jaeger
docker rm jaeger
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

## Docker Compose Integration

Add Jaeger to your Docker Compose for integrated development:

```yaml
# docker-compose.debug.yaml
services:
  jaeger:
    image: jaegertracing/jaeger:latest
    ports:
      - "16686:16686"
      - "4317:4317"
    networks:
      - dev-network

  backend:
    environment:
      - OTEL_ENABLED=true
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
      - OTEL_SERVICE_NAME=dtx-backend
      - OTEL_TRACES_SAMPLER_ARG=1.0
    depends_on:
      - jaeger
```

## Troubleshooting

### No Traces in Jaeger

1. **Check OTEL_ENABLED**
   ```bash
   echo $OTEL_ENABLED  # Should be "true"
   ```

2. **Check endpoint connectivity**
   ```bash
   curl -v http://localhost:4317
   # Should connect (may return error page, but connection works)
   ```

3. **Check Jaeger logs**
   ```bash
   docker logs jaeger
   ```

4. **Verify Django initialization**
   Look for this log at startup:
   ```
   telemetry_initialized otel_enabled=True
   ```

### Jaeger Container Won't Start

```bash
# Check if port is in use
lsof -i :16686
lsof -i :4317

# Remove existing container
docker rm -f jaeger

# Start fresh
docker run -d --name jaeger ...
```

### High Memory Usage

Jaeger stores traces in memory by default. For extended sessions:

```bash
# Restart Jaeger to clear traces
docker restart jaeger
```

Or use Jaeger with persistent storage (advanced):

```bash
docker run -d --name jaeger \
  -e SPAN_STORAGE_TYPE=badger \
  -e BADGER_EPHEMERAL=false \
  -e BADGER_DIRECTORY_VALUE=/badger/data \
  -e BADGER_DIRECTORY_KEY=/badger/key \
  -v jaeger_data:/badger \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/jaeger:latest
```

## Alternative: Grafana Stack

For a more complete observability setup:

```yaml
# docker-compose.observability.yaml
services:
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    volumes:
      - grafana_data:/var/lib/grafana

  tempo:
    image: grafana/tempo:latest
    ports:
      - "4317:4317"
    command: ["-config.file=/etc/tempo.yaml"]
    volumes:
      - ./tempo.yaml:/etc/tempo.yaml

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"

volumes:
  grafana_data:
```

This provides:

- **Grafana**: Dashboard and visualization
- **Tempo**: Trace storage (Jaeger alternative)
- **Loki**: Log aggregation

Configure Django to send traces to Tempo at `http://tempo:4317`.
