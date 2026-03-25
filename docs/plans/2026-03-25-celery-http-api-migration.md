# Celery HTTP API Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate celery tasks from direct SQLite access to authenticated HTTP calls to Django REST API, eliminating multi-process write contention.

**Architecture:** Celery workers become HTTP clients. A new internal service auth system (shared secret token) gates internal-only endpoints at `/api/internal/`. Tasks read data and report results via HTTP — Django/Daphne is the sole DB writer. The Discord bot also migrates to this pattern.

**Tech Stack:** Django REST Framework TokenAuthentication (or custom header auth), `httpx` for async HTTP from celery, existing `requests` library for sync calls.

---

## Why

SQLite supports only one writer at a time. Currently 4+ Docker containers (backend, celery-worker, celery-beat, discord-bot) all write to the same SQLite file. Django's `busy_timeout=30s` helps but doesn't prevent `OperationalError: database is locked` under rapid writes (10 approve calls + celery notification tasks firing simultaneously).

The fix: make Django the **single writer**. Celery and the Discord bot call Django's HTTP API to read data and report results. All DB writes happen inside Daphne's process.

## Internal Service Auth

A simple shared-secret token, checked via a custom DRF authentication class:

```python
# backend/app/auth.py
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")

class InternalServiceAuth(BaseAuthentication):
    def authenticate(self, request):
        token = request.headers.get("X-Internal-Token")
        if token and token == INTERNAL_SERVICE_TOKEN:
            return (InternalServiceUser(), None)
        return None

class IsInternalService(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, InternalServiceUser)
```

Set `INTERNAL_SERVICE_TOKEN` in `.env.dev`, `.env.test`, `.env.prod`, `.env.release`. Celery worker and Discord bot containers receive it via docker-compose env_file.

## Migration Phases

### Phase 1: Internal auth + Discord log writing (highest impact)
Tasks: `send_event_announcement`, `send_signup_update`, `create_discord_scheduled_event`, `check_event_reminders`, `send_subscriber_notifications`

These are the tasks causing SQLite lock contention. They follow the pattern:
1. Read event data (keep as direct DB read — celery shares the same mounted DB file for reads)
2. Call Discord API (keep in celery — this is the async work)
3. **Write results back** → migrate to HTTP POST to `/api/internal/discord/log/`

### Phase 2: Steam match sync
Tasks: `sync_league_matches_task`, `update_league_stats_task`

Same pattern: fetch from Steam API, then write Match/PlayerMatchStats via HTTP.

### Phase 3: Avatar refresh + scheduled events
Tasks: `refresh_discord_avatars`, `check_scheduled_events`

Lower priority — these write infrequently and rarely contend.

### Phase 4: Discord bot migration
The bot currently imports Django models directly. Migrate to HTTP client calling existing REST API endpoints + new internal endpoints as needed.

---

## Task 1: Internal Service Auth

**Files:**
- Create: `backend/app/auth.py`
- Modify: `backend/backend/settings.py`
- Modify: `docker/.env.dev`, `docker/.env.test`, `docker/.env.prod`, `docker/.env.release`
- Test: `backend/app/tests/test_internal_auth.py`

**Step 1: Write the failing test**

```python
# backend/app/tests/test_internal_auth.py
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory
from app.auth import InternalServiceAuth, InternalServiceUser

class InternalServiceAuthTest(TestCase):
    def test_valid_token_authenticates(self):
        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN="test-secret-token")
        with override_settings(INTERNAL_SERVICE_TOKEN="test-secret-token"):
            auth = InternalServiceAuth()
            result = auth.authenticate(request)
            self.assertIsNotNone(result)
            self.assertIsInstance(result[0], InternalServiceUser)

    def test_missing_token_returns_none(self):
        factory = APIRequestFactory()
        request = factory.get("/")
        auth = InternalServiceAuth()
        result = auth.authenticate(request)
        self.assertIsNone(result)

    def test_wrong_token_returns_none(self):
        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN="wrong-token")
        with override_settings(INTERNAL_SERVICE_TOKEN="correct-token"):
            auth = InternalServiceAuth()
            result = auth.authenticate(request)
            self.assertIsNone(result)

    def test_empty_env_token_rejects_all(self):
        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN="anything")
        with override_settings(INTERNAL_SERVICE_TOKEN=""):
            auth = InternalServiceAuth()
            result = auth.authenticate(request)
            self.assertIsNone(result)
```

**Step 2: Run test to verify it fails**

```bash
docker compose -f docker/docker-compose.test.yaml run --rm --entrypoint "" backend \
  python manage.py test app.tests.test_internal_auth -v 2
```

**Step 3: Implement InternalServiceAuth**

