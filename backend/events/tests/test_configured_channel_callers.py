import json
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import requests

from discordbot.models import DiscordEvent, DiscordEventMsgSignup, DiscordMessageLog
from discordbot.utils import DISCORD_API_BASE
from events.constants import SignupStatus
from events.models import Event, EventSignup
from events.tasks import (
    fire_event_reminder,
    send_attendance_reminder,
    send_event_announcement,
    send_new_event_notification,
    send_profile_reminder,
    send_start_mention,
)
from events.tests._internal_client_orm import DiscordTestMixin
from events.tests.base import EventTestCase

CHANNEL = "100000000000000001"
GUILD = "200000000000000001"
MESSAGE = "100000000000000002"
THREAD = "100000000000000003"
SIGNUP_CHANNEL = "100000000000000004"


def response(status: int, payload: object) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


class ConfiguredChannelCallersTest(DiscordTestMixin, EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = GUILD
        self.org.save()
        self.channel_type: int = 0
        self.http: MagicMock = self.enterContext(
            patch("discordbot.utils.requests.request", side_effect=self.request)
        )
        self.enterContext(patch("discordbot.utils._acquire_rate_limit_token"))

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        if method == "GET":
            if url == f"{DISCORD_API_BASE}/channels/{SIGNUP_CHANNEL}":
                return response(
                    200, {"id": SIGNUP_CHANNEL, "guild_id": GUILD, "type": 0}
                )
            self.assertEqual(url, f"{DISCORD_API_BASE}/channels/{CHANNEL}")
            return response(
                200, {"id": CHANNEL, "guild_id": GUILD, "type": self.channel_type}
            )
        self.assertEqual(method, "POST")
        if url.endswith("/threads"):
            return response(201, {"id": THREAD, "message": {"id": MESSAGE}})
        return response(201, {"id": MESSAGE})

    def event_for_send(self, **overrides: Any) -> Event:
        fields = {
            "name": "Synthetic Event",
            "discord_event_title": "Synthetic Title",
            "discord_announcement": False,
            "discord_announcement_channel_id": CHANNEL,
            "discord_confirm_attendance": True,
            "discord_confirm_attendance_channel_id": CHANNEL,
            "discord_profile_reminder": True,
            "discord_profile_reminder_channel_id": CHANNEL,
            "discord_new_event_channel_id": CHANNEL,
        }
        fields.update(overrides)
        return self.make_event(**fields)

    def posts(self) -> list[Any]:
        return [call for call in self.http.call_args_list if call.args[0] == "POST"]

    def assert_routing(self, sender: Callable[[int], str]) -> None:
        for kind, route in ((0, "messages"), (5, "messages"), (15, "threads")):
            with self.subTest(kind=kind):
                self.channel_type = kind
                self.http.reset_mock()
                event = self.event_for_send()
                sender(event.pk)
                posts = self.posts()
                self.assertEqual(len(posts), 1)
                self.assertEqual(
                    posts[0].args[1], f"{DISCORD_API_BASE}/channels/{CHANNEL}/{route}"
                )
                body = posts[0].kwargs["json"]
                if kind == 15:
                    self.assertEqual(body["name"], "Synthetic Title")
                    body = body["message"]
                self.assertTrue(body["embeds"])
                self.assertTrue(
                    DiscordMessageLog.objects.get(source_id=event.pk).success
                )

    def test_attendance_reminder_routes_by_channel_type(self) -> None:
        self.assert_routing(send_attendance_reminder)

    def test_profile_reminder_routes_by_channel_type(self) -> None:
        self.assert_routing(send_profile_reminder)

    def test_new_event_notification_routes_by_channel_type(self) -> None:
        self.assert_routing(send_new_event_notification)

    def test_fire_event_reminder_routes_by_channel_type(self) -> None:
        for reminder in ("signup_reminder", "confirm_attendance", "profile_reminder"):
            with self.subTest(reminder=reminder):
                self.assert_routing(
                    lambda pk: fire_event_reminder(pk, reminder, self.admin.pk)
                )
        logs = DiscordMessageLog.objects.filter(source__endswith="reminder")
        self.assertTrue(logs.exists())
        self.assertEqual(
            set(logs.values_list("fired_by_id", flat=True)), {self.admin.pk}
        )

    def test_reminder_falls_back_to_announcement_channel_when_own_blank(self) -> None:
        for sender in (
            send_attendance_reminder,
            send_profile_reminder,
            send_new_event_notification,
        ):
            with self.subTest(sender=sender.name):
                self.http.reset_mock()
                event = self.event_for_send(
                    discord_confirm_attendance_channel_id="",
                    discord_profile_reminder_channel_id="",
                    discord_new_event_channel_id="",
                )
                sender(event.pk)
                self.assertEqual(len(self.posts()), 1)
                self.assertEqual(
                    self.posts()[0].args[1],
                    f"{DISCORD_API_BASE}/channels/{CHANNEL}/messages",
                )

    def test_unsupported_channel_makes_no_post(self) -> None:
        self.channel_type = 2
        for sender in (
            send_attendance_reminder,
            send_profile_reminder,
            send_new_event_notification,
        ):
            sender(self.event_for_send().pk)
        fire_event_reminder(self.event_for_send().pk, "signup_reminder")
        self.assertEqual(self.posts(), [])
        self.assertFalse(DiscordMessageLog.objects.exists())

    def test_notice_routes_by_channel_type_and_records_starter_message(self) -> None:
        for kind, route in ((0, "messages"), (5, "messages"), (15, "threads")):
            with self.subTest(kind=kind):
                self.channel_type = kind
                self.http.reset_mock()
                event = self.event_for_send(
                    discord_post_signups=True,
                    discord_post_signups_channel_id=SIGNUP_CHANNEL,
                    discord_announcement=True,
                )
                send_event_announcement(event.pk)
                self.assertEqual(
                    [post.args[1] for post in self.posts()],
                    [
                        f"{DISCORD_API_BASE}/channels/{SIGNUP_CHANNEL}/messages",
                        f"{DISCORD_API_BASE}/channels/{CHANNEL}/{route}",
                    ],
                )
                if kind == 15:
                    self.assertEqual(
                        self.posts()[1].kwargs["json"]["name"], "Synthetic Title"
                    )
                notice = DiscordEvent.objects.get(event=event).announcement
                self.assertEqual(notice.message_id, MESSAGE)

    def test_start_mention_reply_does_not_resolve_channel(self) -> None:
        event = self.event_for_send(discord_start_mention=True)
        DiscordEventMsgSignup.objects.create(
            event=event, channel_id=CHANNEL, message_id=MESSAGE, has_posted=True
        )
        EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.RSVP
        )
        send_start_mention(event.pk)
        self.assertEqual(len(self.http.call_args_list), 1)
        post = self.posts()[0]
        self.assertEqual(
            post.args[1], f"{DISCORD_API_BASE}/channels/{CHANNEL}/messages"
        )
        self.assertEqual(
            post.kwargs["json"]["message_reference"]["message_id"], MESSAGE
        )
