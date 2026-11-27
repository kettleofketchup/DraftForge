import json
from contextlib import ExitStack
from datetime import time, timedelta
from itertools import product
from typing import Any
from unittest.mock import MagicMock, patch

from celery.exceptions import Retry
from django.test import override_settings
from django.utils import timezone
from requests import Response
from requests.exceptions import HTTPError
from structlog.testing import capture_logs

from app.internal_client import InternalAPIUnavailable
from app.models import CustomUser
from discordbot.models import DiscordEvent, DiscordEventMsgSignup, DiscordMessageLog
from discordbot.utils import DISCORD_API_BASE
from events.constants import EventState
from events.models import EventRepeater, RepeaterSubscription
from events.tasks import (
    build_announcement_v2,
    check_event_reminders,
    fire_event_reminder,
    send_attendance_reminder,
    send_event_announcement,
    send_profile_reminder,
    send_signup_update,
    send_subscriber_notifications,
)
from events.tests._internal_client_orm import DiscordTestMixin
from events.tests.base import EventTestCase
from events.tests.test_signup_post_independence import destination_pairs
from user.models import PositionsModel


def _ok_response(payload: dict[str, Any]) -> MagicMock:
    """Build a MagicMock that mimics a successful Discord API response."""
    resp = MagicMock(status_code=200)
    resp.json = MagicMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    return resp


def _configured_response(method: str, url: str, **kwargs: Any) -> Response:
    payload = (
        {"id": url.rsplit("/", 1)[-1], "guild_id": "200000000000000001", "type": 0}
        if method == "GET"
        else {"id": "100000000000000002"}
    )
    result = Response()
    result.status_code = 200
    result._content = json.dumps(payload).encode()
    return result


GUILD = "200000000000000001"
SIGNUP_CHANNEL = "100000000000000001"
ANNOUNCEMENT_CHANNEL = "100000000000000003"
MESSAGE = "100000000000000002"
THREAD = "100000000000000004"


def _real_response(status: int, payload: object) -> Response:
    result = Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


def _discord_http(
    message_id: str = MESSAGE,
    *,
    types: dict[str, int] | None = None,
    posts: dict[str, Response] | None = None,
) -> Any:
    def handler(method: str, url: str, **kwargs: Any) -> Response:
        path = url.removeprefix(f"{DISCORD_API_BASE}/channels/")
        channel = path.split("/")[0]
        if method == "GET" and "/" not in path:
            kind = (types or {}).get(channel, 0)
            return _real_response(200, {"id": channel, "guild_id": GUILD, "type": kind})
        if method == "POST" and posts and channel in posts:
            return posts[channel]
        if method == "POST" and url.endswith("/threads"):
            return _real_response(201, {"id": THREAD, "message": {"id": message_id}})
        return _real_response(200, {"id": message_id})

    return handler


class _DiscordTaskTestCase(DiscordTestMixin, EventTestCase):
    """EventTestCase + ORM-backed internal_client patches.

    Production code calls ``discordbot.utils._rate_limited_request(method, url,
    json=payload, headers=...)`` which dispatches to ``requests.request``.
    Older tests patched ``requests.post`` / ``requests.patch`` — those names are
    never called in the rate-limited path. We patch the wrapper directly so we
    can assert payload + URL while bypassing the real Discord API.
    """

    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = GUILD
        self.org.save()

    def posts(self, mock_req: MagicMock) -> list[Any]:
        return [c for c in mock_req.call_args_list if c.args[0] == "POST"]


