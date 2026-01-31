# Context Guide

This guide covers how to add telemetry context to new endpoints and features.

## Adding Labels for New URLs

When adding new API endpoints, update the label extraction patterns in `telemetry/labels.py`.

### Adding a New Resource

```python
# In telemetry/labels.py

RESOURCE_PATTERNS = [
    # Existing patterns...

    # Add your new resource
    (r"/seasons/(\d+)", "season"),     # /api/seasons/5/
    (r"/seasons/?$", "season"),         # /api/seasons/
]
```

### Pattern Rules

1. **Patterns with IDs first** - More specific patterns should come before list endpoints
2. **Use capture groups for IDs** - `(\d+)` captures numeric IDs
3. **End with optional slash** - Use `/?$` for list endpoints

### Testing Your Patterns

```python
from telemetry.labels import extract_labels

# Test your new patterns
assert extract_labels("/api/seasons/5/") == {
    "labels": ["season"],
    "season.id": 5
}

assert extract_labels("/api/seasons/") == {
    "labels": ["season"]
}
```

## Adding Context in Views

### Function-Based Views

```python
import structlog
from telemetry.logging import get_logger

log = get_logger(__name__)

def my_view(request, tournament_id):
    # Middleware already provides: request.id, user.id, tournament.id

    # Add additional context for this scope
    structlog.contextvars.bind_contextvars(
        organization_id=tournament.organization_id
    )

    # All logs now include organization_id
    log.info("tournament_accessed")

    return Response(...)
```

### Class-Based Views

```python
import structlog
from rest_framework.views import APIView
from telemetry.logging import get_logger

log = get_logger(__name__)

class TournamentDetailView(APIView):
    def get(self, request, tournament_id):
        tournament = get_object_or_404(Tournament, pk=tournament_id)

        # Add business context
        structlog.contextvars.bind_contextvars(
            organization_id=tournament.organization_id,
            tournament_status=tournament.status
        )

        log.info("tournament_retrieved")
        return Response(TournamentSerializer(tournament).data)
```

## Adding Context to WebSocket Consumers

### Basic Setup

```python
from channels.generic.websocket import AsyncWebsocketConsumer
from telemetry.websocket import TelemetryConsumerMixin
from telemetry.logging import get_logger

log = get_logger(__name__)

class MyConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
    async def connect(self):
        # Initialize telemetry first
        await self.telemetry_connect()

        # Your connection logic
        await self.accept()

    async def disconnect(self, close_code):
        # Clean up telemetry
        await self.telemetry_disconnect(close_code)

    async def receive(self, text_data):
        # Optional: log received messages
        await self.telemetry_receive(text_data)

        # Your message handling
        log.info("message_received")
```

### Adding Custom Context

```python
async def connect(self):
    await self.telemetry_connect()

    # Add custom context after telemetry_connect
    draft_id = self.scope["url_route"]["kwargs"]["draft_id"]
    draft = await get_draft(draft_id)

    structlog.contextvars.bind_contextvars(
        draft_status=draft.status,
        participant_count=draft.participant_count
    )

    await self.accept()
```

## Propagating Context to Celery Tasks

### From HTTP Requests

```python
import structlog
from myapp.tasks import process_tournament

def start_processing(request, tournament_id):
    # Get current context
    ctx = structlog.contextvars.get_contextvars()

    # Propagate to Celery task
    process_tournament.delay(
        tournament_id,
        _request_id=ctx.get("request.id"),
        _user_id=request.user.pk
    )

    return Response({"status": "processing"})
```

### From WebSocket Consumers

```python
async def handle_action(self, data):
    ctx = structlog.contextvars.get_contextvars()

    # Propagate context to background task
    process_draft_action.delay(
        self.draft_id,
        data["action"],
        _request_id=ctx.get("request.id"),
        _user_id=ctx.get("user.id")
    )
```

### In the Celery Task

```python
from celery import current_app
from telemetry.celery import TelemetryTask
from telemetry.logging import get_logger

log = get_logger(__name__)

@current_app.task(base=TelemetryTask)
def process_tournament(tournament_id):
    # Context is already bound: task.id, task.name, request.id, user.id

    log.info("processing_started", tournament_id=tournament_id)

    # Your task logic
    result = do_processing(tournament_id)

    log.info("processing_complete", result_count=len(result))
    return result
```

## Context Field Naming Conventions

Follow these conventions for consistent logs:

### Resource Identifiers

```python
# Pattern: {resource}.id
"tournament.id": 5
"draft.id": 12
"user.id": 42
"match.id": 99
```

### Status Fields

```python
# Pattern: {resource}_status or status
"draft_status": "active"
"tournament_status": "registration"
```

### Counts

```python
# Pattern: {thing}_count
"participant_count": 8
"pick_count": 24
"result_count": 100
```

### HTTP Fields (OTel conventions)

```python
"http.method": "POST"
"http.route": "/api/tournaments/"
"http.status_code": 201
```

### Timing

```python
"duration_ms": 45.67
```

## Testing Context Binding

```python
import structlog
from django.test import TestCase, RequestFactory

class TelemetryContextTest(TestCase):
    def test_context_binding(self):
        # Clear any existing context
        structlog.contextvars.clear_contextvars()

        # Bind context
        structlog.contextvars.bind_contextvars(
            tournament_id=5,
            user_id=42
        )

        # Verify context
        ctx = structlog.contextvars.get_contextvars()
        self.assertEqual(ctx["tournament_id"], 5)
        self.assertEqual(ctx["user_id"], 42)

        # Clean up
        structlog.contextvars.clear_contextvars()
```
