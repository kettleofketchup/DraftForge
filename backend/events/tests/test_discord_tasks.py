import itertools
import json
from collections.abc import Callable
from contextlib import ExitStack
from datetime import time, timedelta
from itertools import product
from typing import Any
from unittest.mock import MagicMock, patch

import requests
from celery.exceptions import Retry
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from requests.exceptions import HTTPError
from structlog.testing import capture_logs

from app.internal_client import InternalAPIUnavailable
from app.models import CustomUser
from discordbot import dm as discord_dm
from discordbot.dm_keys import signup_reminder_key
from discordbot.dm_ledger import ClaimResult
from discordbot.models import (
    DiscordDM,
    DiscordEvent,
    DiscordEventDM,
    DiscordEventMsgSignup,
    DiscordMessageLog,
    DMKind,
    DMStatus,
    DMSubject,
)
from discordbot.schemas import DMClaimBody
from discordbot.tests.ledger_bridge import ledger_bridge
from discordbot.utils import DISCORD_API_BASE
from events.constants import EventState
from events.models import EventRepeater, RepeaterSubscription
from events.schemas import RepeaterSubscriberSchema
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
from org.models import OrgUser
from user.models import PositionsModel


def _ok_response(payload: dict[str, Any]) -> MagicMock:
    """Build a MagicMock that mimics a successful Discord API response."""
    resp = MagicMock(status_code=200)
    resp.json = MagicMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    return resp


def _discord_response(status: int, body: dict[str, Any]) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp.url = "https://discord.com/api/v10/x"
    resp._content = json.dumps(body).encode()
    resp.headers["Content-Type"] = "application/json"
    return resp


