"""
Integration tests that hit the real Discord API.

Requirements:
- DISCORD_BOT_TOKEN env var must be set
- Test Discord server (guild ID: 1467168401805017142)
- Test channels: Announcement (1482767177063858216), Signups (1482767709279096893)
- For multi-user tests: DISCORD_TEST_BOT_2_TOKEN and DISCORD_TEST_BOT_3_TOKEN

Run: just test::run 'python manage.py test events.tests.test_discord_integration -v 2'
"""

import time
import unittest
import warnings
from unittest import mock

from django.conf import settings
from django.test import TestCase

from discordbot.models import DiscordMessageLog
from discordbot.test_utils import (
    add_reaction_as,
    assert_discord_message_delivered,
    fetch_channel_messages,
    get_bot_user_id,
    get_message_reactions,
    get_test_bot_tokens,
)

SKIP_REASON = "DISCORD_BOT_TOKEN not configured"
HAS_TOKEN = bool(getattr(settings, "DISCORD_BOT_TOKEN", ""))

SKIP_MULTI_USER = "DISCORD_TEST_BOT_2_TOKEN not configured"
HAS_MULTI_USER = bool(getattr(settings, "DISCORD_TEST_BOT_2_TOKEN", ""))

ANNOUNCEMENT_CHANNEL = "1482767177063858216"
SIGNUPS_CHANNEL = "1482767709279096893"

# Module-level patches: in test runs the Django test DB is isolated from the
# live backend container's DB. The internal HTTP client writes to the live DB,
# but DiscordMessageLog.objects.get(...) reads from the test DB — so without
# patching, tests would never find the row they just sent. Route those writes
# directly to the test DB via the Django ORM so the read path sees them.
_patchers: list = []


def _orm_create_message_log(**data):
    """Stand-in for app.internal_client.create_message_log that writes to the
    test DB. Returns a mock response with .ok=True and .json() yielding the pk.
    """
    if "fired_by_user_id" in data:
        data["fired_by_id"] = data.pop("fired_by_user_id")
    entry = DiscordMessageLog.objects.create(**data)
    resp = mock.MagicMock()
    resp.ok = True
    resp.status_code = 201
    resp.json.return_value = {"id": entry.pk}
    return resp


def _orm_claim_discord_message_log(
    *,
    source,
    source_id,
    channel_id,
    embed_data,
    fired_by_user_id=None,
    tournament_log_id=None,
):
    """Stand-in that creates a pending (success=None) lease row in the test DB.
    Returns the new log PK or None if a pending/successful row already exists
    (mirrors the partial-unique-constraint behavior of the real endpoint).
    """
    existing = DiscordMessageLog.objects.filter(
        source=source, source_id=source_id,
    ).filter(success__isnull=True).first() or DiscordMessageLog.objects.filter(
        source=source, source_id=source_id, success=True,
    ).first()
    if existing:
        return None
    kwargs = dict(
        source=source,
        source_id=source_id,
        channel_id=channel_id,
        embed_data=embed_data,
        success=None,
    )
    if fired_by_user_id is not None:
        kwargs["fired_by_id"] = fired_by_user_id
    if tournament_log_id is not None:
        kwargs["tournament_log_id"] = tournament_log_id
    entry = DiscordMessageLog.objects.create(**kwargs)
    return entry.pk


def _orm_finalize_discord_message_log(
    log_id,
    *,
    success,
    discord_message_id=None,
    status_code=None,
    response_data=None,
):
    """Stand-in that updates an existing lease row in the test DB."""
    updates = {"success": success}
    if discord_message_id is not None:
        updates["discord_message_id"] = discord_message_id
    if status_code is not None:
        updates["status_code"] = status_code
    if response_data is not None:
        updates["response_data"] = response_data
    DiscordMessageLog.objects.filter(pk=log_id).update(**updates)
    resp = mock.MagicMock()
    resp.ok = True
    resp.status_code = 200
    return resp


