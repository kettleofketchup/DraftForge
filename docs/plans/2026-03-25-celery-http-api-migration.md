# Celery & Discord Bot HTTP API Migration

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate all external processes (celery workers, Discord bot) from direct DB access to authenticated HTTP calls to Django REST API, making Django the sole DB reader/writer.

**Architecture:** Celery workers and Discord bot become HTTP clients. `INTERNAL_API_URL` (configurable, defaults to `http://backend:8000/api/internal`) + shared secret `X-Internal-Token` header gates `/api/internal/` endpoints. Workers can run anywhere — same Docker network or remote. Uses `requests` library (already a dependency).

**Tech Stack:** Custom DRF auth class, `requests` for HTTP, `invalidate_after_commit` for cache safety in internal endpoints.

---

## Cache Invalidation Rules for Internal Endpoints

Internal endpoints replace direct DB writes from celery/bot. They MUST follow these patterns:

| Context | Pattern |
|---------|---------|
| Single `.save()` outside transaction | `invalidate_obj(obj)` after save |
| `.save()` inside `@transaction.atomic` | `invalidate_after_commit(obj)` |
| `.create()` | `invalidate_after_commit(obj)` (defensive) |
| M2M `.add()`/`.remove()` | `invalidate_obj(parent)` after M2M op |
| Bulk `.delete()` | `invalidate_model(Model)` |

Models cached by cacheops (1h TTL): `DiscordEvent`, `DiscordEventMsgSignup`, `DiscordEventMsgAnnouncement`, `Event`, `EventSignup`, `CustomUser`, `OrgUser`, `Match`, `PlayerMatchStats`.

Models NOT cached (write-heavy): `DiscordEventLog`, `DiscordEventDM`, `DiscordMessageLog`.

---

## Test Strategy

**Backend unit tests** (`backend/app/tests/test_internal_auth.py`, `test_internal_endpoints.py`):
- Test auth: valid token, missing token, wrong token, empty env token
- Test each endpoint: creates correct model, returns PK, rejects unauthenticated
- Test cache invalidation: verify `invalidate_obj`/`invalidate_after_commit` called
- Run via: `docker compose -f docker/docker-compose.test.yaml run --rm --entrypoint "" backend python manage.py test app.tests.test_internal_auth -v 2`

**E2E verification** (Playwright):
- Re-enable all celery beat tasks in test (Task 10)
- Run lifecycle test (`06-full-lifecycle.spec.ts`) 5x — must be 5/5 passes
- Run full suite — no new failures

---

## Task 1: Internal Service Auth

**Files:**
- Create: `backend/app/auth.py`
- Modify: `backend/backend/settings.py:41` (add INTERNAL_SERVICE_TOKEN)
- Modify: `docker/.env.dev`, `docker/.env.test`, `docker/.env.prod`, `docker/.env.release`
- Test: `backend/app/tests/test_internal_auth.py`

**Step 1: Write the failing test**

```python
# backend/app/tests/test_internal_auth.py
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory


class InternalServiceAuthTest(TestCase):
    def test_valid_token_authenticates(self):
        from app.auth import InternalServiceAuth, InternalServiceUser

        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN="test-secret")
        with override_settings(INTERNAL_SERVICE_TOKEN="test-secret"):
            result = InternalServiceAuth().authenticate(request)
            self.assertIsNotNone(result)
            self.assertIsInstance(result[0], InternalServiceUser)
            self.assertTrue(result[0].is_authenticated)
            self.assertTrue(result[0].is_staff)

    def test_missing_token_returns_none(self):
        from app.auth import InternalServiceAuth

        factory = APIRequestFactory()
        request = factory.get("/")
        with override_settings(INTERNAL_SERVICE_TOKEN="test-secret"):
            self.assertIsNone(InternalServiceAuth().authenticate(request))

    def test_wrong_token_returns_none(self):
        from app.auth import InternalServiceAuth

        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN="wrong")
        with override_settings(INTERNAL_SERVICE_TOKEN="correct"):
            self.assertIsNone(InternalServiceAuth().authenticate(request))

    def test_empty_env_token_rejects_all(self):
        from app.auth import InternalServiceAuth

        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN="anything")
        with override_settings(INTERNAL_SERVICE_TOKEN=""):
            self.assertIsNone(InternalServiceAuth().authenticate(request))


class IsInternalServiceTest(TestCase):
    def test_allows_internal_user(self):
        from app.auth import InternalServiceUser, IsInternalService

        class FakeRequest:
            user = InternalServiceUser()

        self.assertTrue(IsInternalService().has_permission(FakeRequest(), None))

    def test_rejects_regular_user(self):
        from app.auth import IsInternalService

        class FakeRequest:
            class user:
                is_authenticated = True

        self.assertFalse(IsInternalService().has_permission(FakeRequest(), None))
```