class FakeDiscord:
    """Stands in for ``discordbot.dm._rate_limited_request``."""

    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self.posts = 0
        self.post_failures: list[requests.Response] = []

    def __call__(self, method: str, url: str, **kwargs: object) -> requests.Response:
        n = next(self._ids)
        if url.endswith("/users/@me/channels"):
            return _discord_response(200, {"id": str(800000 + n)})
        self.posts += 1
        if self.post_failures:
            return self.post_failures.pop(0)
        return _discord_response(200, {"id": str(900000 + n)})


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
    def test_announcement_creates_log(self, mock_req: MagicMock) -> None:
        mock_req.return_value = _ok_response({"id": "111222333"})
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
        for signup, announcement in product(
            destination_pairs("signup-channel"),
            destination_pairs("announcement-channel"),
        ):
            with self.subTest(signup=signup, announcement=announcement):
                event = self.make_event(
                    discord_post_signups=signup[0],
                    discord_post_signups_channel_id=signup[1] or "",
                    discord_announcement=announcement[0],
                    discord_announcement_channel_id=announcement[1] or "",
                )
                mock_req.reset_mock()
                mock_req.return_value = _ok_response({"id": "signup-message"})
                with patch(
                    "events.tasks.build_announcement_v2", wraps=build_announcement_v2
                ) as build:
                    send_event_announcement(event.pk)
                has_signup = bool(signup[0] and signup[1])
                has_announcement = bool(announcement[0] and announcement[1])
                posts = [c for c in mock_req.call_args_list if c.args[0] == "POST"]
                urls = [c.args[1] for c in posts]
                expected = []
                if has_signup:
                    expected.append(
                        f"{DISCORD_API_BASE}/channels/signup-channel/threads"
                    )
                if has_announcement:
                    expected.append(
                        f"{DISCORD_API_BASE}/channels/announcement-channel/messages"
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
                    "signup-channel" if has_signup else "announcement-channel",
                )
                row = DiscordEventMsgSignup.objects.get(event=event)
                self.assertTrue(row.has_posted)
                self.assertEqual(row.channel_id, log.channel_id)
                self.assertEqual(row.message_id, "signup-message")
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

    def test_signup_only_falsey_send_has_no_fallback_or_notice(self) -> None:
        for announcement in destination_pairs("announcement-channel")[:-1]:
            with self.subTest(announcement=announcement):
                event = self.make_event(
                    discord_post_signups=True,
                    discord_post_signups_channel_id="signup-channel",
                    discord_announcement=announcement[0],
                    discord_announcement_channel_id=announcement[1] or "",
                )
                with (
                    patch(
                        "events.tasks.sync_send_embed_with_components",
                        return_value=None,
                    ) as send,
                    patch("events.tasks.build_announcement_notice") as notice,
                    patch("events.tasks._update_signup_msg") as update,
                    patch("events.tasks.create_or_update_announcement") as persist,
                ):
                    result = send_event_announcement(event.pk)
                send.assert_called_once()
                self.assertEqual(send.call_args.kwargs["channel_id"], "signup-channel")
                notice.assert_not_called()
                update.assert_not_called()
                persist.assert_not_called()
                self.assertEqual(
                    result, f"Signup post for event {event.pk}: no send result"
                )
                self.assertFalse(
                    DiscordEventMsgSignup.objects.filter(
                        event=event, has_posted=True
                    ).exists()
                )

    def test_both_destinations_falsey_signup_preserves_wrapped_fallback(self) -> None:
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id="signup-channel",
            discord_announcement=True,
            discord_announcement_channel_id="announcement-channel",
        )
        with (
            patch(
                "events.tasks.sync_send_embed_with_components",
                side_effect=[None, {"id": "fallback-message"}],
            ) as send,
            patch("events.tasks.build_announcement_notice") as notice,
        ):
            send_event_announcement(event.pk)
        self.assertEqual(
            [c.kwargs["channel_id"] for c in send.call_args_list],
            ["signup-channel", "announcement-channel"],
        )
        for call in send.call_args_list:
            self.assertEqual(call.kwargs["source"], "event_announcement")
            self.assertEqual(call.kwargs["source_id"], event.pk)
        row = DiscordEventMsgSignup.objects.get(event=event)
        self.assertTrue(row.has_posted)
        self.assertEqual(
            (row.channel_id, row.message_id),
            ("announcement-channel", "fallback-message"),
        )
        notice.assert_not_called()

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_only_second_invocation_does_not_duplicate(
        self, mock_req: MagicMock
    ) -> None:
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id="signup-channel",
            discord_announcement=False,
            discord_announcement_channel_id="announcement-channel",
        )
        mock_req.return_value = _ok_response({"id": "signup-message"})
        send_event_announcement(event.pk)
        send_event_announcement(event.pk)
        mock_req.assert_called_once()
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
            discord_post_signups_channel_id="signup-channel",
            discord_announcement=False,
            discord_announcement_channel_id="announcement-channel",
        )
        mock_req.return_value = _ok_response({"id": "signup-message"})
        send_event_announcement(event.pk)
        self.assertTrue(
            DiscordEventMsgSignup.objects.filter(event=event, has_posted=True).exists()
        )
        row = DiscordEventMsgSignup.objects.get(event=event)
        self.assertEqual(
            (row.channel_id, row.message_id, row.channel_type),
            ("signup-channel", "signup-message", "text"),
        )
        event.discord_post_signups_channel_id = "changed-channel"
        event.save()
        mock_req.reset_mock()
        send_signup_update(event.pk)
        mock_req.assert_called_once()
        self.assertEqual(
            mock_req.call_args.args,
            (
                "PATCH",
                f"{DISCORD_API_BASE}/channels/signup-channel/messages/signup-message",
            ),
        )

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_only_forum_create_then_update_uses_thread(
        self, mock_req: MagicMock
    ) -> None:
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id="signup-forum",
            discord_announcement=True,
            discord_announcement_channel_id="",
        )
        mock_req.return_value = _ok_response(
            {"id": "signup-thread", "message": {"id": "forum-message"}}
        )
        send_event_announcement(event.pk)
        mock_req.assert_called_once()
        self.assertEqual(
            mock_req.call_args.args,
            ("POST", f"{DISCORD_API_BASE}/channels/signup-forum/threads"),
        )
        row = DiscordEventMsgSignup.objects.get(event=event)
        self.assertEqual(
            (row.channel_id, row.thread_id, row.message_id, row.channel_type),
            ("signup-forum", "signup-thread", "forum-message", "forum"),
        )
        mock_req.reset_mock()
        mock_req.return_value = _ok_response({"id": "forum-message"})
        send_signup_update(event.pk)
        mock_req.assert_called_once()
        self.assertEqual(
            mock_req.call_args.args,
            (
                "PATCH",
                f"{DISCORD_API_BASE}/channels/signup-thread/messages/forum-message",
            ),
        )

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_update_edits_announcement(self, mock_req: MagicMock) -> None:
        """signup update should PATCH the original announcement message."""

        def _dispatch(method: str, url: str, **kwargs: Any) -> MagicMock:
            if method == "POST":
                return _ok_response({"id": "444555666"})
            return _ok_response({"id": "444555666"})

        mock_req.side_effect = _dispatch

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        # First create the announcement

        send_event_announcement(self.event.pk)

        # Then update it

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
        mock_req.return_value = _ok_response({"id": "comp111"})

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
        mock_req.return_value = _ok_response({"id": "comp222"})

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
        mock_req.return_value = _ok_response({"id": "orig111"})

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        send_event_announcement(self.event.pk)

        send_signup_update(self.event.pk)

        patch_calls = [
            c for c in mock_req.call_args_list if c.args and c.args[0] == "PATCH"
        ]
        self.assertEqual(len(patch_calls), 1)
        self.assertIn("orig111", patch_calls[0].args[1])

    def test_signup_update_skips_when_no_announcement(self) -> None:
        result = send_signup_update(self.event.pk)
        self.assertEqual(result, "Skipped: no announcement message")


