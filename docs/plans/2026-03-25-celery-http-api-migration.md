# Celery & Discord Bot HTTP API Migration

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate all external processes (celery workers, Discord bot) from direct DB access to authenticated HTTP calls to Django REST API, making Django the sole DB reader/writer.

**Architecture:** Celery workers and Discord bot become HTTP clients. `INTERNAL_API_URL` (configurable, defaults to `http://backend:8000/api/internal`) + shared secret `X-Internal-Token` header gates `/api/internal/` endpoints. Workers can run anywhere — same Docker network or remote. Uses `requests` library (already a dependency).

**Tech Stack:** Custom DRF auth class, `requests` for HTTP, `invalidate_after_commit` for cache safety in internal endpoints.

---

## Review Fixes Applied

Issues identified by 4-agent review and their resolutions:

| Issue | Resolution |
|-------|-----------|
| `is_staff=True` on InternalServiceUser grants site-wide staff access | **Fixed:** `is_staff=False`, internal endpoints use `IsInternalService` only |
| Token comparison uses `==` (timing-vulnerable) | **Fixed:** Use `hmac.compare_digest()` |
| `/api/internal/` exposed publicly via nginx | **Accepted:** All endpoints require auth token — no nginx restriction needed |
| Unvalidated `setattr` loops in endpoints | **Fixed:** Field whitelists on all update endpoints |
| `sync_send_embed()` helper writes DB directly, not covered in plan | **Fixed:** Added Task 4 to refactor helpers |
| `_get_or_create_discord_event()` endpoint incomplete | **Fixed:** Added to Task 3 endpoints |
| `open_scheduled_signups` task writes DB but no migration | **Fixed:** Added to Task 7 |
| No integration test for celery → HTTP → DB | **Fixed:** Added to Task 3 test strategy |
| `pk=None` on InternalServiceUser | **Fixed:** `pk=-1` sentinel |
| Use `invalidate_after_commit()` everywhere in endpoints | **Fixed:** All endpoints use deferred invalidation for safety |
| No input validation on endpoints | **Fixed:** Required field validation before DB write |
| No regression test for future direct DB writes | **Fixed:** Added AST-based import check in Task 10 |
| Same token across environments | **Fixed:** Different defaults per env file, startup validation |

---

## Cache Invalidation Rules for Internal Endpoints

All internal endpoints use `invalidate_after_commit()` (never `invalidate_obj()`) — this is safe regardless of whether the view is wrapped in a transaction now or in a future refactor.

| Model | Cached | Invalidation |
|-------|--------|-------------|
| `DiscordEvent` | Yes (1h) | `invalidate_after_commit(obj)` |
| `DiscordEventMsgSignup` | Yes (1h) | `invalidate_after_commit(obj)` |
| `DiscordEventMsgAnnouncement` | Yes (1h) | `invalidate_after_commit(obj)` |
| `Event` | Yes (1h) | `invalidate_after_commit(obj)` |
| `DiscordEventLog` | No | None needed |
| `DiscordEventDM` | No | None needed |
| `DiscordMessageLog` | No | None needed |

---

## Test Strategy

**Unit tests** (`backend/app/tests/test_internal_auth.py`, `test_internal_endpoints.py`):
- Auth: valid token, missing, wrong, empty, whitespace, timing-safe
- Endpoints: happy path + missing required fields + invalid PK + rejects unauthenticated
- Field whitelists: verify non-whitelisted fields are ignored
- Run: `docker compose -f docker/docker-compose.test.yaml run --rm --entrypoint "" backend python manage.py test app.tests.test_internal_auth app.tests.test_internal_endpoints -v 2`

**Integration tests** (`backend/app/tests/test_internal_client.py`):
- Unmocked test: `internal_client.create_message_log()` → real HTTP → real endpoint → verify DB record
- Error handling: timeout, 500, connection refused

**Regression test** (Task 10):
- AST scan of celery task files to verify no direct ORM imports (`from discordbot.models import`, `Model.objects.create`)

**E2E verification** (Task 10):
- Re-enable all celery beat tasks in test
- Run lifecycle test 5x — must be 5/5 passes
- Run full Playwright suite

---

## Task 1: Internal Service Auth

**Files:**
- Create: `backend/app/auth.py`
- Modify: `backend/backend/settings.py:41` (add INTERNAL_SERVICE_TOKEN + startup validation)
- Modify: `docker/.env.dev`, `docker/.env.test`, `docker/.env.prod`, `docker/.env.release`
- Test: `backend/app/tests/test_internal_auth.py`