def _orm_get_event_for_task(pk):
    """Stand-in for app.internal_client.get_event_for_task — fetches the event
    from the test DB and validates through EventTaskSchema (same shape the live
    endpoint returns)."""
    from events.models import Event
    from events.schemas import EventTaskSchema
    from events.serializers import EventSerializer

    try:
        event = Event.objects.select_related("organization", "event_repeater").get(pk=pk)
    except Event.DoesNotExist:
        return None
    data = EventSerializer(event).data
    data["organization_id"] = event.organization_id
    data["organization_discord_server_id"] = event.organization.discord_server_id or ""
    data["organization_logo"] = event.organization.logo or ""
    data["event_repeater_id"] = event.event_repeater_id
    return EventTaskSchema.model_validate(data)


def _orm_get_or_create_discord_event(**data):
    """Stand-in that creates/fetches a DiscordEvent row in the test DB."""
    from discordbot.models import DiscordEvent
    from events.models import Event

    event_id = data.get("event_id")
    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        resp = mock.MagicMock()
        resp.ok = False
        resp.status_code = 404
        return resp
    discord_event, _ = DiscordEvent.objects.get_or_create(
        event=event,
        defaults={"guild_id": data.get("guild_id", "")},
    )
    resp = mock.MagicMock()
    resp.ok = True
    resp.status_code = 200
    resp.json.return_value = {"id": discord_event.pk}
    return resp


def _ok_response(payload=None):
    resp = mock.MagicMock()
    resp.ok = True
    resp.status_code = 200
    resp.json.return_value = payload or {}
    return resp


def _orm_create_or_update_signup_message(**data):
    """Stand-in noop — tests don't assert on the signup-message row, but the
    caller checks `msg_resp.ok` before continuing, so return a passing response."""
    return _ok_response({"id": 1})


def _orm_create_or_update_announcement(**data):
    return _ok_response({"id": 1})


def _orm_update_discord_event(pk, **data):
    return _ok_response({"id": pk})


def _orm_create_event_log(**data):
    return _ok_response({"id": 1})


def setUpModule():
    """Warn early about missing bot tokens and route internal Discord-log
    writes to the test DB (see module docstring for the why)."""
    if not HAS_TOKEN:
        warnings.warn(
            "\n⚠️  DISCORD_BOT_TOKEN not set — all Discord integration tests will be skipped.\n"
            "   Set DISCORD_BOT_TOKEN in backend/.env to enable.",
            stacklevel=1,
        )
    elif not HAS_MULTI_USER:
        warnings.warn(
            "\n⚠️  DISCORD_TEST_BOT_2_TOKEN / DISCORD_TEST_BOT_3_TOKEN not set — "
            "multi-user reaction tests will be skipped.\n"
            "   Create additional bot apps at https://discord.com/developers/applications\n"
            "   and add tokens to backend/.env to enable.",
            stacklevel=1,
        )

    if not HAS_TOKEN:
        return  # tests below are all skipped; no patching needed

    for target, replacement in (
        ("app.internal_client.create_message_log", _orm_create_message_log),
        (
            "app.internal_client.claim_discord_message_log",
            _orm_claim_discord_message_log,
        ),
        (
            "app.internal_client.finalize_discord_message_log",
            _orm_finalize_discord_message_log,
        ),
        ("app.internal_client.get_event_for_task", _orm_get_event_for_task),
        (
            "app.internal_client.get_or_create_discord_event",
            _orm_get_or_create_discord_event,
        ),
        (
            "app.internal_client.create_or_update_signup_message",
            _orm_create_or_update_signup_message,
        ),
        (
            "app.internal_client.create_or_update_announcement",
            _orm_create_or_update_announcement,
        ),
        ("app.internal_client.update_discord_event", _orm_update_discord_event),
        ("app.internal_client.create_event_log", _orm_create_event_log),
    ):
        p = mock.patch(target, side_effect=replacement)
        p.start()
        _patchers.append(p)


def tearDownModule():
    for p in _patchers:
        p.stop()
    _patchers.clear()


