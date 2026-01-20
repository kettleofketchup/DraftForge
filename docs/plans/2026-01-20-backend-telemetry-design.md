# Backend Telemetry Design

**Date:** 2026-01-20
**Status:** Draft
**Scope:** Backend first (frontend telemetry in follow-up)

## Overview

Establish structured logging and optional tracing for the DTX backend with:
- **structlog** for structured logging with OTel semantic conventions
- **OpenTelemetry** for distributed tracing (opt-in, OTLP export)
- **Context propagation** across HTTP requests, WebSockets, and Celery tasks
- **URL-based label extraction** for filtering by resource (tournament, draft, etc.)

## Design Principles

1. **Safe-by-default / Opt-in**: Export disabled unless configured. No crashes if endpoints missing.
2. **Environment-first**: All config via environment variables with sensible defaults.
3. **Consistent context**: Same fields (`request.id`, `user.id`, labels) everywhere.
4. **Structured first**: JSON in prod, pretty console in dev.

---

## Architecture

### Module Structure

```
backend/telemetry/
├── __init__.py
├── config.py         # Central init, env helpers
├── logging.py        # structlog configuration
├── middleware.py     # Django request context binding
├── labels.py         # URL-based label extraction
├── tracing.py        # OpenTelemetry initialization
├── celery.py         # Context-aware base task
└── websocket.py      # Channels consumer mixin
```

### Context Flow

```
Request → Middleware → Extract labels from URL → Bind to structlog context
                    → Generate/accept request_id
                    → Extract user.id if authenticated
                    → Start OTel span (if enabled)
```

### Output Modes

| Environment | Format | Level |
|-------------|--------|-------|
| Dev | Pretty console | DEBUG |
| Test | JSON | INFO |
| Prod | JSON | ERROR |

---

## Component Designs

### 1. Label Extraction (`labels.py`)

Parses URL paths to produce contextual metadata.

**Examples:**
```python
extract_labels("/api/tournaments/5/")
# → {"labels": ["tournament"], "tournament.id": 5}

extract_labels("/api/tournaments/5/draft/12/")
# → {"labels": ["tournament", "draft"], "tournament.id": 5, "draft.id": 12}

extract_labels("/api/leagues/3/standings/")
# → {"labels": ["league", "standings"], "league.id": 3}
```

**Supported Patterns:**
| Pattern | Labels | IDs Extracted |
|---------|--------|---------------|
| `/api/tournaments/{id}/...` | `["tournament", ...]` | `tournament.id` |
| `/api/drafts/{id}/...` | `["draft", ...]` | `draft.id` |
| `/api/leagues/{id}/...` | `["league", ...]` | `league.id` |
| `/api/organizations/{id}/...` | `["organization", ...]` | `organization.id` |
| `/api/matches/{id}/...` | `["match", ...]` | `match.id` |
| `/api/users/...` | `["user"]` | — |

### 2. Request Middleware (`middleware.py`)

Binds context to every HTTP request.

**Responsibilities:**
1. Generate or accept `request.id` (from `X-Request-ID` header or new UUID)
2. Extract `user.id` from authenticated session
3. Call label extractor for URL-based context
4. Bind all context to structlog for request duration
5. Start OTel span (if tracing enabled)
6. Add `X-Request-ID` to response headers
7. Log request completion with duration

**Pseudocode:**
```python
class TelemetryMiddleware:
    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        user_id = request.user.pk if request.user.is_authenticated else None
        labels = extract_labels(request.path)

        structlog.contextvars.bind_contextvars(
            request.id=request_id,
            user.id=user_id,
            **labels
        )

        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        structlog.contextvars.clear_contextvars()

        return response
```

### 3. Logging Configuration (`logging.py`)

structlog setup integrated with Django logging.

**Dev Output (pretty):**
```
2026-01-20 14:32:15 [info] request_completed
    http.method=GET http.route=/api/tournaments/5/
    http.status_code=200 duration_ms=45.2
    request.id=abc-123 user.id=42
    labels=['tournament'] tournament.id=5
```

**Prod Output (JSON):**
```json
{"timestamp":"2026-01-20T14:32:15Z","level":"info","event":"request_completed","http.method":"GET","http.route":"/api/tournaments/5/","http.status_code":200,"duration_ms":45.2,"request.id":"abc-123","user.id":42,"labels":["tournament"],"tournament.id":5}
```

### 4. OpenTelemetry Tracing (`tracing.py`)

Optional tracing with OTLP export.

**Instrumentation:**
- Django request lifecycle
- Outbound HTTP requests (Steam API calls)
- System metrics (CPU, memory utilization)

**Initialization:**
- Check `OTEL_ENABLED` flag
- Check for OTLP endpoint
- If missing, log once and no-op
- If present, configure tracer and exporters