**Step 2: Run test to verify it fails**

```bash
docker compose -f docker/docker-compose.test.yaml run --rm --entrypoint "" backend \
  python manage.py test app.tests.test_internal_auth -v 2
```

Expected: `ModuleNotFoundError: No module named 'app.auth'`

**Step 3: Implement**

```python
# backend/app/auth.py
"""Internal service authentication for celery workers and Discord bot.

These processes communicate with Django via HTTP instead of accessing the
database directly. Authentication uses a shared secret token passed in the
X-Internal-Token header.

Configuration:
    INTERNAL_SERVICE_TOKEN env var — set in docker env files.
"""

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission


class InternalServiceUser:
    """Sentinel user for authenticated internal service requests."""

    is_authenticated = True
    is_staff = True
    is_superuser = False
    pk = None
    username = "_internal_service"

    def __str__(self):
        return self.username


class InternalServiceAuth(BaseAuthentication):
    """Authenticate via X-Internal-Token header (shared secret)."""

    def authenticate(self, request):
        token = request.headers.get("X-Internal-Token") or request.META.get(
            "HTTP_X_INTERNAL_TOKEN"
        )
        expected = getattr(settings, "INTERNAL_SERVICE_TOKEN", "")
        if not expected:
            return None
        if token and token == expected:
            return (InternalServiceUser(), None)
        return None


class IsInternalService(BasePermission):
    """Allow only authenticated internal service requests."""

    def has_permission(self, request, view):
        return isinstance(request.user, InternalServiceUser)
```

Add to `backend/backend/settings.py` after line 40 (`DISCORD_PUBLIC_KEY`):
```python
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
```

Add to all 4 docker env files at the end:
```
# Internal service auth (celery workers, discord bot → Django API)
INTERNAL_SERVICE_TOKEN=df-internal-dev-token-change-in-prod
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```
git commit -m "feat: add InternalServiceAuth for celery/bot HTTP calls"
```

---

## Task 2: HTTP Client Helper

**Files:**
- Create: `backend/app/internal_client.py`
- Test: `backend/app/tests/test_internal_client.py`

**Step 1: Write the failing test**

```python
# backend/app/tests/test_internal_client.py
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings


class InternalClientHeadersTest(TestCase):
    @override_settings(INTERNAL_SERVICE_TOKEN="my-token")
    def test_headers_include_token(self):
        from app.internal_client import _headers

        h = _headers()
        self.assertEqual(h["X-Internal-Token"], "my-token")
        self.assertEqual(h["Content-Type"], "application/json")


class InternalClientPostTest(TestCase):
    @patch("app.internal_client.requests.post")
    @override_settings(INTERNAL_SERVICE_TOKEN="t")
    def test_post_calls_correct_url(self, mock_post):
        mock_post.return_value = MagicMock(ok=True, status_code=201)
        from app.internal_client import _post

        _post("/discord/message-log/", {"channel_id": "123"})
        args, kwargs = mock_post.call_args
        self.assertIn("/discord/message-log/", args[0])
        self.assertEqual(kwargs["json"]["channel_id"], "123")

    @patch("app.internal_client.requests.post")
    @override_settings(INTERNAL_SERVICE_TOKEN="t")
    def test_post_returns_none_on_exception(self, mock_post):
        import requests

        mock_post.side_effect = requests.RequestException("timeout")
        from app.internal_client import _post

        result = _post("/test/", {})
        self.assertIsNone(result)
```

**Step 2: Run test to verify it fails**

**Step 3: Implement**

```python
# backend/app/internal_client.py
"""HTTP client for internal API calls from celery workers and Discord bot.

All external processes (celery, discord bot) MUST use this client instead of
importing Django models directly. Django/Daphne is the sole DB reader/writer.

Configuration:
    INTERNAL_API_URL: Base URL for internal endpoints.
        Docker default: http://backend:8000/api/internal
        Remote worker:  https://dota.kettle.sh/api/internal
    INTERNAL_SERVICE_TOKEN: Shared secret for X-Internal-Token header.
"""