```python
# backend/app/auth.py
import os
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission

class InternalServiceUser:
    """Sentinel user for internal service requests."""
    is_authenticated = True
    is_staff = True
    is_superuser = False
    pk = None
    username = "_internal_service"

    def __str__(self):
        return self.username

class InternalServiceAuth(BaseAuthentication):
    """Authenticate internal service requests via shared secret token."""
    def authenticate(self, request):
        token = request.headers.get("X-Internal-Token") or request.META.get("HTTP_X_INTERNAL_TOKEN")
        expected = getattr(settings, "INTERNAL_SERVICE_TOKEN", "")
        if not expected:
            return None  # No token configured = reject all
        if token and token == expected:
            return (InternalServiceUser(), None)
        return None

class IsInternalService(BasePermission):
    """Allow only internal service requests."""
    def has_permission(self, request, view):
        return isinstance(request.user, InternalServiceUser)
```

Add to settings.py:
```python
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
```

Add to all docker env files:
```
INTERNAL_SERVICE_TOKEN=df-internal-dev-token-change-in-prod
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git commit -m "feat: add InternalServiceAuth for celery/bot HTTP calls"
```

---

## Task 2: Internal Discord Log Endpoint

**Files:**
- Create: `backend/app/views/internal.py`
- Modify: `backend/backend/urls.py`
- Test: `backend/app/tests/test_internal_endpoints.py`

This is the core endpoint that replaces direct `DiscordMessageLog.objects.create()` and `DiscordEventLog.objects.create()` calls from celery tasks.

**Step 1: Write the failing test**

```python
# backend/app/tests/test_internal_endpoints.py
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

class InternalDiscordLogEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.token = "test-internal-token"
        self.headers = {"HTTP_X_INTERNAL_TOKEN": self.token}

    @override_settings(INTERNAL_SERVICE_TOKEN="test-internal-token")
    def test_create_discord_message_log(self):
        resp = self.client.post("/api/internal/discord/message-log/", {
            "channel_id": "123456",
            "source": "event_announcement",
            "source_id": 1,
            "discord_message_id": "789",
            "status_code": 200,
            "success": True,
        }, format="json", **self.headers)
        self.assertEqual(resp.status_code, 201)

    @override_settings(INTERNAL_SERVICE_TOKEN="test-internal-token")
    def test_create_discord_event_log(self):
        # Requires a DiscordEvent to exist
        from events.models import Event
        from discordbot.models import DiscordEvent
        org = Organization.objects.create(name="Test Org")
        event = Event.objects.create(organization=org, name="Test", state="upcoming")
        de = DiscordEvent.objects.create(event=event, guild_id="111")

        resp = self.client.post("/api/internal/discord/event-log/", {
            "discord_event_id": de.pk,
            "action": "send_signup_post",
            "target_type": "DiscordEventMsgSignup",
            "success": True,
        }, format="json", **self.headers)
        self.assertEqual(resp.status_code, 201)

    def test_rejects_without_token(self):
        resp = self.client.post("/api/internal/discord/message-log/", {
            "channel_id": "123456",
            "source": "test",
            "source_id": 1,
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    @override_settings(INTERNAL_SERVICE_TOKEN="test-internal-token")
    def test_update_discord_event(self):
        """Update DiscordEvent fields (scheduled_event_id, signup_message, etc.)"""
        from events.models import Event
        from discordbot.models import DiscordEvent
        org = Organization.objects.create(name="Test Org")
        event = Event.objects.create(organization=org, name="Test", state="upcoming")
        de = DiscordEvent.objects.create(event=event, guild_id="111")

        resp = self.client.patch(f"/api/internal/discord/events/{de.pk}/", {
            "scheduled_event_id": "999888777",
        }, format="json", **self.headers)
        self.assertEqual(resp.status_code, 200)
        de.refresh_from_db()
        self.assertEqual(de.scheduled_event_id, "999888777")
```

**Step 2: Implement internal endpoints**

```python
# backend/app/views/internal.py
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from app.auth import InternalServiceAuth, IsInternalService

@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def create_discord_message_log(request):
    """Create a DiscordMessageLog entry. Called by celery tasks after Discord API calls."""
    from discordbot.models import DiscordMessageLog
    log = DiscordMessageLog.objects.create(**request.data)
    return Response({"id": log.pk}, status=status.HTTP_201_CREATED)

@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def create_discord_event_log(request):
    """Create a DiscordEventLog entry. Called by celery tasks for audit logging."""
    from discordbot.models import DiscordEventLog
    data = request.data.copy()
    discord_event_id = data.pop("discord_event_id")
    from discordbot.models import DiscordEvent
    discord_event = DiscordEvent.objects.get(pk=discord_event_id)
    log = DiscordEventLog.objects.create(discord_event=discord_event, **data)
    return Response({"id": log.pk}, status=status.HTTP_201_CREATED)

@api_view(["PATCH"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def update_discord_event(request, pk):
    """Update a DiscordEvent record. Called by celery after creating Discord scheduled events."""
    from cacheops import invalidate_obj
    from discordbot.models import DiscordEvent
    de = DiscordEvent.objects.get(pk=pk)
    for field, value in request.data.items():
        setattr(de, field, value)
    de.save()
    invalidate_obj(de)
    return Response({"id": de.pk})
```

Wire up URLs:
```python
# In backend/backend/urls.py, add:
path("api/internal/discord/message-log/", create_discord_message_log),
path("api/internal/discord/event-log/", create_discord_event_log),
path("api/internal/discord/events/<int:pk>/", update_discord_event),
```