class SendEventAnnouncementTaskTest(_DiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_announcement_creates_log(self, mock_req: MagicMock) -> None:
        mock_req.side_effect = _discord_http("111222333")
        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        send_event_announcement(self.event.pk)
        log = DiscordMessageLog.objects.get(
            source="event_announcement", source_id=self.event.pk
        )
        self.assertTrue(log.success)
        self.assertEqual(log.channel_id, "1482767177063858216")

    @patch("discordbot.utils._rate_limited_request")
    def test_announcement_skipped_when_disabled(self, mock_req: MagicMock) -> None:
        self.event.discord_announcement = False
        self.event.save()

        send_event_announcement(self.event.pk)
        self.assertEqual(
            DiscordMessageLog.objects.filter(source="event_announcement").count(), 0
        )
        mock_req.assert_not_called()

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_destination_matrix(self, mock_req: MagicMock) -> None:
        self.org.discord_server_id = "200000000000000001"
        self.org.save()
        for signup, announcement in product(
            destination_pairs("100000000000000001"),
            destination_pairs("100000000000000003"),
        ):
            with self.subTest(signup=signup, announcement=announcement):
                event = self.make_event(
                    discord_post_signups=signup[0],
                    discord_post_signups_channel_id=signup[1] or "",
                    discord_announcement=announcement[0],
                    discord_announcement_channel_id=announcement[1] or "",
                )
                mock_req.reset_mock()
                mock_req.side_effect = _configured_response
                with patch(
                    "events.signup_post_send.build_announcement_v2",
                    wraps=build_announcement_v2,
                ) as build:
                    send_event_announcement(event.pk)
                has_signup = bool(signup[0] and signup[1])
                has_announcement = bool(announcement[0] and announcement[1])
                posts = [c for c in mock_req.call_args_list if c.args[0] == "POST"]
                urls = [c.args[1] for c in posts]
                expected = []
                if has_signup:
                    expected.append(
                        f"{DISCORD_API_BASE}/channels/100000000000000001/messages"
                    )
                if has_announcement:
                    expected.append(
                        f"{DISCORD_API_BASE}/channels/100000000000000003/messages"
                    )
                self.assertEqual(urls, expected)
                if not expected:
                    mock_req.assert_not_called()
                    build.assert_not_called()
                    self.assertFalse(
                        DiscordEventMsgSignup.objects.filter(event=event).exists()
                    )
                    continue
                payload = posts[0].kwargs["json"]
                payload = payload.get("message", payload)
                self.assertTrue(payload["embeds"])
                self.assertTrue(payload["components"])
                log = DiscordMessageLog.objects.get(
                    source="event_announcement", source_id=event.pk
                )
                self.assertTrue(log.success)
                self.assertEqual(
                    log.channel_id,
                    "100000000000000001" if has_signup else "100000000000000003",
                )
                row = DiscordEventMsgSignup.objects.get(event=event)
                self.assertTrue(row.has_posted)
                self.assertEqual(row.channel_id, log.channel_id)
                self.assertEqual(row.message_id, "100000000000000002")
                self.assertEqual(
                    DiscordEvent.objects.get(event=event).signup_message_id, row.pk
                )
                self.assertEqual(
                    DiscordMessageLog.objects.filter(
                        source="event_notice", source_id=event.pk, success=True
                    ).count(),
                    int(has_signup and has_announcement),
                )
                if has_signup and has_announcement:
                    self.assertNotIn("components", posts[1].kwargs["json"])

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_only_rejected_send_has_no_fallback_or_notice(
        self, mock_req: MagicMock
    ) -> None:
        rejected = {SIGNUP_CHANNEL: _real_response(403, {"code": 50013})}
        for announcement in destination_pairs(ANNOUNCEMENT_CHANNEL)[:-1]:
            with self.subTest(announcement=announcement):
                event = self.make_event(
                    discord_post_signups=True,
                    discord_post_signups_channel_id=SIGNUP_CHANNEL,
                    discord_announcement=announcement[0],
                    discord_announcement_channel_id=announcement[1] or "",
                )
                mock_req.reset_mock()
                mock_req.side_effect = _discord_http(posts=rejected)
                result = send_event_announcement(event.pk)
                self.assertEqual(
                    [c.args[1] for c in self.posts(mock_req)],
                    [f"{DISCORD_API_BASE}/channels/{SIGNUP_CHANNEL}/messages"],
                )
                self.assertIn(f"Signup post for event {event.pk}: failed", result)
                self.assertFalse(
                    DiscordMessageLog.objects.filter(
                        source="event_notice", source_id=event.pk
                    ).exists()
                )
                self.assertFalse(
                    DiscordEventMsgSignup.objects.filter(
                        event=event, has_posted=True
                    ).exists()
                )

    @patch("discordbot.utils._rate_limited_request")
    def test_rejected_signup_falls_back_to_announcement(
        self, mock_req: MagicMock
    ) -> None:
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id=SIGNUP_CHANNEL,
            discord_announcement=True,
            discord_announcement_channel_id=ANNOUNCEMENT_CHANNEL,
        )
        mock_req.side_effect = _discord_http(
            "100000000000000005",
            posts={SIGNUP_CHANNEL: _real_response(403, {"code": 50013})},
        )
        send_event_announcement(event.pk)
        self.assertEqual(
            [c.args[1] for c in self.posts(mock_req)],
            [
                f"{DISCORD_API_BASE}/channels/{SIGNUP_CHANNEL}/messages",
                f"{DISCORD_API_BASE}/channels/{ANNOUNCEMENT_CHANNEL}/messages",
            ],
        )
        self.assertEqual(
            list(
                DiscordMessageLog.objects.filter(source_id=event.pk)
                .order_by("pk")
                .values_list("source", "channel_id", "success")
            ),
            [
                ("event_announcement", SIGNUP_CHANNEL, False),
                ("event_announcement", ANNOUNCEMENT_CHANNEL, True),
            ],
        )
        row = DiscordEventMsgSignup.objects.get(event=event, has_posted=True)
        self.assertEqual(
            (row.channel_id, row.message_id),
            (ANNOUNCEMENT_CHANNEL, "100000000000000005"),
        )

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_only_second_invocation_does_not_duplicate(
        self, mock_req: MagicMock
    ) -> None:
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id=SIGNUP_CHANNEL,
            discord_announcement=False,
            discord_announcement_channel_id=ANNOUNCEMENT_CHANNEL,
        )
        mock_req.side_effect = _discord_http()
        send_event_announcement(event.pk)
        result = send_event_announcement(event.pk)
        self.assertEqual(len(self.posts(mock_req)), 1)
        self.assertIn("already_delivered", result)
        self.assertEqual(
            DiscordMessageLog.objects.filter(
                source="event_announcement", source_id=event.pk, success=True
            ).count(),
            1,
        )
        self.assertFalse(
            DiscordMessageLog.objects.filter(
                source="event_notice", source_id=event.pk
            ).exists()
        )
        self.assertTrue(DiscordEventMsgSignup.objects.get(event=event).has_posted)