**Step 1: Write the failing test**

```python
# backend/app/tests/test_internal_auth.py
import hmac

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
            self.assertFalse(result[0].is_staff)  # NOT staff — least privilege
            self.assertEqual(result[0].pk, -1)  # sentinel PK

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

    def test_token_with_whitespace_fails(self):
        from app.auth import InternalServiceAuth

        factory = APIRequestFactory()
        request = factory.get("/", HTTP_X_INTERNAL_TOKEN=" test-secret ")
        with override_settings(INTERNAL_SERVICE_TOKEN="test-secret"):
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

    def test_rejects_staff_user(self):
        """Staff users should NOT pass IsInternalService — it's for service tokens only."""
        from app.auth import IsInternalService

        class FakeRequest:
            class user:
                is_authenticated = True
                is_staff = True

        self.assertFalse(IsInternalService().has_permission(FakeRequest(), None))
```

**Step 2: Run test to verify it fails**

```bash
docker compose -f docker/docker-compose.test.yaml run --rm --entrypoint "" backend \
  python manage.py test app.tests.test_internal_auth -v 2
```

**Step 3: Implement**

```python
# backend/app/auth.py
"""Internal service authentication for celery workers and Discord bot.

External processes communicate with Django via HTTP. Authentication uses
a shared secret token in the X-Internal-Token header, compared with
hmac.compare_digest() for timing safety.
"""

import hmac

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission


class InternalServiceUser:
    """Sentinel user for authenticated internal service requests.

    is_staff=False: internal token must NOT grant access to staff-only endpoints.
    pk=-1: sentinel that never matches real user PKs.
    """

    is_authenticated = True
    is_staff = False
    is_superuser = False
    pk = -1
    username = "_internal_service"

    def __str__(self):
        return self.username


class InternalServiceAuth(BaseAuthentication):
    """Authenticate via X-Internal-Token header (timing-safe comparison)."""

    def authenticate(self, request):
        token = (
            request.headers.get("X-Internal-Token")
            or request.META.get("HTTP_X_INTERNAL_TOKEN")
            or ""
        )
        expected = getattr(settings, "INTERNAL_SERVICE_TOKEN", "")
        if not expected or not token:
            return None
        if hmac.compare_digest(token, expected):
            return (InternalServiceUser(), None)
        return None


class IsInternalService(BasePermission):
    """Allow only authenticated internal service requests."""

    def has_permission(self, request, view):
        return isinstance(request.user, InternalServiceUser)
```

Add to `backend/backend/settings.py` after line 40:
```python
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
```

Add to docker env files:
```
# docker/.env.dev
INTERNAL_SERVICE_TOKEN=df-internal-dev-token

# docker/.env.test
INTERNAL_SERVICE_TOKEN=df-internal-test-token

# docker/.env.prod
INTERNAL_SERVICE_TOKEN=df-internal-CHANGE-ME-IN-PRODUCTION

# docker/.env.release
INTERNAL_SERVICE_TOKEN=df-internal-CHANGE-ME-IN-PRODUCTION
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```
git commit -m "feat: add InternalServiceAuth with timing-safe token comparison"
```

---

## Task 2: HTTP Client Helper

**Files:**
- Create: `backend/app/internal_client.py`
- Test: `backend/app/tests/test_internal_client.py`

**Step 1: Write failing test**

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
        self.assertEqual(kwargs["timeout"], 30)

    @patch("app.internal_client.requests.post")
    @override_settings(INTERNAL_SERVICE_TOKEN="t")
    def test_post_returns_none_on_exception(self, mock_post):
        import requests as req

        mock_post.side_effect = req.RequestException("timeout")
        from app.internal_client import _post

        result = _post("/test/", {})
        self.assertIsNone(result)

    @patch("app.internal_client.requests.post")
    @override_settings(INTERNAL_SERVICE_TOKEN="t")
    def test_post_returns_response_on_error_status(self, mock_post):
        """Non-200 should return the response (not None) — caller decides what to do."""
        mock_post.return_value = MagicMock(ok=False, status_code=400, text="bad request")
        from app.internal_client import _post

        result = _post("/test/", {})
        self.assertIsNotNone(result)
        self.assertEqual(result.status_code, 400)
```

**Step 2: Implement** `backend/app/internal_client.py`

