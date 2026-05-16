from unittest.mock import MagicMock, patch

from django.test import override_settings

from discordbot.models import DiscordMessageLog
from events.constants import EventState
from events.tests._internal_client_orm import DiscordTestMixin
from events.tests.base import EventTestCase


def _ok_response(payload):
    """Build a MagicMock that mimics a successful Discord API response."""
    resp = MagicMock(status_code=200)
    resp.json = MagicMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    return resp


class _DiscordTaskTestCase(DiscordTestMixin, EventTestCase):
    """EventTestCase + ORM-backed internal_client patches.

    Production code calls ``discordbot.utils._rate_limited_request(method, url,
    json=payload, headers=...)`` which dispatches to ``requests.request``.
    Older tests patched ``requests.post`` / ``requests.patch`` — those names are
    never called in the rate-limited path. We patch the wrapper directly so we
    can assert payload + URL while bypassing the real Discord API.
    """


class SendEventAnnouncementTaskTest(_DiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_announcement_creates_log(self, mock_req):
        mock_req.return_value = _ok_response({"id": "111222333"})
        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()
        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)
        log = DiscordMessageLog.objects.get(
            source="event_announcement", source_id=self.event.pk
        )
        self.assertTrue(log.success)
        self.assertEqual(log.channel_id, "1482767177063858216")

    @patch("discordbot.utils._rate_limited_request")
    def test_announcement_skipped_when_disabled(self, mock_req):
        self.event.discord_announcement = False
        self.event.save()
        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)
        self.assertEqual(
            DiscordMessageLog.objects.filter(source="event_announcement").count(), 0
        )
        mock_req.assert_not_called()


class SendSignupUpdateTaskTest(_DiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_signup_update_edits_announcement(self, mock_req):
        """signup update should PATCH the original announcement message."""

        def _dispatch(method, url, **kwargs):
            if method == "POST":
                return _ok_response({"id": "444555666"})
            return _ok_response({"id": "444555666"})

        mock_req.side_effect = _dispatch

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        # First create the announcement
        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)

        # Then update it
        from events.tasks import send_signup_update

        send_signup_update(self.event.pk)

        # PATCH must have been called and the URL must reference the message id.
        patch_calls = [
            c for c in mock_req.call_args_list if c.args and c.args[0] == "PATCH"
        ]
        self.assertEqual(len(patch_calls), 1)
        self.assertIn("444555666", patch_calls[0].args[1])

    def test_signup_update_skipped_when_no_announcement(self):
        from events.tasks import send_signup_update

        result = send_signup_update(self.event.pk)
        self.assertEqual(result, "Skipped: no announcement message")


class SendEventAnnouncementComponentsTest(_DiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_announcement_includes_components_in_payload(self, mock_req):
        mock_req.return_value = _ok_response({"id": "comp111"})

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)

        # Find the POST call to the messages endpoint
        post_calls = [
            c for c in mock_req.call_args_list if c.args and c.args[0] == "POST"
        ]
        self.assertTrue(post_calls, "Expected at least one POST to Discord API")
        payload = post_calls[0].kwargs.get("json") or {}
        self.assertIn("components", payload)
        self.assertTrue(len(payload["components"]) >= 1)

    @patch("discordbot.utils._rate_limited_request")
    def test_announcement_components_contain_signup_button(self, mock_req):
        mock_req.return_value = _ok_response({"id": "comp222"})

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)

        post_calls = [
            c for c in mock_req.call_args_list if c.args and c.args[0] == "POST"
        ]
        self.assertTrue(post_calls, "Expected at least one POST to Discord API")
        payload = post_calls[0].kwargs.get("json") or {}
        buttons = payload["components"][0]["components"]
        custom_ids = [b.get("custom_id") for b in buttons if b.get("custom_id")]
        self.assertIn(f"event_signup:{self.event.pk}", custom_ids)


class SendSignupUpdateEditsMessageTest(_DiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_signup_update_edits_original_announcement(self, mock_req):
        mock_req.return_value = _ok_response({"id": "orig111"})

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)

        from events.tasks import send_signup_update

        send_signup_update(self.event.pk)

        patch_calls = [
            c for c in mock_req.call_args_list if c.args and c.args[0] == "PATCH"
        ]
        self.assertEqual(len(patch_calls), 1)
        self.assertIn("orig111", patch_calls[0].args[1])

    def test_signup_update_skips_when_no_announcement(self):
        from events.tasks import send_signup_update

        result = send_signup_update(self.event.pk)
        self.assertEqual(result, "Skipped: no announcement message")