**System Metrics:**
- `system.cpu.utilization`
- `system.memory.utilization`
- `process.runtime.cpu.utilization`
- `process.runtime.memory`

### 5. WebSocket Telemetry (`websocket.py`)

Mixin for Django Channels consumers.

**Features:**
- Generate `ws.conn_id` on connect
- Extract labels from WebSocket path
- Bind context for all logs during connection
- Log connect/disconnect events
- Optional spans for message handling

**Usage:**
```python
class DraftConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
    ...
```

### 6. Celery Telemetry (`celery.py`)

Base task class with context binding.

**Features:**
- Bind `task.id`, `task.name` automatically
- Accept propagated `request.id`, `user.id` via kwargs
- Log task start/complete/fail
- Clear context on completion

**Usage:**
```python
@app.task(base=TelemetryTask)
def process_match_stats(match_id: int):
    log.info("processing_match", match.id=match_id)
```

### 7. Central Configuration (`config.py`)

Single initialization entry point.

```python
def init_telemetry():
    if not env_bool("TELEMETRY_ENABLED", True):
        log.info("telemetry_disabled")
        return

    configure_logging(...)
    init_tracing()

    log.info("telemetry_initialized", ...)
```

---

## Environment Variables

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEMETRY_ENABLED` | `true` | Master switch |
| `LOG_LEVEL` | `INFO` | Minimum log level |
| `LOG_FORMAT` | derived | `json` or `pretty` |
| `STRUCTLOG_ENABLED` | `true` | Use structlog |

### OpenTelemetry

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `false` | Enable tracing |
| `OTEL_SERVICE_NAME` | `dtx-backend` | Service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | Grafana/collector URL |
| `OTEL_EXPORTER_OTLP_HEADERS` | — | Auth headers |
| `OTEL_TRACES_SAMPLER_ARG` | `0.1` | Sample rate (10%) |

### Per-Environment Defaults

| Variable | Dev | Test | Prod |
|----------|-----|------|------|
| `LOG_FORMAT` | `pretty` | `json` | `json` |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `ERROR` |
| `OTEL_ENABLED` | `false` | `false` | `false` (opt-in) |

---

## File Changes

### New Files

- `backend/telemetry/__init__.py`
- `backend/telemetry/config.py`
- `backend/telemetry/logging.py`
- `backend/telemetry/middleware.py`
- `backend/telemetry/labels.py`
- `backend/telemetry/tracing.py`
- `backend/telemetry/celery.py`
- `backend/telemetry/websocket.py`
- `docker/docker-compose.observability.yaml`

### Modified Files

- `backend/backend/settings.py` — Add telemetry init and middleware
- `backend/backend/asgi.py` — Add telemetry init
- `backend/.env.example` — Add telemetry variables
- `docker/.env.dev` — Add logging config
- `docker/.env.test` — Add logging config
- `docker/.env.prod` — Add logging config
- `backend/app/consumers.py` — Add TelemetryConsumerMixin

### Documentation

- `docs/dev/telemetry/index.md`
- `docs/dev/telemetry/architecture.md`
- `docs/dev/telemetry/logging.md`
- `docs/dev/telemetry/tracing.md`
- `docs/dev/telemetry/context.md`
- `docs/dev/telemetry/local-observability.md`
- `docs/dev/telemetry/reference.md`

---

## Dependencies

### Python Packages (add to pyproject.toml)

```toml
structlog = "^24.0"
opentelemetry-api = "^1.20"
opentelemetry-sdk = "^1.20"
opentelemetry-exporter-otlp = "^1.20"
opentelemetry-instrumentation-django = "^0.41"
opentelemetry-instrumentation-requests = "^0.41"
opentelemetry-instrumentation-system-metrics = "^0.41"
opentelemetry-instrumentation-celery = "^0.41"
```

---

## Testing Strategy

### Local Verification

1. **Console output**: Pretty logs in dev show all context fields
2. **Local Jaeger**: Optional `docker-compose.observability.yaml` for trace visualization
3. **Unit tests**: Verify label extraction, context binding

### Acceptance Criteria

- [ ] Logs are structured with OTel semantic conventions
- [ ] JSON output in prod, pretty in dev
- [ ] `request.id`, `user.id`, labels present in request logs
- [ ] WebSocket connect/disconnect logged with context
- [ ] Celery tasks logged with context
- [ ] OTel disabled: no crashes, single info log at startup
- [ ] OTel enabled: traces export to configured endpoint
- [ ] System metrics (CPU/mem) collected when OTel enabled

---

## Future Work (Out of Scope)

- Frontend Sentry integration
- Frontend OTel tracing
- Grafana dashboards and alerts
- Log aggregation pipeline
- Session replay