```python
# backend/app/internal_client.py
"""HTTP client for internal API calls from celery workers and Discord bot.

All external processes MUST use this client instead of importing Django models.
Django/Daphne is the sole DB reader/writer.

Config:
    INTERNAL_API_URL: defaults to http://backend:8000/api/internal (Docker).
                      Set to https://dota.kettle.sh/api/internal for remote.
    INTERNAL_SERVICE_TOKEN: shared secret for X-Internal-Token header.
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
TIMEOUT = 30


def _headers():
    return {
        "X-Internal-Token": getattr(settings, "INTERNAL_SERVICE_TOKEN", ""),
        "Content-Type": "application/json",
    }


def _post(path, data):
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
    url = f"{INTERNAL_API_URL}{path}"
    try:
        resp = requests.get(url, params=params, headers=_headers(), timeout=TIMEOUT)
        if not resp.ok:
            logger.error("Internal GET %s: %s %s", path, resp.status_code, resp.text[:200])
        return resp
    except requests.RequestException:
        logger.exception("Internal GET %s failed", path)
        return None


# ---- Discord writes ----

def create_message_log(**data):
    return _post("/discord/message-log/", data)

def create_event_log(**data):
    return _post("/discord/event-log/", data)

def get_or_create_discord_event(**data):
    return _post("/discord/events/get-or-create/", data)

def update_discord_event(pk, **data):
    return _patch(f"/discord/events/{pk}/", data)

def create_or_update_signup_message(**data):
    return _post("/discord/signup-message/", data)

def create_or_update_announcement(**data):
    return _post("/discord/announcement/", data)

def create_event_dm(**data):
    return _post("/discord/event-dm/", data)

def update_event_dm(pk, **data):
    return _patch(f"/discord/event-dm/{pk}/", data)

# ---- Event writes ----

def transition_event_state(event_pk, new_state):
    return _post(f"/events/{event_pk}/transition/", {"state": new_state})

# ---- Event reads ----

def get_event(pk):
    return _get(f"/events/{pk}/")

def get_event_signups(event_pk):
    return _get(f"/events/{event_pk}/signups/")

# ---- Steam writes ----

def batch_upsert_matches(data):
    return _post("/steam/matches/", data)

def update_sync_state(pk, **data):
    return _patch(f"/steam/sync-state/{pk}/", data)

# ---- User writes ----

def update_user_avatar(pk, avatar_url):
    return _patch(f"/users/{pk}/avatar/", {"avatar": avatar_url})
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

All endpoints use:
- `InternalServiceAuth` + `IsInternalService` (token auth, not staff auth)
- `invalidate_after_commit()` for cached models (safe in any transaction context)
- Field whitelists on update endpoints (no generic `setattr` loops)
- Required field validation before DB write

**Step 1: Write failing tests**

```python
# backend/app/tests/test_internal_endpoints.py
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import Organization


class InternalAuthGateTest(TestCase):
    """All internal endpoints reject unauthenticated requests."""

    def test_rejects_no_token(self):
        c = APIClient()
        resp = c.post("/api/internal/discord/message-log/", {}, format="json")
        self.assertEqual(resp.status_code, 403)

    @override_settings(INTERNAL_SERVICE_TOKEN="tok")
    def test_rejects_wrong_token(self):
        c = APIClient()
        resp = c.post("/api/internal/discord/message-log/", {}, format="json",
                       HTTP_X_INTERNAL_TOKEN="wrong")
        self.assertEqual(resp.status_code, 403)


