# Telemetry

DTX uses structured logging and optional distributed tracing for observability.

## Quick Start

### Logging in Your Code

```python
from telemetry.logging import get_logger

log = get_logger(__name__)

def my_function():
    log.info("processing_request", user_id=42, action="create")
```

### What Gets Logged Automatically

- All HTTP requests with timing, status, and context
- WebSocket connections and disconnections
- Celery task lifecycle (start, complete, fail)

## Features

| Feature | Status | Description |
|---------|--------|-------------|
| Structured Logging | Enabled | JSON logs in prod, pretty in dev |
| Request Context | Enabled | request.id, user.id, URL labels |
| WebSocket Context | Enabled | Connection tracking |
| Celery Context | Enabled | Task tracking |
| OpenTelemetry | Opt-in | Distributed tracing |

## Documentation

- [Architecture](architecture.md) - Design decisions and data flow
- [Logging Guide](logging.md) - How to add logging to code
- [Tracing Guide](tracing.md) - OpenTelemetry setup
- [Context Guide](context.md) - Adding context to new endpoints
- [Local Observability](local-observability.md) - Running Jaeger locally
- [Reference](reference.md) - Environment variable reference
