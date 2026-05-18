---
name: logging
description: Structured logging conventions for DraftForge backend (Django/Celery/Daphne) and frontend (React). This skill should be used when adding log statements, creating new modules, debugging with logs, or reviewing logging patterns. Covers structlog usage, system/subsystem taxonomy, required fields, log levels, and Grafana query patterns.
---

# Structured Logging

DraftForge uses **structlog** (backend) for structured JSON logging exported to Grafana Cloud via OpenTelemetry. All logs use a `system`/`subsystem` taxonomy for filtering.

## Backend: Quick Start

```python
from telemetry.logging import get_logger
log = get_logger(__name__)

# Structured log — event name first, then kwargs
log.info("order_created", system="tournament", subsystem="registration", draft_id=5, user_id=42)
```

**Never use f-strings or `%` formatting in log messages.** The first argument is always an event name (snake_case). All context goes in kwargs.

## System / Subsystem Taxonomy

Every log MUST include `system` and `subsystem` kwargs. These are the primary Grafana filter dimensions.

| system | subsystem | Where | What |
|--------|-----------|-------|------|
| `herodraft` | `connection` | `consumers.py` | WS connect/disconnect, captain state, kicks |
| `herodraft` | `heartbeat` | `herodraft_tick.py` | Heartbeat staleness checks, heartbeat-triggered pauses |
| `herodraft` | `timer` | `herodraft_tick.py` | Tick loop lifecycle, tick broadcast, timeout auto-pick, resume |
| `websocket` | `heartbeat` | `consumers_base.py` | Heartbeat receive, captain register/unregister (generic WS infra) |
| `events` | `discord` | `events/tasks.py` | Discord event sync, announcements, reminders |
| `events` | `scheduling` | `events/tasks.py` | Event generation, signup opening, repeaters |
| `tournament` | `discord` | `discordbot/tasks.py` | Tournament DMs, bracket notifications |
| `avatars` | `endpoint` | `user/internal/avatar.py` | Internal endpoints: list-linked-users, list-guild-ids, bulk-update + invalidate |
| `avatars` | `refresh` | `app/tasks/avatar_refresh.py` | Daily Celery beat: read guild-member cache, diff against DB, POST bulk-update |
| `discord` | `lease` | `discordbot/tasks.py`, `app/views/internal.py` | DiscordMessageLog stale-lease sweep (pending NULL >5min, failed >1h) |

Add new systems/subsystems as features grow. Keep systems coarse (feature area), subsystems functional (what role the code plays).

## Log Levels

| Level | When | Exported to Grafana? |
|-------|------|---------------------|
| `DEBUG` | Per-request/per-tick detail, heartbeat received | No (prod=INFO) |
| `INFO` | State transitions, lifecycle events, periodic health | Yes |
| `WARNING` | Anomalies that self-recover (stale heartbeat, slow tick) | Yes |
| `ERROR` | Failures requiring attention (broadcast failed, API error) | Yes |

## Required Fields

Beyond `system` and `subsystem`, include relevant entity IDs:

- `draft_id` — for anything draft-related
- `user_id` / `username` — for user-scoped actions
- `event_id` — for event system logs
- `duration_s` / `elapsed_ms` — for timing-sensitive operations
- `reason` — for skipped/stopped/failed actions
- `error` — for exception context (`str(e)`, never the full traceback)

## References

- Backend patterns (structlog config, OTel export, Celery/Daphne logging, middleware): [references/backend.md](references/backend.md)
- Frontend console logging conventions: [references/frontend.md](references/frontend.md)

## Grafana Queries

```logql
# All herodraft heartbeat logs
{service_name="backend"} | json | system="herodraft" | subsystem="heartbeat"

# Slow ticks
{service_name="backend"} | json | event="tick_slow"

# All errors across systems
{service_name="backend"} | json | level="error"

# Filter by draft
{service_name="backend"} | json | draft_id="42"
```
