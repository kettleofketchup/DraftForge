# Reference

Environment variable reference for the telemetry system.

## Master Switch

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEMETRY_ENABLED` | `true` | Master switch for all telemetry. Set to `false` to disable completely. |

## Logging Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Minimum log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | auto | Output format: `json` or `pretty`. Auto-detected from `NODE_ENV` if not set. |
| `NODE_ENV` | `dev` | Environment name. `dev`/`development` triggers pretty format. |

### Log Level Details

| Level | Use Case |
|-------|----------|
| `DEBUG` | Verbose debugging, cache hits, internal state |
| `INFO` | Normal operations, request completion, key events |
| `WARNING` | Unexpected but handled situations, approaching limits |
| `ERROR` | Failures requiring attention, unhandled exceptions |

### Format Examples

**JSON** (production):
```json
{"timestamp":"2024-01-15T10:23:45.123456Z","level":"info","event":"request_completed"}
```

**Pretty** (development):
```
2024-01-15 10:23:45 [info     ] request_completed [module.name]
```

## OpenTelemetry Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `OTEL_SERVICE_NAME` | `dtx-backend` | Service name in traces |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (none) | OTLP collector endpoint URL |
| `OTEL_EXPORTER_OTLP_HEADERS` | (none) | Authentication headers |
| `OTEL_TRACES_SAMPLER_ARG` | `0.1` | Sample rate (0.0 to 1.0) |

### Sample Rate Guidelines

| Rate | Use Case |
|------|----------|
| `1.0` | Local development, debugging |
| `0.1` | Low-traffic production |
| `0.01` | High-traffic production |
| `0.0` | Effectively disabled |

### Header Format

Comma-separated key=value pairs:

```bash
OTEL_EXPORTER_OTLP_HEADERS="api-key=abc123,x-org-id=myorg"
```

## Context Fields

Fields automatically added to logs by telemetry components.

### HTTP Request Context (TelemetryMiddleware)

| Field | Type | Description |
|-------|------|-------------|
| `request.id` | string | Unique request ID (from header or generated) |
| `user.id` | int | Authenticated user's primary key |
| `labels` | list | Resource types in URL path |
| `{resource}.id` | int | Resource IDs extracted from URL |
| `http.method` | string | HTTP method (GET, POST, etc.) |
| `http.route` | string | Request URL path |
| `http.status_code` | int | Response status code |
| `duration_ms` | float | Request processing time |

### WebSocket Context (TelemetryConsumerMixin)

| Field | Type | Description |
|-------|------|-------------|
| `ws.conn_id` | string | Unique WebSocket connection ID |
| `user.id` | int | Authenticated user's primary key |
| `labels` | list | Resource types in WebSocket path |
| `{resource}.id` | int | Resource IDs from path |
| `close_code` | int | WebSocket close code (on disconnect) |

### Celery Task Context (TelemetryTask)

| Field | Type | Description |
|-------|------|-------------|
| `task.id` | string | Celery task ID |
| `task.name` | string | Task function name |
| `request.id` | string | Propagated or generated request ID |
| `user.id` | int | Propagated user ID |

## Supported URL Patterns

The label extractor recognizes these URL patterns:

| Pattern | Label | ID Field |
|---------|-------|----------|
| `/api/tournaments/5/` | `tournament` | `tournament.id` |
| `/api/drafts/12/` | `draft` | `draft.id` |
| `/api/leagues/3/` | `league` | `league.id` |
| `/api/organizations/1/` | `organization` | `organization.id` |
| `/api/matches/99/` | `match` | `match.id` |
| `/api/games/7/` | `game` | `game.id` |
| `/api/teams/4/` | `team` | `team.id` |
| `/api/users/42/` | `user` | `user.id` |
| `/ws/draft/5/` | `draft` | `draft.id` |
| `/ws/tournament/3/` | `tournament` | `tournament.id` |

List endpoints (without IDs) produce labels without ID fields:

| Pattern | Label |
|---------|-------|
| `/api/tournaments/` | `tournament` |
| `/api/drafts/` | `draft` |
| `/api/users/me/` | `user` |

## Example Configurations

### Development

```bash
# .env.dev
TELEMETRY_ENABLED=true
LOG_LEVEL=DEBUG
LOG_FORMAT=pretty
OTEL_ENABLED=false
```

### Development with Tracing

```bash
# .env.dev with local Jaeger
TELEMETRY_ENABLED=true
LOG_LEVEL=DEBUG
LOG_FORMAT=pretty
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=dtx-backend-dev
OTEL_TRACES_SAMPLER_ARG=1.0
```

### Production

```bash
# .env.prod
TELEMETRY_ENABLED=true
LOG_LEVEL=INFO
LOG_FORMAT=json
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=https://collector.example.com:4317
OTEL_SERVICE_NAME=dtx-backend
OTEL_TRACES_SAMPLER_ARG=0.1
OTEL_EXPORTER_OTLP_HEADERS=api-key=your-production-key
```

### Disabled (Testing)

```bash
# .env.test
TELEMETRY_ENABLED=false
```
