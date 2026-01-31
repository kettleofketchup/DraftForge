# Tracing Guide

This guide covers OpenTelemetry distributed tracing setup.

## Overview

OpenTelemetry tracing is **opt-in** and disabled by default. When enabled, it provides:

- Distributed trace correlation across services
- Request timing and span visualization
- Automatic Django instrumentation

## Enabling Tracing

Set the following environment variables:

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=dtx-backend  # optional, default: dtx-backend
```

## What Gets Traced

When enabled, OpenTelemetry auto-instruments:

### Django Requests

Every HTTP request creates a span with:

- HTTP method and route
- Response status code
- Request/response timing

### Outbound HTTP Requests

Calls via `requests` library create child spans:

- Target URL
- Response status
- Timing

### System Metrics

Optional system metrics collection:

- CPU usage
- Memory usage
- Process metrics

## Configuration

### Sample Rate

Control what percentage of requests are traced:

```bash
# 10% sampling (default)
OTEL_TRACES_SAMPLER_ARG=0.1

# 100% sampling (development only)
OTEL_TRACES_SAMPLER_ARG=1.0

# 1% sampling (high-traffic production)
OTEL_TRACES_SAMPLER_ARG=0.01
```

### Authentication

For collectors requiring authentication:

```bash
OTEL_EXPORTER_OTLP_HEADERS=api-key=your-api-key,x-custom-header=value
```

## Local Development

See [Local Observability](local-observability.md) for running Jaeger locally.

Quick start:

```bash
# Start Jaeger
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/jaeger:latest

# Enable tracing
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Start Django
python manage.py runserver
```

View traces at http://localhost:16686

## Production Backends

OpenTelemetry supports many backends:

| Backend | Endpoint Format |
|---------|-----------------|
| Jaeger | `http://jaeger:4317` |
| Grafana Tempo | `http://tempo:4317` |
| Honeycomb | `https://api.honeycomb.io` |
| Datadog | `http://datadog-agent:4317` |

## Trace Context Propagation

Traces automatically propagate via HTTP headers:

```
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
```

This means:

- Requests from frontend carry trace context
- Outbound API calls continue the trace
- Celery tasks can receive parent trace context

## Manual Spans

For custom instrumentation:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def complex_operation():
    with tracer.start_as_current_span("complex_operation") as span:
        span.set_attribute("step", "initialization")
        initialize()

        span.set_attribute("step", "processing")
        result = process()

        span.set_attribute("result_count", len(result))
        return result
```

## Troubleshooting

### Traces Not Appearing

1. Verify `OTEL_ENABLED=true` is set
2. Check endpoint is reachable
3. Verify sample rate isn't 0
4. Check collector logs for errors

### Missing Spans

Auto-instrumentation may miss:

- Custom protocols
- Background threads without context propagation
- Code running before instrumentation

### High Overhead

Reduce with lower sample rate:

```bash
OTEL_TRACES_SAMPLER_ARG=0.01  # 1%
```

## Disabling Tracing

To disable without code changes:

```bash
OTEL_ENABLED=false
# or simply don't set the OTEL_ENABLED variable
```

Tracing initialization becomes a no-op, with minimal performance impact.