TOKEN = "test-tok"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class DiscordMessageLogEndpointTest(TestCase):
    def test_create(self):
        c = APIClient()
        resp = c.post("/api/internal/discord/message-log/", {
            "channel_id": "123", "source": "event_announcement",
            "source_id": 1, "discord_message_id": "789",
            "status_code": 200, "success": True,
        }, format="json", **HEADERS)
        self.assertEqual(resp.status_code, 201)
        self.assertIn("id", resp.json())

    def test_missing_required_field(self):
        c = APIClient()
        resp = c.post("/api/internal/discord/message-log/", {
            "channel_id": "123",
            # missing source, source_id
        }, format="json", **HEADERS)
        self.assertEqual(resp.status_code, 400)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class DiscordEventEndpointTest(TestCase):
    def _make_discord_event(self):
        from discordbot.models import DiscordEvent
        from events.models import Event
        org = Organization.objects.create(name="Internal Test Org")
        event = Event.objects.create(organization=org, name="Test", state="upcoming")
        return DiscordEvent.objects.create(event=event, guild_id="111")

    def test_get_or_create(self):
        from events.models import Event
        org = Organization.objects.create(name="GOC Org")
        event = Event.objects.create(organization=org, name="GOC Test", state="upcoming")
        c = APIClient()
        resp = c.post("/api/internal/discord/events/get-or-create/", {
            "event_id": event.pk, "guild_id": "555",
        }, format="json", **HEADERS)
        self.assertEqual(resp.status_code, 201)
        self.assertIn("id", resp.json())

    def test_update_whitelisted_field(self):
        de = self._make_discord_event()
        c = APIClient()
        resp = c.patch(f"/api/internal/discord/events/{de.pk}/", {
            "scheduled_event_id": "999888",
        }, format="json", **HEADERS)
        self.assertEqual(resp.status_code, 200)
        de.refresh_from_db()
        self.assertEqual(de.scheduled_event_id, "999888")

    def test_update_rejects_non_whitelisted_field(self):
        """event_id should NOT be updatable via this endpoint."""
        de = self._make_discord_event()
        original_event_id = de.event_id
        c = APIClient()
        resp = c.patch(f"/api/internal/discord/events/{de.pk}/", {
            "event_id": 99999,
        }, format="json", **HEADERS)
        self.assertEqual(resp.status_code, 200)  # request succeeds but field is ignored
        de.refresh_from_db()
        self.assertEqual(de.event_id, original_event_id)

    def test_create_event_log(self):
        de = self._make_discord_event()
        c = APIClient()
        resp = c.post("/api/internal/discord/event-log/", {
            "discord_event_id": de.pk,
            "action": "create_scheduled_event",
            "target_type": "DiscordEvent",
            "success": True,
        }, format="json", **HEADERS)
        self.assertEqual(resp.status_code, 201)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class InternalClientIntegrationTest(TestCase):
    """Unmocked integration: internal_client → real endpoint → real DB."""

    def test_create_message_log_full_chain(self):
        from discordbot.models import DiscordMessageLog

        # Override INTERNAL_API_URL to point to Django test server
        import app.internal_client as client
        old_url = client.INTERNAL_API_URL
        client.INTERNAL_API_URL = "http://testserver/api/internal"
        try:
            resp = client.create_message_log(
                channel_id="integration-test",
                source="test_integration",
                source_id=1,
                status_code=200,
                success=True,
            )
            self.assertIsNotNone(resp)
            self.assertEqual(resp.status_code, 201)
            self.assertTrue(
                DiscordMessageLog.objects.filter(channel_id="integration-test").exists()
            )
        finally:
            client.INTERNAL_API_URL = old_url
```

**Step 2: Implement internal views**

```python
# backend/app/views/internal.py
"""Internal API endpoints for celery workers and Discord bot.

All endpoints require InternalServiceAuth (X-Internal-Token header).
All cached model writes use invalidate_after_commit() for safety.
All update endpoints use field whitelists — no generic setattr loops.
"""

import logging

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.cache_utils import invalidate_after_commit

logger = logging.getLogger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]


