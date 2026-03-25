# Celery & Discord Bot HTTP API Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate all external processes (celery workers, Discord bot) from direct DB access to authenticated HTTP calls to Django REST API, making Django the sole DB reader/writer.

**Architecture:** Celery workers and the Discord bot become pure HTTP clients. A configurable `INTERNAL_API_URL` + shared secret token (`X-Internal-Token`) gates internal-only endpoints at `/api/internal/`. No external process touches the DB directly — Django/Daphne is the single source of truth. Workers can run anywhere (same Docker network, remote server, different cloud).

**Tech Stack:** Custom DRF authentication class (shared secret header), `requests` library for HTTP calls, configurable `INTERNAL_API_URL` env var.

---

## Why

SQLite supports only one writer at a time. Currently 4+ Docker containers (backend, celery-worker, celery-beat, discord-bot) all write to the same SQLite file, causing `OperationalError: database is locked` under load.

The fix: make Django the **single reader/writer**. All external processes communicate via HTTP:
- **Reliability**: HTTP retries are well-understood; DB lock recovery is not
- **Scalability**: Workers can run anywhere — no shared filesystem needed
- **Simplicity**: One process owns the DB; no lock contention by design

## Internal Service Auth

A shared-secret token checked via custom DRF authentication:

```python
# backend/app/auth.py
class InternalServiceAuth(BaseAuthentication):
    def authenticate(self, request):
        token = request.headers.get("X-Internal-Token")
        expected = getattr(settings, "INTERNAL_SERVICE_TOKEN", "")
        if not expected:
            return None
        if token and token == expected:
            return (InternalServiceUser(), None)
        return None
```

Set `INTERNAL_SERVICE_TOKEN` in all docker env files. Every celery worker, beat, and Discord bot container receives it.

## Internal API URL

```python
# backend/app/internal_client.py
INTERNAL_API_URL = os.environ.get("INTERNAL_API_URL", "http://backend:8000/api/internal")
```

| Environment | Value | Why |
|-------------|-------|-----|
| Docker Compose (default) | `http://backend:8000/api/internal` | Internal Docker DNS |
| Remote worker | `https://dota.kettle.sh/api/internal` | Public URL + TLS |
| CI | Default (Docker) | Same compose network |

Workers don't need to be fast — just reliable. HTTP adds ~1-5ms latency on Docker network, irrelevant for tasks that call Discord/Steam APIs (100-500ms each).

## Migration Phases

### Phase 1: Internal auth + infra (Tasks 1-3)
Foundation: auth system, internal endpoints, HTTP client helper.

### Phase 2: Celery task migration (Tasks 4-8)
Migrate all event/Discord celery tasks from direct DB writes to HTTP.

### Phase 3: Discord bot migration (Tasks 9-11)
Bot becomes a pure Discord client that reads/writes via HTTP.

### Phase 4: Steam + avatar tasks (Tasks 12-13)
Remaining celery tasks.

### Phase 5: Cleanup + verification (Tasks 14-15)
Remove direct DB access from worker/bot containers, re-enable beat in test, full verification.

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
        """If INTERNAL_SERVICE_TOKEN is not set, all requests are rejected."""
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
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission


class InternalServiceUser:
    """Sentinel user for internal service requests (celery, discord bot)."""
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
        token = request.headers.get("X-Internal-Token") or request.META.get("HTTP_X_INTERNAL_TOKEN")
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

Add to `backend/backend/settings.py`:
```python
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
```

