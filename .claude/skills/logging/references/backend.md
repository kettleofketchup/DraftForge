# Backend Logging Reference

## Architecture

```
structlog (app code)
  → ProcessorFormatter (shared pipeline)
    → StreamHandler (stdout — JSON in prod, colored in dev)
    → OTel LoggingHandler (ships to Grafana Cloud via OTLP)
```

Configured in `backend/telemetry/logging.py`. Initialized by `backend/telemetry/config.py:init_telemetry()`.

## Logger Setup

Always use structlog via `get_logger`, never stdlib `logging.getLogger`:

```python
from telemetry.logging import get_logger
log = get_logger(__name__)
```

This returns a `structlog.stdlib.BoundLogger` that supports kwargs natively.

## Event Naming

Event names (first arg) are snake_case verbs describing what happened:

```python
# Good — descriptive, filterable
log.info("heartbeat_stale", system="herodraft", subsystem="heartbeat", ...)
log.info("tick_loop_started", system="herodraft", subsystem="timer", ...)
log.warning("captain_disconnect_paused", system="herodraft", subsystem="connection", ...)

# Bad — f-strings, vague names, no taxonomy
log.info(f"Draft {draft_id} paused")
log.info("something happened")
```

## Anti-Patterns

| Don't | Do Instead |
|-------|-----------|
| `log.info(f"User {uid} joined")` | `log.info("user_joined", user_id=uid)` |
| `log.error(str(e))` | `log.error("task_failed", error=str(e), task_id=tid)` |
| `logging.getLogger(__name__)` | `from telemetry.logging import get_logger` |
| `log.info("doing thing", extra={...})` | `log.info("doing_thing", key=value)` |
| Missing system/subsystem | Always include both |

## OTel Trace Correlation

Structlog automatically injects `trace_id` and `span_id` from the active OTel span (via `_add_otel_trace_context` processor). No manual work needed — logs produced during an instrumented request or task automatically correlate with traces.

## Celery Worker Logging

Celery workers fork from the main process. `config/celery.py:init_worker_telemetry` resets both `_tracing_initialized` and `_log_export_initialized` then calls `init_telemetry()` to get fresh providers.

The `TelemetryTask` base class (`telemetry/celery.py`) auto-binds `task.id`, `task.name`, `request.id`, and `user.id` to structlog contextvars for every task execution.

```python
@app.task(base=TelemetryTask)
def my_task(arg):
    log.info("processing", system="myfeature", subsystem="worker")
    # task.id, task.name, request.id already in context
```

## WebSocket Logging

`TelemetryConsumerMixin` (`telemetry/websocket.py`) binds `ws_conn_id` and path labels on connect. Use `system`/`subsystem` in all consumer log calls:

```python
log.info("herodraft_connected", system="herodraft", subsystem="connection",
         draft_id=self.draft_id, user_id=self.user.id)
```

## Django Middleware

`TelemetryMiddleware` (`telemetry/middleware.py`) binds `request.id`, `user.id`, and URL labels to structlog contextvars for every HTTP request. Logs `request_completed` with `duration_ms`.

`QueryStatsMiddleware` (`telemetry/db.py`) logs `db_query_stats` per request and `slow_query` for queries above threshold.

## Environment Variables

| Variable | Default | Effect |
|----------|---------|--------|
| `LOG_LEVEL` | `INFO` | Root logger level |
| `LOG_FORMAT` | `pretty` (dev) / `json` (prod) | Output format |
| `TELEMETRY_ENABLED` | `true` | Master switch for all telemetry |
| `OTEL_ENABLED` | `false` | Enable OTLP export (tracing + logs) |

## Service Names (OTEL_SERVICE_NAME)

Set per-service in docker-compose `environment`:

| Service | Name |
|---------|------|
| Django/Daphne | `backend` |
| Celery worker | `celery-worker` |
| Celery beat | `celery-beat` |
| Discord bot | `discord` |
