from collections.abc import Callable
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
from discordbot.utils import DISCORD_API_BASE, sync_send_embed_with_components
from events.constants import EventState
from events.models import EventRepeater, RepeaterSubscription
from events.tasks import (
    build_announcement_notice,
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

GUILD: str = "guild-1"
SIGNUP_BUILD: dict[str, Any] = {
    "embeds": [{"title": "Signup embed"}],
    "components": [{"type": 1, "components": [{"type": 2, "custom_id": "x"}]}],
    "content": "<@&42>",
    "allowed_mentions": {"parse": [], "roles": ["42"]},
}


def _ok_response(payload: dict[str, Any]) -> MagicMock:
    """Build a MagicMock that mimics a successful Discord API response."""
    resp = MagicMock(status_code=200)
    resp.json = MagicMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    return resp


def _error_response(status: int) -> Response:
    resp = Response()
    resp.status_code = status
    resp._content = b'{"message": "Missing Access", "code": 50001}'
    return resp


def _metadata(channel: str, kind: int) -> dict[str, Any]:
    return {"id": channel, "guild_id": GUILD, "type": kind}


def _discord_api(
    metadata: dict[str, dict[str, Any] | None],
    *,
    failing_posts: frozenset[str] = frozenset(),
) -> Callable[..., Any]:
    """Method/path-aware Discord double; unexpected requests fail the test."""

    def dispatch(method: str, url: str, **kwargs: Any) -> Any:
        path = url.removeprefix(f"{DISCORD_API_BASE}/channels/").split("/")
        channel = path[0]
        if method == "GET" and len(path) == 1 and channel in metadata:
            payload = metadata[channel]
            return _ok_response(payload) if payload else _error_response(404)
        if method == "POST" and len(path) == 2 and path[1] in {"messages", "threads"}:
            if channel in failing_posts:
                return _error_response(403)
            if path[1] == "threads":
                return _ok_response(
                    {"id": "signup-thread", "message": {"id": "signup-message"}}
                )
            return _ok_response({"id": "signup-message"})
        if method == "PATCH" and len(path) == 3 and path[1] == "messages":
            return _ok_response({"id": path[2]})
        raise AssertionError(f"unexpected Discord request {method} {url}")

    return dispatch


def _calls(mock_req: MagicMock, method: str | None = None) -> list[tuple[str, str]]:
    return [
        (c.args[0], c.args[1])
        for c in mock_req.call_args_list
        if method is None or c.args[0] == method
    ]


def _url(channel: str, suffix: str = "") -> str:
    return f"{DISCORD_API_BASE}/channels/{channel}{suffix}"


class _DiscordTaskTestCase(DiscordTestMixin, EventTestCase):
    """EventTestCase + ORM-backed internal_client patches.

    Production code calls ``discordbot.utils._rate_limited_request(method, url,
    json=payload, headers=...)`` which dispatches to ``requests.request``.
    Older tests patched ``requests.post`` / ``requests.patch`` — those names are
    never called in the rate-limited path. We patch the wrapper directly so we
    can assert payload + URL while bypassing the real Discord API.
    """


class _GuildDiscordTaskTestCase(_DiscordTaskTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = GUILD
        self.org.save()


class SendEventAnnouncementTaskTest(_GuildDiscordTaskTestCase):
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

    @patch("events.tasks.build_announcement_v2", return_value=SIGNUP_BUILD)
    @patch("discordbot.utils._rate_limited_request")
    def test_primary_signup_operation_and_payload(
        self, mock_req: MagicMock, _build: MagicMock
    ) -> None:
        long_title = "T" * 150
        for kind, title in ((0, ""), (5, ""), (15, ""), (15, long_title)):
            with self.subTest(kind=kind, title=title):
                event = self.make_event(
                    discord_post_signups=True,
                    discord_post_signups_channel_id="signup-channel",
                    discord_event_title=title,
                )
                mock_req.reset_mock()
                mock_req.side_effect = _discord_api(
                    {"signup-channel": _metadata("signup-channel", kind)}
                )
                send_event_announcement(event.pk)
                suffix = "/threads" if kind == 15 else "/messages"
                self.assertEqual(
                    _calls(mock_req),
                    [
                        ("GET", _url("signup-channel")),
                        ("POST", _url("signup-channel", suffix)),
                    ],
                )
                payload = mock_req.call_args.kwargs["json"]
                row = DiscordEventMsgSignup.objects.get(event=event)
                if kind == 15:
                    expected_name = (title or event.name)[:100]
                    self.assertEqual(
                        payload, {"name": expected_name, "message": SIGNUP_BUILD}
                    )
                    self.assertEqual(
                        (row.thread_id, row.channel_type), ("signup-thread", "forum")
                    )
                else:
                    self.assertEqual(payload, SIGNUP_BUILD)
                    self.assertEqual((row.thread_id, row.channel_type), (None, "text"))
                self.assertEqual(
                    (row.channel_id, row.message_id),
                    ("signup-channel", "signup-message"),
                )
        self.assertEqual(len(long_title[:100]), 100)

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_destination_matrix(self, mock_req: MagicMock) -> None:
        for kind, signup, announcement in product(
            (0, 15),
            destination_pairs("signup-channel"),
            destination_pairs("announcement-channel"),
        ):
            with self.subTest(kind=kind, signup=signup, announcement=announcement):
                event = self.make_event(
                    discord_post_signups=signup[0],
                    discord_post_signups_channel_id=signup[1] or "",
                    discord_announcement=announcement[0],
                    discord_announcement_channel_id=announcement[1] or "",
                )
                mock_req.reset_mock()
                mock_req.side_effect = _discord_api(
                    {"signup-channel": _metadata("signup-channel", kind)}
                )
                with (
                    patch(
                        "events.tasks.build_announcement_v2",
                        wraps=build_announcement_v2,
                    ) as build,
                    patch(
                        "events.tasks.build_announcement_notice",
                        wraps=build_announcement_notice,
                    ) as notice,
                ):
                    send_event_announcement(event.pk)
                has_signup = bool(signup[0] and signup[1])
                has_announcement = bool(announcement[0] and announcement[1])
                posts = [c for c in mock_req.call_args_list if c.args[0] == "POST"]
                urls = [c.args[1] for c in posts]
                expected = []
                if has_signup:
                    suffix = "/threads" if kind == 15 else "/messages"
                    expected.append(_url("signup-channel", suffix))
                if has_announcement:
                    expected.append(_url("announcement-channel", "/messages"))
                self.assertEqual(urls, expected)
                self.assertEqual(
                    _calls(mock_req, "GET"),
                    [("GET", _url("signup-channel"))] if has_signup else [],
                )
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
                forum = has_signup and kind == 15
                self.assertEqual(row.thread_id, "signup-thread" if forum else None)
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
                    parent = "signup-thread" if forum else "signup-channel"
                    self.assertEqual(
                        notice.call_args.args[1],
                        f"https://discord.com/channels/{GUILD}/{parent}/signup-message",
                    )
                else:
                    notice.assert_not_called()

    @patch("events.tasks.build_announcement_v2", return_value=SIGNUP_BUILD)
    @patch("discordbot.utils._rate_limited_request")
    def test_primary_failure_fallback_matrix(
        self, mock_req: MagicMock, _build: MagicMock
    ) -> None:
        invalid_metadata = {
            "lookup": None,
            "boolean": {**_metadata("signup-channel", 0), "type": True},
            "string": {**_metadata("signup-channel", 0), "type": "0"},
            "missing": {"id": "signup-channel", "guild_id": GUILD},
            "wrong-channel": _metadata("other-channel", 0),
            "wrong-guild": {**_metadata("signup-channel", 0), "guild_id": "other"},
            "post": _metadata("signup-channel", 0),
        }
        for failure, announcement in product(
            invalid_metadata, destination_pairs("announcement-channel")
        ):
            with self.subTest(failure=failure, announcement=announcement):
                event = self.make_event(
                    discord_post_signups=True,
                    discord_post_signups_channel_id="signup-channel",
                    discord_announcement=announcement[0],
                    discord_announcement_channel_id=announcement[1] or "",
                )
                metadata = {"signup-channel": invalid_metadata[failure]}
                mock_req.reset_mock()
                mock_req.side_effect = _discord_api(
                    metadata, failing_posts=frozenset({"signup-channel"})
                )
                with patch("events.tasks.build_announcement_notice") as notice:
                    send_event_announcement(event.pk)
                has_announcement = bool(announcement[0] and announcement[1])
                expected = [("GET", _url("signup-channel"))]
                if failure == "post":
                    expected.append(("POST", _url("signup-channel", "/messages")))
                if has_announcement:
                    expected.append(("POST", _url("announcement-channel", "/messages")))
                self.assertEqual(_calls(mock_req), expected)
                notice.assert_not_called()
                if has_announcement:
                    self.assertEqual(
                        mock_req.call_args.kwargs["json"],
                        {
                            "embeds": SIGNUP_BUILD["embeds"],
                            "components": SIGNUP_BUILD["components"],
                        },
                    )
                    row = DiscordEventMsgSignup.objects.get(event=event)
                    self.assertEqual(
                        (row.channel_id, row.thread_id, row.message_id, row.has_posted),
                        ("announcement-channel", None, "signup-message", True),
                    )
                else:
                    self.assertFalse(
                        DiscordEventMsgSignup.objects.filter(event=event).exists()
                    )
                self.assertEqual(
                    DiscordMessageLog.objects.filter(
                        source="event_announcement", source_id=event.pk, success=True
                    ).count(),
                    int(has_announcement),
                )

    @patch("discordbot.utils._rate_limited_request")
    def test_lookup_failure_does_not_claim_primary(self, mock_req: MagicMock) -> None:
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id="signup-channel",
        )
        wrong_guild = {"id": "signup-channel", "guild_id": "other", "type": 0}
        mock_req.side_effect = _discord_api({"signup-channel": wrong_guild})
        with patch(
            "events.tasks.sync_send_embed_with_components",
            wraps=sync_send_embed_with_components,
        ) as send:
            result = send_event_announcement(event.pk)
        send.assert_not_called()
        self.assertEqual(result, f"Signup post for event {event.pk}: no send result")
        self.assertFalse(
            DiscordMessageLog.objects.filter(
                source="event_announcement", source_id=event.pk
            ).exists()
        )
        self.assertFalse(DiscordEventMsgSignup.objects.filter(event=event).exists())

        mock_req.reset_mock()
        mock_req.side_effect = _discord_api(
            {"signup-channel": _metadata("signup-channel", 0)}
        )
        send_event_announcement(event.pk)
        self.assertEqual(
            _calls(mock_req, "POST"), [("POST", _url("signup-channel", "/messages"))]
        )
        self.assertTrue(DiscordEventMsgSignup.objects.get(event=event).has_posted)

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
                    patch("events.tasks.resolve_signup_channel_type", return_value=0),
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
            patch("events.tasks.resolve_signup_channel_type", return_value=15),
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
        for announcement in (False, True):
            with self.subTest(announcement=announcement):
                event = self.make_event(
                    discord_post_signups=True,
                    discord_post_signups_channel_id="signup-channel",
                    discord_announcement=announcement,
                    discord_announcement_channel_id="announcement-channel",
                )
                mock_req.reset_mock()
                mock_req.side_effect = _discord_api(
                    {"signup-channel": _metadata("signup-channel", 0)}
                )
                send_event_announcement(event.pk)
                send_event_announcement(event.pk)
                expected = [("POST", _url("signup-channel", "/messages"))]
                if announcement:
                    expected.append(("POST", _url("announcement-channel", "/messages")))
                self.assertEqual(_calls(mock_req, "POST"), expected)
                self.assertEqual(
                    DiscordMessageLog.objects.filter(
                        source="event_announcement", source_id=event.pk, success=True
                    ).count(),
                    1,
                )
                self.assertEqual(
                    DiscordMessageLog.objects.filter(
                        source="event_notice", source_id=event.pk
                    ).count(),
                    int(announcement),
                )
                self.assertTrue(
                    DiscordEventMsgSignup.objects.get(event=event).has_posted
                )

    @patch("discordbot.utils._rate_limited_request")
    def test_held_primary_lease_does_not_post_fallback(
        self, mock_req: MagicMock
    ) -> None:
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id="signup-channel",
            discord_announcement=True,
            discord_announcement_channel_id="announcement-channel",
        )
        DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=event.pk,
            channel_id="signup-channel",
            embed_data={},
            success=None,
            claimed_at=timezone.now(),
        )
        mock_req.side_effect = _discord_api(
            {"signup-channel": _metadata("signup-channel", 0)}
        )
        send_event_announcement(event.pk)
        self.assertEqual(_calls(mock_req, "POST"), [])
        self.assertFalse(DiscordEventMsgSignup.objects.filter(event=event).exists())

    @patch("discordbot.utils._rate_limited_request")
    def test_text_repost_clears_stale_thread_id(self, mock_req: MagicMock) -> None:
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id="signup-channel",
        )
        DiscordEventMsgSignup.objects.create(
            event=event,
            channel_id="signup-channel",
            thread_id="old-thread",
            message_id="old-message",
            channel_type="forum",
            has_posted=False,
        )
        mock_req.side_effect = _discord_api(
            {"signup-channel": _metadata("signup-channel", 0)}
        )
        send_event_announcement(event.pk)
        row = DiscordEventMsgSignup.objects.get(event=event)
        self.assertEqual(
            (row.channel_id, row.thread_id, row.message_id, row.channel_type),
            ("signup-channel", None, "signup-message", "text"),
        )
        self.assertEqual(
            DiscordEvent.objects.get(event=event).signup_message_id, row.pk
        )
        mock_req.reset_mock()
        send_signup_update(event.pk)
        self.assertEqual(
            _calls(mock_req),
            [("PATCH", _url("signup-channel", "/messages/signup-message"))],
        )