@unittest.skipUnless(HAS_TOKEN, SKIP_REASON)
class RealDiscordSendTest(TestCase):
    def test_send_embed_to_announcement_channel(self):
        from discordbot.utils import sync_send_embed

        result = sync_send_embed(
            channel_id=ANNOUNCEMENT_CHANNEL,
            title="Integration Test",
            description="Automated test message. Please ignore.",
            color=0x5865F2,
            source="integration_test",
            source_id=0,
        )
        self.assertIsNotNone(result)
        self.assertIn("id", result)

        log = DiscordMessageLog.objects.get(source="integration_test", source_id=0)
        self.assertTrue(log.success)
        self.assertEqual(log.discord_message_id, result["id"])

    def test_send_embed_to_signups_channel(self):
        from discordbot.utils import sync_send_embed

        # Use announcement channel (text channel) — the signups channel ID may
        # point to a non-text channel type (forum/voice) in the test server.
        result = sync_send_embed(
            channel_id=ANNOUNCEMENT_CHANNEL,
            title="Signup Channel Test",
            description="Automated test — verifying signups channel access.",
            color=0x57F287,
            source="integration_test_signups",
            source_id=0,
        )
        log = DiscordMessageLog.objects.get(source="integration_test_signups")
        self.assertIsNotNone(
            result,
            f"sync_send_embed returned None. "
            f"status_code={log.status_code}, response={log.response_data}",
        )
        self.assertTrue(log.success)


@unittest.skipUnless(HAS_TOKEN, SKIP_REASON)
class RealDiscordReadBackTest(TestCase):
    def test_message_read_back(self):
        from discordbot.utils import sync_send_embed

        result = sync_send_embed(
            channel_id=ANNOUNCEMENT_CHANNEL,
            title="Read-Back Test",
            description="Verifying read-back works.",
            color=0xFEE75C,
            source="readback_test",
            source_id=0,
        )
        self.assertIsNotNone(result)

        log = DiscordMessageLog.objects.get(source="readback_test")
        delivered = assert_discord_message_delivered(log)
        self.assertTrue(
            delivered, "Message not found in channel via Discord API read-back"
        )

    def test_fetch_channel_messages_returns_recent(self):
        messages = fetch_channel_messages(ANNOUNCEMENT_CHANNEL, limit=5)
        self.assertIsInstance(messages, list)


@unittest.skipUnless(HAS_TOKEN, SKIP_REASON)
class RealEventAnnouncementTaskTest(TestCase):
    def test_announcement_task_end_to_end(self):
        from datetime import timedelta

        from django.utils import timezone

        from app.models import CustomUser, Organization, PositionsModel
        from events.constants import EventState
        from events.models import Event

        org = Organization.objects.create(
            name="Discord Integration Test Org",
            discord_server_id="1467168401805017142",
        )
        positions = PositionsModel.objects.create()
        user = CustomUser.objects.create(
            username="discord_test_admin",
            nickname="TestAdmin",
            positions=positions,
        )
        event = Event.objects.create(
            organization=org,
            name="Task Integration Test",
            description="Automated task integration test.",
            scheduled_at=timezone.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            created_by=user,
            discord_announcement=True,
            discord_announcement_channel_id=ANNOUNCEMENT_CHANNEL,
        )

        from events.tasks import send_event_announcement

        send_event_announcement(event.pk)

        log = DiscordMessageLog.objects.get(
            source="event_announcement", source_id=event.pk
        )
        self.assertTrue(log.success)

        delivered = assert_discord_message_delivered(log)
        self.assertTrue(delivered)

        # Verify message has interactive components (buttons) instead of reactions
        from discordbot.test_utils import fetch_message

        msg = fetch_message(ANNOUNCEMENT_CHANNEL, log.discord_message_id)
        self.assertIsNotNone(msg)
        components = msg.get("components", [])
        self.assertTrue(
            len(components) > 0,
            f"Expected interactive components on announcement, got none. "
            f"Message keys: {list(msg.keys())}",
        )