class SendSignupUpdateTaskTest(_DiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_signup_only_create_then_update_uses_persisted_destination(
        self, mock_req: MagicMock
    ) -> None:
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id=SIGNUP_CHANNEL,
            discord_announcement=False,
            discord_announcement_channel_id=ANNOUNCEMENT_CHANNEL,
        )
        mock_req.side_effect = _discord_http()
        send_event_announcement(event.pk)
        self.assertTrue(
            DiscordEventMsgSignup.objects.filter(event=event, has_posted=True).exists()
        )
        row = DiscordEventMsgSignup.objects.get(event=event)
        self.assertEqual(
            (row.channel_id, row.message_id, row.channel_type),
            (SIGNUP_CHANNEL, MESSAGE, "text"),
        )
        event.discord_post_signups_channel_id = "100000000000000009"
        event.save()
        mock_req.reset_mock()
        send_signup_update(event.pk)
        mock_req.assert_called_once()
        self.assertEqual(
            mock_req.call_args.args,
            (
                "PATCH",
                f"{DISCORD_API_BASE}/channels/{SIGNUP_CHANNEL}/messages/{MESSAGE}",
            ),
        )

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_only_forum_create_then_update_uses_thread(
        self, mock_req: MagicMock
    ) -> None:
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id=SIGNUP_CHANNEL,
            discord_announcement=True,
            discord_announcement_channel_id="",
        )
        mock_req.side_effect = _discord_http(types={SIGNUP_CHANNEL: 15})
        send_event_announcement(event.pk)
        self.assertEqual(
            [c.args for c in self.posts(mock_req)],
            [("POST", f"{DISCORD_API_BASE}/channels/{SIGNUP_CHANNEL}/threads")],
        )
        row = DiscordEventMsgSignup.objects.get(event=event)
        self.assertEqual(
            (row.channel_id, row.thread_id, row.message_id, row.channel_type),
            (SIGNUP_CHANNEL, THREAD, MESSAGE, "forum"),
        )
        mock_req.reset_mock()
        send_signup_update(event.pk)
        mock_req.assert_called_once()
        self.assertEqual(
            mock_req.call_args.args,
            (
                "PATCH",
                f"{DISCORD_API_BASE}/channels/{THREAD}/messages/{MESSAGE}",
            ),
        )

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_update_edits_announcement(self, mock_req: MagicMock) -> None:
        """signup update should PATCH the original announcement message."""

        mock_req.side_effect = _discord_http("444555666")

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        send_event_announcement(self.event.pk)

        send_signup_update(self.event.pk)

        # PATCH must have been called and the URL must reference the message id.
        patch_calls = [
            c for c in mock_req.call_args_list if c.args and c.args[0] == "PATCH"
        ]
        self.assertEqual(len(patch_calls), 1)
        self.assertIn("444555666", patch_calls[0].args[1])

    def test_signup_update_skipped_when_no_announcement(self) -> None:
        result = send_signup_update(self.event.pk)
        self.assertEqual(result, "Skipped: no announcement message")