**Step 3: Run tests, commit**

---

## Task 3: HTTP Client Helper for Celery Tasks

**Files:**
- Create: `backend/app/internal_client.py`
- Test: `backend/app/tests/test_internal_client.py`

A thin wrapper so tasks can call internal endpoints easily:

```python
# backend/app/internal_client.py
import os
import requests
from django.conf import settings

def _get_base_url():
    """Internal URL for the Django backend (within Docker network)."""
    host = os.environ.get("BACKEND_HOST", "backend")
    port = os.environ.get("BACKEND_PORT", "8000")
    return f"http://{host}:{port}/api/internal"

def _get_headers():
    return {
        "X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN,
        "Content-Type": "application/json",
    }

def post_discord_message_log(**data):
    url = f"{_get_base_url()}/discord/message-log/"
    return requests.post(url, json=data, headers=_get_headers(), timeout=10)

def post_discord_event_log(**data):
    url = f"{_get_base_url()}/discord/event-log/"
    return requests.post(url, json=data, headers=_get_headers(), timeout=10)

def patch_discord_event(pk, **data):
    url = f"{_get_base_url()}/discord/events/{pk}/"
    return requests.patch(url, json=data, headers=_get_headers(), timeout=10)
```

---

## Task 4: Migrate `create_discord_scheduled_event` Task

**Files:**
- Modify: `backend/events/tasks.py` (lines 481-568)

This is the simplest task to migrate — clear pattern of read → Discord API → write results.

**Current flow:**
1. Read Event + Organization (keep as direct DB read)
2. POST to Discord API (keep in celery)
3. `DiscordMessageLog.objects.create()` → **replace with** `post_discord_message_log()`
4. `discord_event.save(update_fields=["scheduled_event_id"])` → **replace with** `patch_discord_event(pk, scheduled_event_id=data["id"])`
5. `DiscordEventLog.objects.create()` → **replace with** `post_discord_event_log()`

**Test:** Run the lifecycle E2E test 5x to verify no more OperationalError.

---

## Task 5: Migrate `send_event_announcement` Task

**Files:**
- Modify: `backend/events/tasks.py` (lines 187-369)

Largest task — creates DiscordEvent, DiscordEventMsgSignup, DiscordEventMsgAnnouncement, DiscordEventLog, DiscordMessageLog.

Needs a new internal endpoint:
```
POST /api/internal/discord/signup-message/  → creates/updates DiscordEventMsgSignup
POST /api/internal/discord/announcement/    → creates/updates DiscordEventMsgAnnouncement
```

Or a single batch endpoint:
```
POST /api/internal/discord/announcement-result/
{
    "event_id": 1,
    "signup_post": { "channel_id": "...", "message_id": "...", "thread_id": "...", "channel_type": "forum" },
    "announcement": { "channel_id": "...", "message_id": "..." },
    "logs": [{ "action": "send_signup_post", ... }]
}
```

The batch approach is better — one HTTP call replaces 5-6 DB writes.

---

## Task 6: Migrate `send_signup_update` Task

**Files:**
- Modify: `backend/events/tasks.py` (lines 372-457)

Small — just updates `message_last_updated` and creates one log entry.

---

## Task 7: Migrate `check_event_reminders` Task

**Files:**
- Modify: `backend/events/tasks.py` (lines 662-780)

Writes `DiscordMessageLog` for each reminder sent. Replace with `post_discord_message_log()`.

---

## Task 8: Migrate `send_subscriber_notifications` Task

**Files:**
- Modify: `backend/events/tasks.py` (lines 783-876)

Creates `DiscordEventDM` records. Needs:
```
POST /api/internal/discord/event-dm/
```

---

## Task 9: Migrate Steam Tasks (Phase 2)

**Files:**
- Modify: `backend/steam/tasks.py`

Needs internal endpoints for:
```
POST /api/internal/steam/matches/         → batch create/update Match records
POST /api/internal/steam/player-stats/    → batch create/update PlayerMatchStats
PATCH /api/internal/steam/sync-state/<pk>/ → update LeagueSyncState
```

---

## Task 10: Migrate Avatar Refresh (Phase 3)

**Files:**
- Modify: `backend/app/tasks/avatar_refresh.py`

Needs:
```
PATCH /api/internal/users/<pk>/avatar/   → update CustomUser.avatar
```

---

## Task 11: Re-enable Celery Beat Tasks in Test

**Files:**
- Modify: `backend/config/celery.py`

Once tasks use HTTP instead of direct DB writes, re-enable all beat tasks in test. The SQLite lock contention is eliminated because Django is the sole writer.

---

## Task 12: Full E2E Verification

Run the lifecycle test 10x locally with all beat tasks enabled. Should be 10/10 passes.

Run full Playwright suite. Push and verify CI.

---

## Out of Scope (Future)

- **Discord bot migration to HTTP client** (Phase 4) — larger effort, separate plan
- **Herodraft tick tasks** — these use `select_for_update()` and WebSocket channel layers, different pattern
- **PostgreSQL migration** — eliminates SQLite limitations entirely, but requires infrastructure change