Add to all 4 docker env files (`.env.dev`, `.env.test`, `.env.prod`, `.env.release`):
```
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

A thin wrapper used by celery tasks and the Discord bot to call internal endpoints.

**Step 1: Implement client**

```python
# backend/app/internal_client.py
"""HTTP client for internal API calls from celery workers and Discord bot.

These processes must NOT access the database directly — all reads and writes
go through Django's REST API via this client.

Configuration:
    INTERNAL_API_URL: Base URL for internal endpoints.
        Default: http://backend:8000/api/internal (Docker Compose network)
        Remote:  https://dota.kettle.sh/api/internal
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

TIMEOUT = 30  # seconds — workers don't need to be fast, just reliable


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
            logger.error("Internal API POST %s failed: %s %s", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException as e:
        logger.exception("Internal API POST %s error: %s", path, e)
        return None


def _patch(path, data):
    """PATCH an internal endpoint."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.patch(url, json=data, headers=_headers(), timeout=TIMEOUT)
        if not resp.ok:
            logger.error("Internal API PATCH %s failed: %s %s", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException as e:
        logger.exception("Internal API PATCH %s error: %s", path, e)
        return None


def _get(path, params=None):
    """GET from an internal endpoint."""
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.get(url, params=params, headers=_headers(), timeout=TIMEOUT)
        if not resp.ok:
            logger.error("Internal API GET %s failed: %s %s", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException as e:
        logger.exception("Internal API GET %s error: %s", path, e)
        return None


# ---- Discord log endpoints ----

def create_message_log(**data):
    return _post("/discord/message-log/", data)

def create_event_log(**data):
    return _post("/discord/event-log/", data)

def update_discord_event(pk, **data):
    return _patch(f"/discord/events/{pk}/", data)

def create_signup_message(**data):
    return _post("/discord/signup-message/", data)

def create_announcement_message(**data):
    return _post("/discord/announcement/", data)

def create_event_dm(**data):
    return _post("/discord/event-dm/", data)

def update_event_dm(pk, **data):
    return _patch(f"/discord/event-dm/{pk}/", data)


# ---- Event read endpoints (for bot/celery that can't import models) ----

def get_event(pk):
    return _get(f"/events/{pk}/")

def get_event_signups(event_pk):
    return _get(f"/events/{event_pk}/signups/")


# ---- Steam endpoints ----

def batch_create_matches(data):
    return _post("/steam/matches/", data)

def update_sync_state(pk, **data):
    return _patch(f"/steam/sync-state/{pk}/", data)


# ---- User endpoints ----

def update_user_avatar(pk, avatar_url):
    return _patch(f"/users/{pk}/avatar/", {"avatar": avatar_url})
```

**Step 2: Write test**

```python
# backend/app/tests/test_internal_client.py
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from app.internal_client import create_message_log, _headers

class InternalClientTest(TestCase):
    @override_settings(INTERNAL_SERVICE_TOKEN="test-token")
    def test_headers_include_token(self):
        h = _headers()
        self.assertEqual(h["X-Internal-Token"], "test-token")

    @patch("app.internal_client.requests.post")
    @override_settings(INTERNAL_SERVICE_TOKEN="test-token")
    def test_create_message_log_calls_api(self, mock_post):
        mock_post.return_value = MagicMock(ok=True, status_code=201)
        resp = create_message_log(channel_id="123", source="test", source_id=1)
        mock_post.assert_called_once()
        self.assertTrue(resp.ok)
```

**Step 3: Commit**

```
git commit -m "feat: add internal HTTP client for celery/bot API calls"
```

---

## Task 3: Internal Discord Endpoints

**Files:**
- Create: `backend/app/views/internal.py`
- Modify: `backend/backend/urls.py`
- Test: `backend/app/tests/test_internal_endpoints.py`

Endpoints that replace direct DB writes from celery tasks:

```
POST   /api/internal/discord/message-log/       → create DiscordMessageLog
POST   /api/internal/discord/event-log/          → create DiscordEventLog
PATCH  /api/internal/discord/events/<pk>/        → update DiscordEvent
POST   /api/internal/discord/signup-message/     → create/update DiscordEventMsgSignup
POST   /api/internal/discord/announcement/       → create/update DiscordEventMsgAnnouncement
POST   /api/internal/discord/event-dm/           → create DiscordEventDM
PATCH  /api/internal/discord/event-dm/<pk>/      → update DiscordEventDM delivery status
```

All gated by `InternalServiceAuth` + `IsInternalService`.

Each endpoint:
1. Validates input
2. Creates/updates the model
3. Calls `invalidate_after_commit()` or `invalidate_obj()` as appropriate
4. Returns the created object's PK

**Step 1: Write tests for each endpoint**

**Step 2: Implement views**

**Step 3: Wire URLs under `api/internal/discord/`**

**Step 4: Commit**

```
git commit -m "feat: add /api/internal/discord/ endpoints for celery task writes"
```

---

## Task 4: Migrate `create_discord_scheduled_event`

**Files:**
- Modify: `backend/events/tasks.py` (lines 481-568)

**Current flow:**
1. `Event.objects.get()` — READ (keep direct for now, migrate in Phase 3)
2. `requests.post()` to Discord API — keep in celery
3. `DiscordMessageLog.objects.create()` → **replace with** `internal_client.create_message_log()`
4. `discord_event.save()` → **replace with** `internal_client.update_discord_event()`
5. `DiscordEventLog.objects.create()` → **replace with** `internal_client.create_event_log()`

**Step 1: Replace DB writes with HTTP calls**

**Step 2: Test — run lifecycle E2E test**

**Step 3: Commit**

---

## Task 5: Migrate `send_event_announcement`

**Files:**
- Modify: `backend/events/tasks.py` (lines 187-369)

Largest task. Replace 6+ DB write operations with HTTP calls:
- `DiscordEvent` get_or_create → `internal_client`
- `DiscordEventMsgSignup` create/update → `internal_client.create_signup_message()`
- `DiscordEventMsgAnnouncement` create/update → `internal_client.create_announcement_message()`
- `DiscordEventLog` create → `internal_client.create_event_log()`
- `DiscordMessageLog` create → `internal_client.create_message_log()`

---

## Task 6: Migrate `send_signup_update`

Small — replace `DiscordEventMsgSignup.save()` + `DiscordEventLog.create()` with HTTP calls.

---

## Task 7: Migrate `check_event_reminders`

Replace `sync_send_embed()` (which writes `DiscordMessageLog`) with Discord API call + `internal_client.create_message_log()`.

---

## Task 8: Migrate `send_subscriber_notifications`

Replace `DiscordEventDM.objects.create()` and `.save()` with `internal_client.create_event_dm()` and `internal_client.update_event_dm()`.

---

## Task 9: Discord Bot — Read via HTTP

**Files:**
- Modify: `backend/discordbot/bot.py`
- Modify: `backend/events/discord/handlers.py`

The Discord bot currently imports Django models directly:
```python
from app.models import CustomUser
user = CustomUser.objects.get(discordId=discord_id)
```

Replace with HTTP reads:
```python
resp = internal_client.get(f"/users/by-discord-id/{discord_id}/")
user_data = resp.json()
```

New internal read endpoints needed:
```
GET /api/internal/users/by-discord-id/<discord_id>/
GET /api/internal/events/<pk>/
GET /api/internal/events/<pk>/signups/
GET /api/internal/organizations/<pk>/
```

---

## Task 10: Discord Bot — Write via HTTP

The bot's interaction handlers write to DB:
- `EventSignup` creation (Discord signup flow)
- `DiscordEventLog` creation (interaction logging)
- `PlayerDotaProfile` updates (rank/screenshot uploads)
- `OrgUser` creation (auto-create from Discord)

Replace all with HTTP calls to existing REST API endpoints (using the internal service token) or new internal endpoints where existing API doesn't cover the operation.

---

## Task 11: Discord Bot — Remove Direct DB Access

**Files:**
- Modify: `docker/docker-compose.*.yaml` — bot container no longer mounts DB volume
- Modify: `backend/discordbot/bot.py` — remove all Django ORM imports

The bot becomes a pure discord.py client + HTTP client. It needs:
- `INTERNAL_API_URL`
- `INTERNAL_SERVICE_TOKEN`
- `DISCORD_BOT_TOKEN`
- No Django, no SQLite, no ORM

---

## Task 12: Migrate Steam Tasks

**Files:**
- Modify: `backend/steam/tasks.py`

New internal endpoints:
```
POST  /api/internal/steam/matches/           → batch create/update Match
POST  /api/internal/steam/player-stats/      → batch create/update PlayerMatchStats
PATCH /api/internal/steam/sync-state/<pk>/   → update LeagueSyncState
POST  /api/internal/steam/league-stats/      → trigger stats recalculation
```

---

## Task 13: Migrate Avatar Refresh

**Files:**
- Modify: `backend/app/tasks/avatar_refresh.py`

New internal endpoint:
```
PATCH /api/internal/users/<pk>/avatar/   → update CustomUser.avatar
```

---

## Task 14: Re-enable Celery Beat in Test

**Files:**
- Modify: `backend/config/celery.py`

Remove the `IS_TEST` guard. All beat tasks now use HTTP — no SQLite contention.

```python
# Remove this:
if not IS_TEST:
    _beat_schedule.update(_event_tasks)
else:
    _beat_schedule = {}

# Replace with:
_beat_schedule.update(_event_tasks)
```

---

## Task 15: Full Verification

1. Run lifecycle E2E test 10x locally — should be 10/10 passes
2. Run full Playwright suite locally
3. Push and verify CI passes
4. Deploy to production, verify celery tasks work via Grafana traces

---

## Celery Task Read Access

After Phase 3 (Discord bot), celery tasks should also read via HTTP (not direct DB). This means:

- **Phase 1-2**: Tasks still read from DB directly (SQLite reads don't lock). This is pragmatic — reads are safe.
- **Phase 3+**: Celery tasks also read via HTTP for full isolation. This enables running workers on different machines without shared filesystem.

The internal client already has `_get()` for reads. Migration is straightforward — replace `Event.objects.get(pk=X)` with `internal_client.get_event(X)`.

## Out of Scope (Future)

- **PostgreSQL migration** — eliminates SQLite limitations entirely, but requires infrastructure change
- **Herodraft tick tasks** — these use WebSocket channel layers + Redis distributed locks, different pattern (no DB contention)
- **Task result tracking** — if needed, add Celery result backend via Redis (not DB)