class SendEventAnnouncementComponentsTest(_DiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_announcement_includes_components_in_payload(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.side_effect = _discord_http()

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

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
    def test_announcement_components_contain_signup_button(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.side_effect = _discord_http()

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

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
    def test_signup_update_edits_original_announcement(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.side_effect = _discord_http("100000000000000111")

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        send_event_announcement(self.event.pk)

        send_signup_update(self.event.pk)

        patch_calls = [
            c for c in mock_req.call_args_list if c.args and c.args[0] == "PATCH"
        ]
        self.assertEqual(len(patch_calls), 1)
        self.assertIn("100000000000000111", patch_calls[0].args[1])

    def test_signup_update_skips_when_no_announcement(self) -> None:
        result = send_signup_update(self.event.pk)
        self.assertEqual(result, "Skipped: no announcement message")


class SendSignupUpdateOrphanedMessageRecoveryTest(_DiscordTaskTestCase):
    """When Discord reports the target message no longer exists (404 + 10008),
    send_signup_update must clear the dedup state so the next sync recreates
    the post.
    """

    @patch("discordbot.utils._rate_limited_request")
    def test_404_unknown_message_clears_dedup_state(self, mock_req: MagicMock) -> None:
        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        # Phase 1: create the original post. POST returns 201.
        mock_req.side_effect = _discord_http("100000000000000222")
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

        def _edit_404(method: str, url: str, **kwargs: Any) -> MagicMock:
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
    That requires a repeater + a subscriber with a Discord ID, so tests add
    both and stub ``sync_send_dm`` so the pipeline runs without hitting Discord.
    """

    def _arm_signup_reminder(self) -> None:
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

    @patch("events.tasks.sync_send_dm")
    def test_signup_reminder_sent_when_due(self, mock_send_dm: MagicMock) -> None:
        mock_send_dm.return_value = {"id": "dm111"}
        self._arm_signup_reminder()

        check_event_reminders()
        mock_send_dm.assert_called_once()
        log = DiscordMessageLog.objects.get(
            source="signup_reminder", source_id=self.event.pk
        )
        self.assertTrue(log.success)

    @patch("events.tasks.sync_send_dm")
    def test_signup_reminder_not_sent_twice(self, mock_send_dm: MagicMock) -> None:
        mock_send_dm.return_value = {"id": "dm222"}
        self._arm_signup_reminder()

        check_event_reminders()
        check_event_reminders()  # Run again — should NOT send duplicate
        mock_send_dm.assert_called_once()
        self.assertEqual(
            DiscordMessageLog.objects.filter(
                source="signup_reminder", source_id=self.event.pk
            ).count(),
            1,
        )


class FireEventReminderChannelTest(_DiscordTaskTestCase):
    OWN_CHANNEL = "100000000000000001"
    ANNOUNCEMENT_CHANNEL = "100000000000000003"

    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = "200000000000000001"
        self.org.save()
        self.event.discord_announcement_channel_id = self.ANNOUNCEMENT_CHANNEL
        self.event.discord_confirm_attendance = True
        self.event.discord_profile_reminder = True
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.save()

    @patch("discordbot.utils._rate_limited_request")
    def test_fire_confirm_attendance_uses_own_channel(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.side_effect = _configured_response
        self.event.discord_confirm_attendance_channel_id = self.OWN_CHANNEL
        self.event.save(update_fields=["discord_confirm_attendance_channel_id"])

        fire_event_reminder(self.event.pk, "confirm_attendance")

        log = DiscordMessageLog.objects.get(
            source="attendance_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, self.OWN_CHANNEL)

    @patch("discordbot.utils._rate_limited_request")
    def test_fire_profile_reminder_uses_own_channel(self, mock_req: MagicMock) -> None:
        mock_req.side_effect = _configured_response
        self.event.discord_profile_reminder_channel_id = self.OWN_CHANNEL
        self.event.save(update_fields=["discord_profile_reminder_channel_id"])

        fire_event_reminder(self.event.pk, "profile_reminder")

        log = DiscordMessageLog.objects.get(
            source="profile_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, self.OWN_CHANNEL)

    @patch("discordbot.utils._rate_limited_request")
    def test_fire_blank_own_channel_uses_announcement(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.side_effect = _configured_response

        fire_event_reminder(self.event.pk, "confirm_attendance")

        log = DiscordMessageLog.objects.get(
            source="attendance_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, self.ANNOUNCEMENT_CHANNEL)

    @patch("discordbot.utils._rate_limited_request")
    def test_fire_reminder_blank_channels_skips(self, mock_req: MagicMock) -> None:
        self.event.discord_announcement_channel_id = ""
        self.event.save(update_fields=["discord_announcement_channel_id"])

        result = fire_event_reminder(self.event.pk, "profile_reminder")

        mock_req.assert_not_called()
        self.assertIn("No channel configured", result)


class SignupReadUnavailableTest(_DiscordTaskTestCase):
    """A failed signup read must never post or edit with an empty list."""

    def setUp(self) -> None:
        super().setUp()
        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.discord_confirm_attendance = True
        self.event.discord_profile_reminder = True
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.save()

    def _unavailable(self) -> ExitStack:
        stack = ExitStack()
        for target in (
            "events.discord.embeds.get_event_signups",
            "events.tasks.get_event_signups",
        ):
            stack.enter_context(
                patch(target, side_effect=InternalAPIUnavailable("signups"))
            )
        return stack

    def _assert_skipped(self, logs: list[dict], mock_req: MagicMock) -> None:
        mock_req.assert_not_called()
        events = [entry["event"] for entry in logs]
        self.assertIn("signup_list_unavailable", events)
        self.assertNotIn("celery_task_failed", events)
        entry = next(e for e in logs if e["event"] == "signup_list_unavailable")
        self.assertEqual(entry["event_id"], self.event.pk)
        self.assertEqual(entry["system"], "discord")
        self.assertEqual(entry["subsystem"], "celery")

    @patch("discordbot.utils._rate_limited_request")
    def test_announcement_not_posted(self, mock_req: MagicMock) -> None:
        with self._unavailable(), capture_logs() as logs:
            send_event_announcement(self.event.pk)

        self._assert_skipped(logs, mock_req)

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_update_does_not_edit(self, mock_req: MagicMock) -> None:
        mock_req.side_effect = _discord_http("100000000000000111")
        send_event_announcement(self.event.pk)
        mock_req.reset_mock()

        with (
            self._unavailable(),
            capture_logs() as logs,
            self.assertRaises(Retry),
        ):
            send_signup_update(self.event.pk)

        self._assert_skipped(logs, mock_req)
        self.assertIn("celery_task_retry", [entry["event"] for entry in logs])

    @patch("discordbot.utils._rate_limited_request")
    def test_attendance_reminder_not_sent(self, mock_req: MagicMock) -> None:
        with self._unavailable(), capture_logs() as logs:
            send_attendance_reminder(self.event.pk)

        self._assert_skipped(logs, mock_req)

    @patch("discordbot.utils._rate_limited_request")
    def test_profile_reminder_not_sent(self, mock_req: MagicMock) -> None:
        with self._unavailable(), capture_logs() as logs:
            send_profile_reminder(self.event.pk)

        self._assert_skipped(logs, mock_req)

    @patch("discordbot.utils._rate_limited_request")
    def test_fired_signup_reminder_not_sent(self, mock_req: MagicMock) -> None:
        with self._unavailable(), capture_logs() as logs:
            fire_event_reminder(self.event.pk, "signup_reminder")

        self._assert_skipped(logs, mock_req)

    @patch("events.tasks.sync_send_dm")
    @patch("discordbot.utils._rate_limited_request")
    def test_subscriber_dms_not_sent_and_no_lease_held(
        self, mock_req: MagicMock, mock_send_dm: MagicMock
    ) -> None:
        CheckEventRemindersTaskTest._arm_signup_reminder(self)

        with self._unavailable(), capture_logs() as logs:
            send_subscriber_notifications(self.event.pk)

        mock_send_dm.assert_not_called()
        self._assert_skipped(logs, mock_req)
        self.assertFalse(
            DiscordMessageLog.objects.filter(
                source="signup_reminder", source_id=self.event.pk
            ).exists()
        )