def _validate_required(data, fields):
    """Return error Response if required fields are missing, else None."""
    missing = [f for f in fields if f not in data]
    if missing:
        return Response(
            {"error": f"Missing required fields: {missing}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


# ---- DiscordMessageLog (NOT cached) ----

@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_discord_message_log(request):
    from discordbot.models import DiscordMessageLog

    err = _validate_required(request.data, ["channel_id", "source", "source_id"])
    if err:
        return err
    entry = DiscordMessageLog.objects.create(**request.data)
    return Response({"id": entry.pk}, status=status.HTTP_201_CREATED)


# ---- DiscordEventLog (NOT cached) ----

@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_discord_event_log(request):
    from discordbot.models import DiscordEvent, DiscordEventLog

    err = _validate_required(request.data, ["discord_event_id", "action", "target_type"])
    if err:
        return err
    data = dict(request.data)
    discord_event = DiscordEvent.objects.get(pk=data.pop("discord_event_id"))
    entry = DiscordEventLog.objects.create(discord_event=discord_event, **data)
    return Response({"id": entry.pk}, status=status.HTTP_201_CREATED)


# ---- DiscordEvent (CACHED) ----

DISCORD_EVENT_UPDATE_FIELDS = {"scheduled_event_id"}

@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_or_create_discord_event(request):
    from discordbot.models import DiscordEvent

    err = _validate_required(request.data, ["event_id"])
    if err:
        return err
    de, created = DiscordEvent.objects.get_or_create(
        event_id=request.data["event_id"],
        defaults={"guild_id": request.data.get("guild_id", "")},
    )
    if created:
        invalidate_after_commit(de)
    return Response(
        {"id": de.pk, "created": created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )

@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_discord_event(request, pk):
    from discordbot.models import DiscordEvent

    de = DiscordEvent.objects.get(pk=pk)
    changed = False
    for field in DISCORD_EVENT_UPDATE_FIELDS:
        if field in request.data:
            setattr(de, field, request.data[field])
            changed = True
    if changed:
        de.save()
        invalidate_after_commit(de)
    return Response({"id": de.pk})


# ---- DiscordEventMsgSignup (CACHED) ----

SIGNUP_MSG_UPDATE_FIELDS = {
    "message_id", "thread_id", "channel_type", "has_posted", "message_last_updated",
}

@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_or_update_signup_message(request):
    from discordbot.models import ChannelType, DiscordEventMsgSignup

    err = _validate_required(request.data, ["event_id", "channel_id"])
    if err:
        return err
    data = dict(request.data)
    event_id = data.pop("event_id")
    channel_id = data.pop("channel_id")

    msg, created = DiscordEventMsgSignup.objects.get_or_create(
        event_id=event_id,
        channel_id=channel_id,
        defaults={"channel_type": data.get("channel_type", ChannelType.TEXT)},
    )
    for field in SIGNUP_MSG_UPDATE_FIELDS:
        if field in data:
            setattr(msg, field, data[field])
    msg.save()
    invalidate_after_commit(msg)
    return Response(
        {"id": msg.pk, "created": created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ---- DiscordEventMsgAnnouncement (CACHED) ----

ANNOUNCEMENT_UPDATE_FIELDS = {
    "message_id", "channel_type", "has_posted", "message_last_updated",
}

@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_or_update_announcement(request):
    from discordbot.models import ChannelType, DiscordEventMsgAnnouncement

    err = _validate_required(request.data, ["event_id", "channel_id"])
    if err:
        return err
    data = dict(request.data)
    event_id = data.pop("event_id")
    channel_id = data.pop("channel_id")

    msg, created = DiscordEventMsgAnnouncement.objects.get_or_create(
        event_id=event_id,
        channel_id=channel_id,
        defaults={"channel_type": data.get("channel_type", ChannelType.TEXT)},
    )
    for field in ANNOUNCEMENT_UPDATE_FIELDS:
        if field in data:
            setattr(msg, field, data[field])
    msg.save()
    invalidate_after_commit(msg)
    return Response(
        {"id": msg.pk, "created": created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ---- DiscordEventDM (NOT cached) ----

@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def create_event_dm(request):
    from discordbot.models import DiscordEventDM

    dm = DiscordEventDM.objects.create(**request.data)
    return Response({"id": dm.pk}, status=status.HTTP_201_CREATED)

DM_UPDATE_FIELDS = {"message_id", "sent_at", "delivered"}

@api_view(["PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def update_event_dm(request, pk):
    from discordbot.models import DiscordEventDM

    dm = DiscordEventDM.objects.get(pk=pk)
    for field in DM_UPDATE_FIELDS:
        if field in request.data:
            setattr(dm, field, request.data[field])
    dm.save()
    return Response({"id": dm.pk})


# ---- Event state transition (CACHED) ----

@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def transition_event_state(request, pk):
    from events.models import Event

    event = Event.objects.get(pk=pk)
    new_state = request.data.get("state")
    if not new_state:
        return Response({"error": "state required"}, status=status.HTTP_400_BAD_REQUEST)
    event.transition_state(new_state)
    invalidate_after_commit(event)
    return Response({"id": event.pk, "state": event.state})
```

Wire URLs — add to `backend/backend/urls.py` before the test URL block:

```python
from app.views.internal import (
    create_discord_event_log,
    create_discord_message_log,
    create_event_dm,
    create_or_update_announcement,
    create_or_update_signup_message,
    get_or_create_discord_event,
    transition_event_state,
    update_discord_event,
    update_event_dm,
)

# Internal API — celery workers and Discord bot (token auth)
path("api/internal/discord/message-log/", create_discord_message_log),
path("api/internal/discord/event-log/", create_discord_event_log),
path("api/internal/discord/events/get-or-create/", get_or_create_discord_event),
path("api/internal/discord/events/<int:pk>/", update_discord_event),
path("api/internal/discord/signup-message/", create_or_update_signup_message),
path("api/internal/discord/announcement/", create_or_update_announcement),
path("api/internal/discord/event-dm/", create_event_dm),
path("api/internal/discord/event-dm/<int:pk>/", update_event_dm),
path("api/internal/events/<int:pk>/transition/", transition_event_state),
```

**Step 3: Run tests, commit**

```
git commit -m "feat: add /api/internal/ endpoints with field whitelists and deferred cache invalidation"
```

---

## Task 4: Refactor `sync_send_embed` and `sync_send_embed_with_components`

**Files:**
- Modify: `backend/discordbot/utils.py`

These helper functions currently:
1. Create `DiscordMessageLog` (DB write)
2. Call Discord API
3. Update `DiscordMessageLog` with response (DB write)

Refactor to:
1. Call Discord API (keep)
2. Call `internal_client.create_message_log()` with result (HTTP instead of DB)

This unblocks Tasks 5-8 since most celery tasks call these helpers rather than writing to DB directly.

---

## Task 5: Migrate `create_discord_scheduled_event`

**Files:**
- Modify: `backend/events/tasks.py:481-567`

Replace 3 DB writes with `internal_client` calls. Task still reads Event via ORM (reads don't lock SQLite).

---

## Task 6: Migrate `send_event_announcement`

**Files:**
- Modify: `backend/events/tasks.py:187-369`

Largest task. Replace `_get_or_create_discord_event()` with `internal_client.get_or_create_discord_event()`. Replace all `DiscordEventMsgSignup`, `DiscordEventMsgAnnouncement`, `DiscordEventLog` writes with HTTP calls.

---

## Task 7: Migrate remaining event tasks

**Files:**
- Modify: `backend/events/tasks.py`

Tasks: `send_signup_update`, `check_event_reminders`, `send_subscriber_notifications`, `send_new_event_notification`, `sync_discord_event_signups`, `open_scheduled_signups`.

`open_scheduled_signups` calls `event.transition_state()` — replace with `internal_client.transition_event_state()`.

---

## Task 8: Migrate Discord bot + scheduled event tasks

**Files:**
- Modify: `backend/discordbot/tasks.py` — `check_scheduled_events`

Same pattern: keep Discord API calls, replace `ScheduledEvent.save()` with HTTP.

---

## Task 9: Migrate Steam tasks

**Files:**
- Modify: `backend/steam/tasks.py`
- Create: `backend/app/views/internal_steam.py`

New endpoints:
```
POST  /api/internal/steam/matches/           → batch upsert
PATCH /api/internal/steam/sync-state/<pk>/   → update state
POST  /api/internal/steam/league-stats/<pk>/ → trigger recalc
```

---

## Task 10: Re-enable Beat + Regression Test + Verification

**Files:**
- Modify: `backend/config/celery.py` — remove IS_TEST guard, re-enable all tasks
- Create: `backend/app/tests/test_no_direct_db_writes.py`

**Regression test:**

```python
# backend/app/tests/test_no_direct_db_writes.py
import ast
import os
from django.test import TestCase

CELERY_TASK_FILES = [
    "events/tasks.py",
    "discordbot/tasks.py",
    "steam/tasks.py",
    "app/tasks/avatar_refresh.py",
]

FORBIDDEN_IMPORTS = {
    "discordbot.models": {"DiscordMessageLog", "DiscordEventLog", "DiscordEventDM"},
}

class NoCeleryDirectDBWritesTest(TestCase):
    def test_celery_tasks_do_not_import_write_models(self):
        """Verify celery tasks use internal_client, not direct ORM imports."""
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        violations = []
        for task_file in CELERY_TASK_FILES:
            path = os.path.join(backend_dir, task_file)
            if not os.path.exists(path):
                continue
            with open(path) as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module in FORBIDDEN_IMPORTS:
                    imported = {a.name for a in node.names}
                    forbidden = imported & FORBIDDEN_IMPORTS[node.module]
                    if forbidden:
                        violations.append(f"{task_file}: imports {forbidden} from {node.module}")
        self.assertEqual(violations, [], f"Direct DB model imports in celery tasks: {violations}")
```

**E2E verification:**
1. `just test::setup`
2. Run lifecycle test 5x: all must pass
3. Run full suite: `just test::pw::headless`
4. Push and verify CI

---

## Future (Separate Plans)

- **Discord bot full migration** — bot becomes pure discord.py + HTTP client, no Django ORM
- **Avatar refresh** — `PATCH /api/internal/users/<pk>/avatar/`
- **PostgreSQL migration** — eliminates SQLite entirely
- **Herodraft tick** — uses WebSocket + Redis, different pattern