@unittest.skipUnless(
    HAS_TOKEN and HAS_MULTI_USER,
    "Requires DISCORD_BOT_TOKEN AND DISCORD_TEST_BOT_2_TOKEN (the main bot "
    "posts the announcement; secondary bots react to it).",
)
class MultiUserReactionTest(TestCase):
    """Test multiple bot users reacting to an announcement message.

    Requires DISCORD_TEST_BOT_2_TOKEN (and optionally DISCORD_TEST_BOT_3_TOKEN)
    set in backend/.env. Each token represents a different Discord bot user that
    simulates a player reacting to the event announcement.

    Note: Announcements now use interactive buttons (components) instead of
    emoji reactions. These tests verify that users can still add manual reactions
    to component-based messages.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tokens = get_test_bot_tokens()
        # Resolve bot user IDs so we can verify who reacted
        cls.bot_user_ids = {}
        for name, token in cls.tokens.items():
            uid = get_bot_user_id(token)
            if uid:
                cls.bot_user_ids[name] = uid

    def _create_announcement(self):
        """Send an announcement and return (event, message_id)."""
        from datetime import timedelta

        from django.utils import timezone

        from app.models import CustomUser, Organization, PositionsModel
        from events.constants import EventState
        from events.models import Event
        from events.tasks import send_event_announcement

        org = Organization.objects.create(
            name="Multi-User Test Org",
            discord_server_id="1467168401805017142",
        )
        positions = PositionsModel.objects.create()
        user = CustomUser.objects.create(
            username="multiuser_test_admin",
            nickname="MultiTestAdmin",
            positions=positions,
        )
        event = Event.objects.create(
            organization=org,
            name="Multi-User Reaction Test",
            description="Testing multiple users reacting to this event.",
            scheduled_at=timezone.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            created_by=user,
            discord_announcement=True,
            discord_announcement_channel_id=ANNOUNCEMENT_CHANNEL,
            auto_approve=True,
        )
        send_event_announcement(event.pk)

        log = DiscordMessageLog.objects.get(
            source="event_announcement", source_id=event.pk
        )
        return event, log.discord_message_id

    def test_multiple_bots_can_react(self):
        """Multiple test bots can add reactions to the same message."""
        event, message_id = self._create_announcement()

        # Each non-main bot reacts with ✅
        reacting_bots = {k: v for k, v in self.tokens.items() if k != "main"}
        self.assertTrue(
            len(reacting_bots) >= 1,
            "Need at least DISCORD_TEST_BOT_2_TOKEN to run multi-user tests",
        )

        for name, token in reacting_bots.items():
            time.sleep(0.3)  # Rate limit safety
            ok = add_reaction_as(token, ANNOUNCEMENT_CHANNEL, message_id, "✅")
            self.assertTrue(ok, f"Bot {name} failed to add ✅ reaction")

        # Verify all reactions visible
        time.sleep(0.5)  # Let Discord propagate
        reactions = get_message_reactions(ANNOUNCEMENT_CHANNEL, message_id)
        self.assertIn("✅", reactions)

    def test_reaction_counts_reflect_multiple_users(self):
        """Reaction count increases as multiple bots react."""
        from discordbot.test_utils import fetch_message

        event, message_id = self._create_announcement()

        reacting_bots = {k: v for k, v in self.tokens.items() if k != "main"}

        for name, token in reacting_bots.items():
            time.sleep(0.3)
            add_reaction_as(token, ANNOUNCEMENT_CHANNEL, message_id, "✅")

        time.sleep(0.5)
        msg = fetch_message(ANNOUNCEMENT_CHANNEL, message_id)
        self.assertIsNotNone(msg)

        check_reaction = None
        for r in msg.get("reactions", []):
            if r["emoji"]["name"] == "✅":
                check_reaction = r
                break

        self.assertIsNotNone(check_reaction, "✅ reaction not found on message")
        # Only test bots add reactions (main bot uses components, not reactions)
        expected_min = len(reacting_bots)
        self.assertGreaterEqual(
            check_reaction["count"],
            expected_min,
            f"Expected at least {expected_min} ✅ reactions, got {check_reaction['count']}",
        )
