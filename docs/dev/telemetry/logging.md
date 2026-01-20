# Logging Guide

This guide covers how to add structured logging to your code.

## Getting a Logger

```python
from telemetry.logging import get_logger

log = get_logger(__name__)
```

Always pass `__name__` to get a logger named after your module. This appears in the `logger` field of log output.

## Logging Events

### Basic Logging

```python
# Simple event
log.info("user_registered")

# Event with context
log.info("user_registered", user_id=42, username="alice")

# With dynamic values
log.info("order_placed", order_id=order.id, total=order.total)
```

### Event Naming

Use snake_case event names that describe what happened:

```python
# Good
log.info("tournament_created", tournament_id=5)
log.info("draft_started", draft_id=12, participant_count=8)
log.info("match_completed", match_id=99, winner_id=3)

# Avoid
log.info("Created a tournament")  # Human-readable strings are harder to filter
log.info("TournamentCreated")     # PascalCase inconsistent with conventions
```

## Log Levels

| Level | Method | When to Use |
|-------|--------|-------------|
| DEBUG | `log.debug()` | Detailed debugging info, rarely needed in production |
| INFO | `log.info()` | Normal operations, key events |
| WARNING | `log.warning()` | Unexpected but handled situations |
| ERROR | `log.error()` | Failures that need attention |

### Examples

```python
# DEBUG - Detailed tracing
log.debug("cache_lookup", key="tournament:5", hit=True)

# INFO - Normal operations
log.info("draft_pick_made", draft_id=12, hero="Invoker", pick_num=5)

# WARNING - Unexpected but handled
log.warning("rate_limit_approached", user_id=42, requests=95, limit=100)

# ERROR - Failures
log.error("payment_failed", order_id=99, error="Card declined")
```

### Logging Exceptions

```python
try:
    process_payment(order)
except PaymentError as e:
    log.error("payment_failed", order_id=order.id, error=str(e), exc_info=True)
    raise
```

The `exc_info=True` parameter includes the full stack trace.

## Context Fields

Context fields are automatically added to all logs within scope:

### HTTP Request Context

These fields are automatically added by `TelemetryMiddleware`:

| Field | Description |
|-------|-------------|
| `request.id` | Unique request identifier |
| `user.id` | Authenticated user ID |
| `labels` | Resource types in URL |
| `{resource}.id` | Resource IDs (e.g., `tournament.id`) |

### WebSocket Context

Added by `TelemetryConsumerMixin`:

| Field | Description |
|-------|-------------|
| `ws.conn_id` | Unique connection identifier |
| `user.id` | Authenticated user ID |
| `labels` | Resource types in path |
| `{resource}.id` | Resource IDs |

### Celery Task Context

Added by `TelemetryTask`:

| Field | Description |
|-------|-------------|
| `task.id` | Celery task ID |
| `task.name` | Task function name |
| `request.id` | Propagated or generated request ID |
| `user.id` | Propagated user ID |

## Binding Additional Context

You can bind additional context for a scope:

```python
import structlog

# Bind context for remaining scope
structlog.contextvars.bind_contextvars(
    organization_id=org.id,
    subscription_tier="premium"
)

# All subsequent logs include this context
log.info("feature_enabled", feature="bulk_import")
# Output includes: organization_id=5, subscription_tier="premium"
```

!!! warning "Context Cleanup"
    Context is automatically cleared at the end of request/task scope.
    If binding context in long-running code, clear it manually:

    ```python
    structlog.contextvars.clear_contextvars()
    ```

## Output Formats

### Development (Pretty)

In development (`NODE_ENV=dev`), logs use colored console output:

```
2024-01-15 10:23:45 [info     ] tournament_created [app.views.tournament] tournament_id=5 request.id=abc-123
```

### Production (JSON)

In production, logs are JSON for easy parsing:

```json
{
  "timestamp": "2024-01-15T10:23:45.123456Z",
  "level": "info",
  "logger": "app.views.tournament",
  "event": "tournament_created",
  "tournament_id": 5,
  "request.id": "abc-123"
}
```

## Best Practices

### 1. Log at Decision Points

```python
def process_draft_pick(draft_id, hero):
    draft = get_draft(draft_id)

    if draft.is_complete:
        log.warning("draft_pick_rejected", reason="draft_complete")
        return None

    pick = draft.add_pick(hero)
    log.info("draft_pick_added", hero=hero, pick_number=pick.number)
    return pick
```

### 2. Include Relevant IDs

```python
# Good - includes all relevant identifiers
log.info("match_started",
    match_id=match.id,
    tournament_id=match.tournament_id,
    team_a_id=match.team_a_id,
    team_b_id=match.team_b_id
)

# Less useful - missing context
log.info("match_started")
```

### 3. Avoid Logging Sensitive Data

```python
# Bad - logs password
log.info("login_attempt", username=user, password=pwd)

# Good - only log what's needed
log.info("login_attempt", username=user)
log.info("login_success", user_id=authenticated_user.id)
```

### 4. Use Appropriate Levels

```python
# Don't use ERROR for expected failures
if not user.has_permission:
    log.info("access_denied", user_id=user.id, resource="admin_panel")
    # Not log.error() - this is expected behavior

# Use ERROR for unexpected failures
try:
    send_email(user.email)
except SMTPError as e:
    log.error("email_failed", user_id=user.id, error=str(e), exc_info=True)
```