class SendSignupUpdateTaskTest(_GuildDiscordTaskTestCase):
    @patch("discordbot.utils._rate_limited_request")
    def test_deleted_primary_signup_is_recreated(self, mock_req: MagicMock) -> None:
        for kind in (0, 5, 15):
            with self.subTest(kind=kind):
                event = self.make_event(
                    discord_post_signups=True,
                    discord_post_signups_channel_id="signup-channel",
                )
                dispatch = _discord_api(
                    {"signup-channel": _metadata("signup-channel", kind)}
                )
                mock_req.side_effect = dispatch
                send_event_announcement(event.pk)
                row = DiscordEventMsgSignup.objects.get(event=event)
                self.assertTrue(row.has_posted)

                response = _error_response(404)
                response._content = b'{"message": "Unknown Message", "code": 10008}'
                mock_req.reset_mock()
                mock_req.side_effect = None
                mock_req.return_value = response
                result = send_signup_update(event.pk)
                parent = "signup-thread" if kind == 15 else "signup-channel"
                self.assertEqual(
                    _calls(mock_req),
                    [("PATCH", _url(parent, "/messages/signup-message"))],
                )
                self.assertIn("Recovered", result)
                row.refresh_from_db()
                self.assertFalse(row.has_posted)
                self.assertFalse(
                    DiscordMessageLog.objects.filter(
                        source="event_announcement", source_id=event.pk, success=True
                    ).exists()
                )

                mock_req.reset_mock()
                mock_req.side_effect = dispatch
                send_event_announcement(event.pk)
                suffix = "/threads" if kind == 15 else "/messages"
                self.assertEqual(
                    _calls(mock_req),
                    [
                        ("GET", _url("signup-channel")),
                        ("POST", _url("signup-channel", suffix)),
                    ],
                )
                row.refresh_from_db()
                self.assertTrue(row.has_posted)
                self.assertEqual(row.message_id, "signup-message")
                self.assertEqual(row.thread_id, "signup-thread" if kind == 15 else None)
                self.assertEqual(row.channel_type, "forum" if kind == 15 else "text")

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_only_create_then_update_uses_persisted_destination(
        self, mock_req: MagicMock
    ) -> None:
        for kind in (0, 5):
            with self.subTest(kind=kind):
                event = self.make_event(
                    discord_post_signups=True,
                    discord_post_signups_channel_id="signup-channel",
                    discord_announcement=False,
                    discord_announcement_channel_id="announcement-channel",
                )
                mock_req.reset_mock()
                mock_req.side_effect = _discord_api(
                    {"signup-channel": _metadata("signup-channel", kind)}
                )
                send_event_announcement(event.pk)
                row = DiscordEventMsgSignup.objects.get(event=event, has_posted=True)
                self.assertEqual(
                    (row.channel_id, row.thread_id, row.message_id, row.channel_type),
                    ("signup-channel", None, "signup-message", "text"),
                )
                event.discord_post_signups_channel_id = "changed-channel"
                event.save()
                mock_req.reset_mock()
                send_signup_update(event.pk)
                self.assertEqual(
                    _calls(mock_req),
                    [("PATCH", _url("signup-channel", "/messages/signup-message"))],
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
        mock_req.side_effect = _discord_api(
            {"signup-forum": _metadata("signup-forum", 15)}
        )
        send_event_announcement(event.pk)
        self.assertEqual(
            _calls(mock_req),
            [("GET", _url("signup-forum")), ("POST", _url("signup-forum", "/threads"))],
        )
        row = DiscordEventMsgSignup.objects.get(event=event)
        self.assertEqual(
            (row.channel_id, row.thread_id, row.message_id, row.channel_type),
            ("signup-forum", "signup-thread", "signup-message", "forum"),
        )
        event.discord_post_signups_channel_id = "changed-channel"
        event.save()
        mock_req.reset_mock()
        send_signup_update(event.pk)
        self.assertEqual(
            _calls(mock_req),
            [("PATCH", _url("signup-thread", "/messages/signup-message"))],
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

        send_event_announcement(self.event.pk)
        send_signup_update(self.event.pk)

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
    the post.
    """

    @patch("discordbot.utils._rate_limited_request")
    def test_404_unknown_message_clears_dedup_state(self, mock_req: MagicMock) -> None:
        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

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
        self.assertEqual(_calls(mock_req, "DELETE"), [])

        mock_req.reset_mock()
        mock_req.side_effect = _discord_api({})
        send_event_announcement(self.event.pk)
        self.assertEqual(
            _calls(mock_req),
            [("POST", _url("1482767177063858216", "/messages"))],
        )
        row = DiscordEventMsgSignup.objects.get(event_id=self.event.pk)
        self.assertEqual(
            (row.has_posted, row.message_id, row.thread_id),
            (True, "signup-message", None),
        )


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class CheckEventRemindersTaskTest(_DiscordTaskTestCase):
    """Verify check_event_reminders idempotency for the signup_reminder source.

    The production code only writes a ``signup_reminder`` ``DiscordMessageLog``
    when ``send_subscriber_notifications`` actually attempts (or sends) a DM.
    A repeater and subscriber with a Discord ID enable that path;
    ``sync_send_dm`` is stubbed to avoid hitting Discord.
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
    OWN_CHANNEL = "333333333333333333"
    ANNOUNCEMENT_CHANNEL = "1482767177063858216"

    def setUp(self) -> None:
        super().setUp()
        self.event.discord_announcement_channel_id = self.ANNOUNCEMENT_CHANNEL
        self.event.discord_confirm_attendance = True
        self.event.discord_profile_reminder = True
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.save()

    @patch("discordbot.utils._rate_limited_request")
    def test_fire_confirm_attendance_uses_own_channel(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.return_value = _ok_response({"id": "fire_att"})
        self.event.discord_confirm_attendance_channel_id = self.OWN_CHANNEL
        self.event.save(update_fields=["discord_confirm_attendance_channel_id"])

        fire_event_reminder(self.event.pk, "confirm_attendance")

        log = DiscordMessageLog.objects.get(
            source="attendance_reminder", source_id=self.event.pk, success=True
        )
        self.assertEqual(log.channel_id, self.OWN_CHANNEL)

    @patch("discordbot.utils._rate_limited_request")
    def test_fire_profile_reminder_uses_own_channel(self, mock_req: MagicMock) -> None:
        mock_req.return_value = _ok_response({"id": "fire_prof"})
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
        mock_req.return_value = _ok_response({"id": "fire_att_blank"})

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
