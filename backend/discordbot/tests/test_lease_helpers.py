"""End-to-end tests for the claim/finalize lease helpers.

Uses Django's TestCase in-process ORM — the worker-side helpers POST over
HTTP, but in tests we exercise the underlying Django views via an APIClient
authenticated with the same X-Internal-Token header that workers use.

InternalServiceAuth requires BOTH (a) the X-Internal-Token header to match
settings.INTERNAL_SERVICE_TOKEN AND (b) the request IP to be in the
allowlist. We pin a known token via @override_settings so the test container
(where INTERNAL_SERVICE_TOKEN is unset by default) can authenticate; the
APIClient request IP defaults to 127.0.0.1 which is in DEFAULT_ALLOWED_IPS.
"""

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from discordbot.models import DiscordMessageLog


CLAIM_PAYLOAD = dict(channel_id="ch_1", embed_data={"title": "test"})
INTERNAL_TOKEN = "test-internal-token"


def _internal_client():
    client = APIClient()
    client.credentials(HTTP_X_INTERNAL_TOKEN=INTERNAL_TOKEN)
    return client


@override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN)
class LeaseEndpointsTest(TestCase):
    def test_claim_returns_201_with_log_id(self):
        client = _internal_client()
        resp = client.post(
            "/api/internal/discord/message-log/claim/",
            data={"source": "event_announcement", "source_id": 10, **CLAIM_PAYLOAD},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        log_id = resp.json()["id"]
        row = DiscordMessageLog.objects.get(pk=log_id)
        self.assertIsNone(row.success)
        self.assertIsNotNone(row.claimed_at)
        self.assertEqual(row.channel_id, "ch_1")
        self.assertEqual(row.embed_data, {"title": "test"})

    def test_claim_returns_409_when_pending_lease_held(self):
        DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=11,
            success=None,
            claimed_at=timezone.now(),
            channel_id="ch_1",
            embed_data={"title": "prior"},
        )
        client = _internal_client()
        resp = client.post(
            "/api/internal/discord/message-log/claim/",
            data={"source": "event_announcement", "source_id": 11, **CLAIM_PAYLOAD},
            format="json",
        )
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_claim_returns_409_when_already_succeeded(self):
        DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=12,
            success=True,
            channel_id="ch_1",
            embed_data={"title": "prior"},
        )
        client = _internal_client()
        resp = client.post(
            "/api/internal/discord/message-log/claim/",
            data={"source": "event_announcement", "source_id": 12, **CLAIM_PAYLOAD},
            format="json",
        )
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_claim_succeeds_after_failed_send(self):
        DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=13,
            success=False,
            channel_id="ch_1",
            embed_data={"title": "prior"},
        )
        client = _internal_client()
        resp = client.post(
            "/api/internal/discord/message-log/claim/",
            data={"source": "event_announcement", "source_id": 13, **CLAIM_PAYLOAD},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_finalize_marks_success_true(self):
        client = _internal_client()
        claim = client.post(
            "/api/internal/discord/message-log/claim/",
            data={"source": "event_announcement", "source_id": 14, **CLAIM_PAYLOAD},
            format="json",
        )
        log_id = claim.json()["id"]
        resp = client.post(
            f"/api/internal/discord/message-log/{log_id}/finalize/",
            data={"success": True, "discord_message_id": "msg_1"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        row = DiscordMessageLog.objects.get(pk=log_id)
        self.assertTrue(row.success)
        self.assertEqual(row.discord_message_id, "msg_1")

    def test_finalize_marks_success_false(self):
        client = _internal_client()
        claim = client.post(
            "/api/internal/discord/message-log/claim/",
            data={"source": "event_announcement", "source_id": 15, **CLAIM_PAYLOAD},
            format="json",
        )
        log_id = claim.json()["id"]
        resp = client.post(
            f"/api/internal/discord/message-log/{log_id}/finalize/",
            data={"success": False, "response_data": {"error": "HTTP 500"}},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        row = DiscordMessageLog.objects.get(pk=log_id)
        self.assertFalse(row.success)

    def test_finalize_returns_410_when_row_swept(self):
        client = _internal_client()
        # log_id 99999 doesn't exist (sweeper deleted the row)
        resp = client.post(
            "/api/internal/discord/message-log/99999/finalize/",
            data={"success": True, "discord_message_id": "msg_late"},
            format="json",
        )
        self.assertEqual(resp.status_code, 410, resp.content)


@override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN)
class ClearEventSignupStateEndpointTest(TestCase):
    """Verify the new POST /discord/signup-message/clear/ route.

    This is the contract test the orphaned-recovery shim relies on — proves
    the HTTP path, payload shape, auth, and ORM side effects are correct.
    The worker-side recovery test exercises the worker logic through the
    shim; this test exercises the endpoint independently of the shim.
    """

    def _seed_dedup_state(self, event_id):
        from app.models import Organization
        from discordbot.models import (
            ChannelType,
            DiscordEventMsgSignup,
            DiscordMessageLog,
        )
        from events.models import Event

        org = Organization.objects.create(name=f"Clear Test Org {event_id}")
        Event.objects.create(
            pk=event_id,
            organization=org,
            name="Clear Test Event",
            state="signups_open",
            scheduled_at=timezone.now(),
        )
        DiscordEventMsgSignup.objects.create(
            event_id=event_id,
            channel_id="ch_clear",
            channel_type=ChannelType.TEXT,
            has_posted=True,
            message_id="ghost_msg",
        )
        DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=event_id,
            success=True,
            channel_id="ch_clear",
            embed_data={"title": "seed"},
        )

    def test_clear_flips_both_dedup_gates(self):
        from discordbot.models import DiscordEventMsgSignup, DiscordMessageLog

        self._seed_dedup_state(event_id=201)
        client = _internal_client()
        resp = client.post(
            "/api/internal/discord/signup-message/clear/",
            data={"event_id": 201},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["event_id"], 201)
        self.assertEqual(body["signup_rows_cleared"], 1)
        self.assertEqual(body["message_log_rows_cleared"], 1)

        self.assertFalse(
            DiscordEventMsgSignup.objects.filter(
                event_id=201, has_posted=True
            ).exists()
        )
        self.assertFalse(
            DiscordMessageLog.objects.filter(
                source="event_announcement", source_id=201, success=True
            ).exists()
        )

    def test_clear_requires_event_id(self):
        client = _internal_client()
        resp = client.post(
            "/api/internal/discord/signup-message/clear/",
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_clear_is_noop_when_nothing_to_clear(self):
        """Idempotent: calling clear with no matching rows returns 200 + zero
        counts, so the auto-recovery path can call it safely even if a
        concurrent run already cleared the state."""
        client = _internal_client()
        resp = client.post(
            "/api/internal/discord/signup-message/clear/",
            data={"event_id": 99999},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["signup_rows_cleared"], 0)
        self.assertEqual(body["message_log_rows_cleared"], 0)