import logging
import os

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

INTERNAL_API_URL = os.environ.get(
    "INTERNAL_API_URL",
    "http://backend:8000/api/internal",
)

TIMEOUT = 30  # seconds — reliability over speed


def _headers():
    return {
        "X-Internal-Token": getattr(settings, "INTERNAL_SERVICE_TOKEN", ""),
        "Content-Type": "application/json",
    }


def _post(path, data):
    """POST to an internal endpoint. Returns response or None on error."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.post(url, json=data, headers=_headers(), timeout=TIMEOUT)
        if not resp.ok:
            logger.error("Internal POST %s: %s %s", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException:
        logger.exception("Internal POST %s failed", path)
        return None


def _patch(path, data):
    """PATCH an internal endpoint. Returns response or None on error."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.patch(url, json=data, headers=_headers(), timeout=TIMEOUT)
        if not resp.ok:
            logger.error("Internal PATCH %s: %s %s", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException:
        logger.exception("Internal PATCH %s failed", path)
        return None


def _get(path, params=None):
    """GET from an internal endpoint. Returns response or None on error."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.get(url, params=params, headers=_headers(), timeout=TIMEOUT)
        if not resp.ok:
            logger.error("Internal GET %s: %s %s", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException:
        logger.exception("Internal GET %s failed", path)
        return None


# ---- Discord log writes ----

def create_message_log(**data):
    """Create DiscordMessageLog entry."""
    return _post("/discord/message-log/", data)


def create_event_log(**data):
    """Create DiscordEventLog audit entry."""
    return _post("/discord/event-log/", data)


def update_discord_event(pk, **data):
    """Update DiscordEvent fields (scheduled_event_id, signup_message, etc.)."""
    return _patch(f"/discord/events/{pk}/", data)


def create_or_update_signup_message(**data):
    """Create/update DiscordEventMsgSignup record."""
    return _post("/discord/signup-message/", data)


def create_or_update_announcement(**data):
    """Create/update DiscordEventMsgAnnouncement record."""
    return _post("/discord/announcement/", data)


def create_event_dm(**data):
    """Create DiscordEventDM record (crash-safe: create before send)."""
    return _post("/discord/event-dm/", data)


def update_event_dm(pk, **data):
    """Update DiscordEventDM delivery status after DM sent."""
    return _patch(f"/discord/event-dm/{pk}/", data)


# ---- Event reads (for bot/celery without ORM access) ----

def get_event(pk):
    """Get event data by PK."""
    return _get(f"/events/{pk}/")


def get_event_signups(event_pk):
    """Get signups for an event."""
    return _get(f"/events/{event_pk}/signups/")


# ---- Steam writes ----

def batch_upsert_matches(data):
    """Batch create/update Match + PlayerMatchStats records."""
    return _post("/steam/matches/", data)


def update_sync_state(pk, **data):
    """Update LeagueSyncState after sync."""
    return _patch(f"/steam/sync-state/{pk}/", data)


# ---- User writes ----

def update_user_avatar(pk, avatar_url):
    """Update CustomUser avatar field."""
    return _patch(f"/users/{pk}/avatar/", {"avatar": avatar_url})
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```
git commit -m "feat: add internal HTTP client for celery/bot API calls"
```

---

## Task 3: Internal Discord Endpoints

**Files:**
- Create: `backend/app/views/internal.py`
- Modify: `backend/backend/urls.py` (add internal URL patterns)
- Test: `backend/app/tests/test_internal_endpoints.py`

**Step 1: Write failing tests**

```python
# backend/app/tests/test_internal_endpoints.py
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import Organization


class InternalEndpointAuthTest(TestCase):
    """All internal endpoints reject unauthenticated requests."""

    def test_message_log_rejects_no_token(self):
        client = APIClient()
        resp = client.post("/api/internal/discord/message-log/", {}, format="json")
        self.assertEqual(resp.status_code, 403)

    @override_settings(INTERNAL_SERVICE_TOKEN="tok")
    def test_message_log_rejects_wrong_token(self):
        client = APIClient()
        resp = client.post(
            "/api/internal/discord/message-log/",
            {},
            format="json",
            HTTP_X_INTERNAL_TOKEN="wrong",
        )
        self.assertEqual(resp.status_code, 403)


class InternalDiscordMessageLogTest(TestCase):
    @override_settings(INTERNAL_SERVICE_TOKEN="tok")
    def test_create_message_log(self):
        client = APIClient()
        resp = client.post(
            "/api/internal/discord/message-log/",
            {
                "channel_id": "123456",
                "source": "event_announcement",
                "source_id": 1,
                "discord_message_id": "789",
                "status_code": 200,
                "success": True,
            },
            format="json",
            HTTP_X_INTERNAL_TOKEN="tok",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIn("id", resp.json())


class InternalDiscordEventLogTest(TestCase):
    @override_settings(INTERNAL_SERVICE_TOKEN="tok")
    def test_create_event_log(self):
        from discordbot.models import DiscordEvent
        from events.models import Event

        org = Organization.objects.create(name="Test Org")
        event = Event.objects.create(
            organization=org, name="Test Event", state="upcoming"
        )
        de = DiscordEvent.objects.create(event=event, guild_id="111")

        client = APIClient()
        resp = client.post(
            "/api/internal/discord/event-log/",
            {
                "discord_event_id": de.pk,
                "action": "create_scheduled_event",
                "target_type": "DiscordEvent",
                "success": True,
            },
            format="json",
            HTTP_X_INTERNAL_TOKEN="tok",
        )
        self.assertEqual(resp.status_code, 201)


class InternalDiscordEventUpdateTest(TestCase):
    @override_settings(INTERNAL_SERVICE_TOKEN="tok")
    def test_update_discord_event(self):
        from discordbot.models import DiscordEvent
        from events.models import Event

        org = Organization.objects.create(name="Test Org")
        event = Event.objects.create(
            organization=org, name="Test", state="upcoming"
        )
        de = DiscordEvent.objects.create(event=event, guild_id="111")

        client = APIClient()
        resp = client.patch(
            f"/api/internal/discord/events/{de.pk}/",
            {"scheduled_event_id": "999888"},
            format="json",
            HTTP_X_INTERNAL_TOKEN="tok",
        )
        self.assertEqual(resp.status_code, 200)
        de.refresh_from_db()
        self.assertEqual(de.scheduled_event_id, "999888")
```

**Step 2: Run test to verify fails**

**Step 3: Implement internal views**

```python
# backend/app/views/internal.py
"""Internal API endpoints for celery workers and Discord bot.

All endpoints require InternalServiceAuth (X-Internal-Token header).
These replace direct DB writes from external processes.

Cache invalidation:
- DiscordEvent, DiscordEventMsgSignup, DiscordEventMsgAnnouncement are cached
  (1h TTL). Use invalidate_obj() after save (outside transaction).
- DiscordEventLog, DiscordEventDM, DiscordMessageLog are NOT cached.
  No invalidation needed.
"""

import logging

from cacheops import invalidate_obj
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService

logger = logging.getLogger(__name__)

# Shorthand decorators for all internal views
_auth = [InternalServiceAuth]
_perm = [IsInternalService]


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_discord_message_log(request):
    """Create a DiscordMessageLog entry (not cached — no invalidation needed)."""
    from discordbot.models import DiscordMessageLog

    log_entry = DiscordMessageLog.objects.create(**request.data)
    return Response({"id": log_entry.pk}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_discord_event_log(request):
    """Create a DiscordEventLog audit entry (not cached)."""
    from discordbot.models import DiscordEvent, DiscordEventLog

    data = dict(request.data)
    discord_event_id = data.pop("discord_event_id")
    discord_event = DiscordEvent.objects.get(pk=discord_event_id)
    entry = DiscordEventLog.objects.create(discord_event=discord_event, **data)
    return Response({"id": entry.pk}, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_discord_event(request, pk):
    """Update DiscordEvent fields. CACHED — invalidate after save."""
    from discordbot.models import DiscordEvent

    de = DiscordEvent.objects.get(pk=pk)
    for field, value in request.data.items():
        setattr(de, field, value)
    de.save()
    invalidate_obj(de)  # safe — outside transaction, save already committed
    return Response({"id": de.pk})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_or_update_signup_message(request):
    """Create/update DiscordEventMsgSignup. CACHED — invalidate after save."""
    from discordbot.models import ChannelType, DiscordEventMsgSignup

    data = dict(request.data)
    event_id = data.pop("event_id")
    channel_id = data.pop("channel_id")

    msg, created = DiscordEventMsgSignup.objects.get_or_create(
        event_id=event_id,
        channel_id=channel_id,
        defaults={"channel_type": data.get("channel_type", ChannelType.TEXT)},
    )
    for field, value in data.items():
        setattr(msg, field, value)
    msg.save()
    invalidate_obj(msg)
    return Response(
        {"id": msg.pk, "created": created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_or_update_announcement(request):
    """Create/update DiscordEventMsgAnnouncement. CACHED — invalidate after save."""
    from discordbot.models import ChannelType, DiscordEventMsgAnnouncement

    data = dict(request.data)
    event_id = data.pop("event_id")
    channel_id = data.pop("channel_id")

    msg, created = DiscordEventMsgAnnouncement.objects.get_or_create(
        event_id=event_id,
        channel_id=channel_id,
        defaults={"channel_type": data.get("channel_type", ChannelType.TEXT)},
    )
    for field, value in data.items():
        setattr(msg, field, value)
    msg.save()
    invalidate_obj(msg)
    return Response(
        {"id": msg.pk, "created": created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_event_dm(request):
    """Create DiscordEventDM record (not cached). Crash-safe: create before send."""
    from discordbot.models import DiscordEventDM

    dm = DiscordEventDM.objects.create(**request.data)
    return Response({"id": dm.pk}, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_event_dm(request, pk):
    """Update DiscordEventDM delivery status (not cached)."""
    from discordbot.models import DiscordEventDM

    dm = DiscordEventDM.objects.get(pk=pk)
    for field, value in request.data.items():
        setattr(dm, field, value)
    dm.save()
    return Response({"id": dm.pk})
```

Wire URLs in `backend/backend/urls.py` — add before the test URL block (before line 296):

```python
from app.views.internal import (
    create_discord_event_log,
    create_discord_message_log,
    create_event_dm,
    create_or_update_announcement,
    create_or_update_signup_message,
    update_discord_event,
    update_event_dm,
)

# Internal API — celery workers and Discord bot (token auth)
path("api/internal/discord/message-log/", create_discord_message_log),
path("api/internal/discord/event-log/", create_discord_event_log),
path("api/internal/discord/events/<int:pk>/", update_discord_event),
path("api/internal/discord/signup-message/", create_or_update_signup_message),
path("api/internal/discord/announcement/", create_or_update_announcement),
path("api/internal/discord/event-dm/", create_event_dm),
path("api/internal/discord/event-dm/<int:pk>/", update_event_dm),
```

**Step 4: Run tests**

```bash
docker compose -f docker/docker-compose.test.yaml run --rm --entrypoint "" backend \
  python manage.py test app.tests.test_internal_endpoints -v 2
```

**Step 5: Commit**

```
git commit -m "feat: add /api/internal/discord/ endpoints for celery task writes"
```

---

## Task 4: Migrate `create_discord_scheduled_event`

**Files:**
- Modify: `backend/events/tasks.py:481-567`

Replace 3 direct DB writes with HTTP calls. The task still reads Event from DB directly (reads don't lock SQLite) and still calls the Discord API directly (that's the async work celery is for).

**Step 1: Replace DB writes with internal_client calls**

Change `backend/events/tasks.py` `create_discord_scheduled_event` function:

```python
# BEFORE (lines 521-530):
DiscordMessageLog.objects.create(
    channel_id=guild_id,
    embed_data=payload,
    source="create_discord_event",
    source_id=event.pk,
    discord_message_id=data.get("id"),
    status_code=response.status_code,
    response_data=data,
    success=success,
)

# AFTER:
from app.internal_client import create_message_log
create_message_log(
    channel_id=guild_id,
    embed_data=payload,
    source="create_discord_event",
    source_id=event.pk,
    discord_message_id=data.get("id"),
    status_code=response.status_code,
    response_data=data,
    success=success,
)
```

```python
# BEFORE (lines 534-536):
discord_event.scheduled_event_id = data["id"]
discord_event.save(update_fields=["scheduled_event_id", "updated_at"])
invalidate_obj(discord_event)

# AFTER:
from app.internal_client import update_discord_event
update_discord_event(discord_event.pk, scheduled_event_id=data["id"])
```

```python
# BEFORE (lines 539-546):
DiscordEventLog.objects.create(
    discord_event=discord_event,
    action="create_scheduled_event",
    target_type="DiscordEvent",
    status_code=response.status_code,
    response_data=data,
    success=success,
)

# AFTER:
from app.internal_client import create_event_log
create_event_log(
    discord_event_id=discord_event.pk,
    action="create_scheduled_event",
    target_type="DiscordEvent",
    status_code=response.status_code,
    response_data=data,
    success=success,
)
```

Apply same pattern to the `except` block (lines 549-563).

**Step 2: Test — run lifecycle E2E test**

```bash
just test::setup
just test::pw::spec "06-full-lifecycle"
```

**Step 3: Commit**

```
git commit -m "feat: migrate create_discord_scheduled_event to internal HTTP API"
```

---

## Task 5: Migrate `send_signup_update`

**Files:**
- Modify: `backend/events/tasks.py:372-457`

Replace `signup_msg.save()` and `DiscordEventLog.objects.create()` with HTTP calls.

---

## Task 6: Migrate `send_event_announcement`

**Files:**
- Modify: `backend/events/tasks.py:187-369`

Largest migration — 6+ DB write operations. Replace each with the corresponding `internal_client` function. The `_get_or_create_discord_event` helper also needs to use HTTP.

Add new internal endpoint for get-or-create DiscordEvent:
```
POST /api/internal/discord/events/get-or-create/
  { "event_id": 1, "guild_id": "123" }
  → { "id": 5, "created": true }
```

---

## Task 7: Migrate `check_event_reminders` + `send_subscriber_notifications`

**Files:**
- Modify: `backend/events/tasks.py:662-876`

Replace `sync_send_embed()` internals (which write `DiscordMessageLog`) with Discord API call + `internal_client.create_message_log()`. Replace `DiscordEventDM` writes with `internal_client.create_event_dm()` / `update_event_dm()`.

---

## Task 8: Migrate remaining Discord tasks

**Files:**
- Modify: `backend/events/tasks.py` — `send_new_event_notification`, `sync_discord_event_signups`, `mark_interested_discord_event`
- Modify: `backend/discordbot/tasks.py` — `check_scheduled_events`

Same pattern: keep Discord API calls in celery, replace DB writes with HTTP.

---

## Task 9: Migrate Steam tasks

**Files:**
- Modify: `backend/steam/tasks.py`
- Create: `backend/app/views/internal_steam.py`

New internal endpoints:
```
POST  /api/internal/steam/matches/           → batch upsert Match + PlayerMatchStats
PATCH /api/internal/steam/sync-state/<pk>/   → update LeagueSyncState
POST  /api/internal/steam/league-stats/<pk>/ → trigger stats recalculation
```

---

## Task 10: Re-enable Celery Beat in Test + Full Verification

**Files:**
- Modify: `backend/config/celery.py` — remove IS_TEST guard

```python
# Remove:
if not IS_TEST:
    _beat_schedule.update(_event_tasks)
else:
    _beat_schedule = {}

# Replace with:
_beat_schedule.update(_event_tasks)
```

**Verification:**
1. `just test::setup`
2. Run lifecycle test 5x: `just test::pw::spec "06-full-lifecycle"` — must be 5/5 passes
3. Run full suite: `just test::pw::headless` — no new failures
4. Push and verify CI: `gh run watch`

---

## Future Tasks (Separate Plans)

### Discord Bot Migration (Phase 4)
The bot currently imports Django models directly in `discordbot/bot.py` and `events/discord/handlers.py`. Migrate to HTTP client using `internal_client`. The bot container then needs only:
- `INTERNAL_API_URL`
- `INTERNAL_SERVICE_TOKEN`
- `DISCORD_BOT_TOKEN`
- No Django ORM, no SQLite mount

### Avatar Refresh (Phase 3)
```
PATCH /api/internal/users/<pk>/avatar/
```

### PostgreSQL Migration
Eliminates SQLite limitations entirely. Separate infrastructure plan.