class SendSignupUpdateOrphanedMessageRecoveryTest(_DiscordTaskTestCase):
    """When Discord reports the target message no longer exists (404 + 10008),
    send_signup_update must clear the dedup state so the next sync recreates
    the post. Prior to this fix the bot would silently retry edits forever on
    a ghost message and never re-post.
    """

    @patch("discordbot.utils._rate_limited_request")
    def test_404_unknown_message_clears_dedup_state(self, mock_req):
        from discordbot.models import DiscordEventMsgSignup, DiscordMessageLog
        from events.tasks import send_event_announcement, send_signup_update

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        # Phase 1: create the original post. POST returns 201.
        mock_req.return_value = _ok_response({"id": "ghost_msg"})
        send_event_announcement(self.event.pk)

        # Sanity: dedup is set (has_posted=True, log success=True).
        self.assertTrue(
            DiscordEventMsgSignup.objects.filter(
                event_id=self.event.pk, has_posted=True
            ).exists()
        )
        self.assertTrue(
            DiscordMessageLog.objects.filter(
                source="event_announcement",
                source_id=self.event.pk,
                success=True,
            ).exists()
        )

        # Phase 2: the next edit returns 404 + 10008 (admin deleted in Discord).
        from requests.exceptions import HTTPError

        def _edit_404(method, url, **kwargs):
            if method == "PATCH":
                resp = MagicMock(status_code=404)
                resp.json.return_value = {
                    "message": "Unknown Message",
                    "code": 10008,
                }
                resp.raise_for_status.side_effect = HTTPError("404")
                return resp
            return _ok_response({"id": "ignored"})

        mock_req.side_effect = _edit_404
        result = send_signup_update(self.event.pk)

        # Dedup state must be cleared so the next sync recreates the post.
        self.assertIn("Recovered", result)
        self.assertFalse(
            DiscordEventMsgSignup.objects.filter(
                event_id=self.event.pk, has_posted=True
            ).exists(),
            "has_posted must flip to False on orphaned-message detection",
        )
        self.assertFalse(
            DiscordMessageLog.objects.filter(
                source="event_announcement",
                source_id=self.event.pk,
                success=True,
            ).exists(),
            "DiscordMessageLog.success must flip to False so existing_logs dedup unblocks",
        )


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class CheckEventRemindersTaskTest(_DiscordTaskTestCase):
    """Verify check_event_reminders idempotency for the signup_reminder source.

    The production code only writes a ``signup_reminder`` ``DiscordMessageLog``
    when ``send_subscriber_notifications`` actually attempts (or sends) a DM.
    That requires a repeater + a subscriber with a Discord ID. Older versions
    of these tests skipped the repeater entirely, so they could never produce
    the log they were asserting on. We add a repeater + subscriber and stub
    ``sync_send_dm`` so the reminder pipeline runs without hitting Discord.
    """

    def _arm_signup_reminder(self):
        from datetime import time, timedelta

        from django.utils import timezone

        from app.models import CustomUser, PositionsModel
        from discordbot.models import DiscordEvent
        from events.models import EventRepeater, RepeaterSubscription

        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Reminder Repeater",
            frequency="weekly",
            time_of_day=time(18, 0),
            starts_at=timezone.now().date(),
            created_by=self.admin,
        )
        subscriber_user = CustomUser.objects.create_user(
            username="reminder_sub", password="pw"
        )
        subscriber_user.positions = PositionsModel.objects.create()
        subscriber_user.discordId = "555111222"
        subscriber_user.save()
        RepeaterSubscription.objects.create(
            event_repeater=repeater, user=subscriber_user
        )

        DiscordEvent.objects.create(
            event=self.event,
            guild_id="1467168401805017142",
        )

        self.event.scheduled_at = timezone.now() + timedelta(hours=23)
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.discord_signup_reminder = True
        self.event.discord_signup_reminder_hours = 24
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.event_repeater = repeater
        self.event.save()

    @patch("discordbot.utils.sync_send_dm")
    def test_signup_reminder_sent_when_due(self, mock_send_dm):
        mock_send_dm.return_value = {"id": "dm111"}
        self._arm_signup_reminder()

        from events.tasks import check_event_reminders

        check_event_reminders()
        self.assertTrue(
            DiscordMessageLog.objects.filter(
                source="signup_reminder", source_id=self.event.pk
            ).exists()
        )

    @patch("discordbot.utils.sync_send_dm")
    def test_signup_reminder_not_sent_twice(self, mock_send_dm):
        mock_send_dm.return_value = {"id": "dm222"}
        self._arm_signup_reminder()

        from events.tasks import check_event_reminders

        check_event_reminders()
        check_event_reminders()  # Run again — should NOT send duplicate
        self.assertEqual(
            DiscordMessageLog.objects.filter(
                source="signup_reminder", source_id=self.event.pk
            ).count(),
            1,
        )