class SendSignupUpdateOrphanedMessageRecoveryTest(_DiscordTaskTestCase):
    """When Discord reports the target message no longer exists (404 + 10008),
    send_signup_update must clear the dedup state so the next sync recreates
    the post instead of retrying edits on a deleted message.
    """

    @patch("discordbot.utils._rate_limited_request")
    def test_404_unknown_message_clears_dedup_state(self, mock_req: MagicMock) -> None:
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
    A repeater and subscriber with a Discord ID are required to produce the log.
    ``send_dm`` runs through the real ledger with Discord stubbed.
    """

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(override_settings(TEST=False))
        self.enterContext(ledger_bridge())
        self.discord = FakeDiscord()
        self.enterContext(
            patch("discordbot.dm._rate_limited_request", side_effect=self.discord)
        )

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

    def test_signup_reminder_sent_when_due(self) -> None:
        self._arm_signup_reminder()

        check_event_reminders()
        self.assertEqual(self.discord.posts, 1)
        log = DiscordMessageLog.objects.get(
            source="signup_reminder", source_id=self.event.pk
        )
        self.assertTrue(log.success)

    def test_signup_reminder_not_sent_twice(self) -> None:
        self._arm_signup_reminder()

        check_event_reminders()
        check_event_reminders()  # Run again — should NOT send duplicate
        self.assertEqual(self.discord.posts, 1)
        self.assertEqual(
            DiscordMessageLog.objects.filter(
                source="signup_reminder", source_id=self.event.pk
            ).count(),
            1,
        )


@override_settings(TEST=False)
class SubscriberReminderLedgerTest(_DiscordTaskTestCase):
    """send_subscriber_notifications through ``send_dm`` and the real ledger."""

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(ledger_bridge())
        self.discord = FakeDiscord()
        self.enterContext(
            patch("discordbot.dm._rate_limited_request", side_effect=self.discord)
        )
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Ledger Repeater",
            frequency="weekly",
            time_of_day=time(18, 0),
            starts_at=timezone.now().date(),
            created_by=self.admin,
        )
        self.discord_event = DiscordEvent.objects.create(
            event=self.event, guild_id="1467168401805017142"
        )
        self.event.event_repeater = self.repeater
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.save()
        self.member = self._subscriber("ledger_member", "700000001", org_member=True)
        self.outsider = self._subscriber("ledger_outsider", "700000002")

    def _subscriber(
        self, username: str, discord_id: str, *, org_member: bool = False
    ) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="pw")
        user.discordId = discord_id
        user.save()
        RepeaterSubscription.objects.create(event_repeater=self.repeater, user=user)
        if org_member:
            OrgUser.objects.get_or_create(user=user, organization=self.org)
        return user

    def _subscribers_with_org_users(self) -> Callable[[int], list[Any]]:
        def fetch(repeater_id: int) -> list[RepeaterSubscriberSchema]:
            out = []
            for sub in RepeaterSubscription.objects.filter(
                event_repeater_id=repeater_id
            ).select_related("user"):
                org_user = OrgUser.objects.filter(
                    user=sub.user, organization=self.org
                ).first()
                out.append(
                    RepeaterSubscriberSchema(
                        user_pk=sub.user_id,
                        discord_id=sub.user.discordId,
                        org_user_pk=org_user.pk if org_user else None,
                    )
                )
            return out

        return fetch

    def _run(self) -> str:
        with patch(
            "events.tasks.get_repeater_subscribers",
            side_effect=self._subscribers_with_org_users(),
        ):
            return send_subscriber_notifications(self.event.pk)

    def _row(self, user: CustomUser) -> DiscordDM:
        return DiscordDM.objects.get(
            idempotency_key=signup_reminder_key(event_id=self.event.pk, user_pk=user.pk)
        )

    def _lease(self) -> DiscordMessageLog:
        return DiscordMessageLog.objects.filter(
            source="signup_reminder", source_id=self.event.pk
        ).latest("pk")

    def test_reminder_builds_key_and_subject(self) -> None:
        self._run()

        row = self._row(self.member)
        self.assertEqual(row.kind, DMKind.SIGNUP_REMINDER)
        self.assertEqual(row.status, DMStatus.SENT)
        self.assertEqual(row.subject_type, DMSubject.EVENT)
        self.assertEqual(row.subject_id, self.event.pk)
        self.assertEqual(row.recipient_id, self.member.pk)
        self.assertEqual(row.organization_id, self.org.pk)
        self.assertTrue(row.has_components)
        self.assertEqual(
            row.context,
            {
                "discord_event_id": self.discord_event.pk,
                "repeater_id": self.repeater.pk,
            },
        )

    def test_reminder_without_org_user_gets_ledger_row_no_event_dm(self) -> None:
        self._run()

        row = self._row(self.outsider)
        self.assertEqual(row.status, DMStatus.SENT)
        self.assertFalse(DiscordEventDM.objects.filter(ledger_entry=row).exists())
        self.assertEqual(DiscordEventDM.objects.count(), 1)

    def test_reminder_event_dm_has_ledger_entry(self) -> None:
        self._run()

        row = self._row(self.member)
        dm = DiscordEventDM.objects.get()
        self.assertEqual(dm.ledger_entry_id, row.pk)
        self.assertTrue(dm.delivered)
        self.assertEqual(dm.message_id, row.discord_message_id)
        self.assertIsNotNone(dm.sent_at)
        self.assertTrue(self._lease().success)

    def test_reminder_retry_after_retryable_failure_one_event_dm(self) -> None:
        self.outsider.delete()
        self.discord.post_failures.append(
            _discord_response(400, {"code": 50035, "message": "Invalid Form Body"})
        )

        self._run()
        row = self._row(self.member)
        self.assertEqual(row.status, DMStatus.FAILED)
        self.assertTrue(row.retryable)
        self.assertFalse(self._lease().success)

        self._run()

        row.refresh_from_db()
        self.assertEqual(row.status, DMStatus.SENT)
        self.assertEqual(row.attempts, 2)
        dm = DiscordEventDM.objects.get()
        self.assertEqual(dm.ledger_entry_id, row.pk)
        self.assertTrue(dm.delivered)
        self.assertTrue(self._lease().success)

    def _claim_unavailable_for(self, user: CustomUser) -> Callable[..., Any]:
        real = discord_dm.claim_dm
        key = signup_reminder_key(event_id=self.event.pk, user_pk=user.pk)

        def claim(body: DMClaimBody) -> ClaimResult | None:
            if body.idempotency_key == key:
                return None
            return real(body)

        return claim

    def test_reminder_ledger_unavailable_fails_lease(self) -> None:
        with patch(
            "discordbot.dm.claim_dm",
            side_effect=self._claim_unavailable_for(self.outsider),
        ):
            self._run()

        lease = self._lease()
        self.assertFalse(lease.success)
        self.assertEqual(lease.response_data["ledger_unavailable"], 1)
        self.assertEqual(lease.response_data["sent"], 1)
        self.assertEqual(self.discord.posts, 1)
        self.assertFalse(
            DiscordDM.objects.filter(
                idempotency_key=signup_reminder_key(
                    event_id=self.event.pk, user_pk=self.outsider.pk
                )
            ).exists()
        )

    def test_reminder_ledger_unavailable_retry_sends_only_missing(self) -> None:
        with patch(
            "discordbot.dm.claim_dm",
            side_effect=self._claim_unavailable_for(self.outsider),
        ):
            self._run()
        first_posts = self.discord.posts

        self._run()

        self.assertEqual(self.discord.posts - first_posts, 1)
        self.assertEqual(self._row(self.member).attempts, 1)
        self.assertEqual(self._row(self.outsider).status, DMStatus.SENT)
        lease = self._lease()
        self.assertTrue(lease.success)
        self.assertEqual(lease.response_data["duplicate"], 1)
        self.assertEqual(lease.response_data["sent"], 1)
        self.assertEqual(DiscordEventDM.objects.count(), 1)

    @override_settings(TEST=True, TEST_DISCORD_USER_ID="999999999")
    def test_reminder_test_mode_marks_delivered_fake_id(self) -> None:
        self._run()

        self.assertEqual(self.discord.posts, 0)
        row = self._row(self.member)
        self.assertEqual(row.status, DMStatus.SKIPPED_TEST_MODE)
        dm = DiscordEventDM.objects.get()
        self.assertEqual(dm.ledger_entry_id, row.pk)
        self.assertTrue(dm.delivered)
        self.assertEqual(dm.message_id, "test-fake-message-id")
        self.assertTrue(self._lease().success)

        internal = self.client.get(
            f"/api/internal/discord/event-state/{self.event.pk}/",
            HTTP_X_INTERNAL_TOKEN="ledger-bridge-token",
        )
        self.assertTrue(internal.json()["has_dms"])
        self.client.force_login(self.admin)
        refire = self.client.post(
            reverse(
                "fire_event_task",
                kwargs={"event_id": self.event.pk, "task_name": "signup_reminder"},
            )
        )
        self.assertEqual(refire.status_code, 409)


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
        mock_req.return_value = _ok_response({"id": "orig111"})
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

    @patch("events.tasks.send_dm")
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
