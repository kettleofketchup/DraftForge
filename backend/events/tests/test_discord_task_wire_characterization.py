"""Literal wire bodies of the scheduled-event and start-mention tasks."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from app.models import CustomUser
from discordbot.models import DiscordEventMsgSignup, DiscordMessageLog
from events.constants import EventState, SignupStatus, StartMentionScope
from events.models import Event, EventSignup
from events.tasks import (
    create_discord_scheduled_event,
    send_start_mention,
    sync_discord_event_signups,
)
from events.tests.test_discord_tasks import _DiscordTaskTestCase, _ok_response

START = datetime(2030, 1, 5, 18, 0, tzinfo=timezone.utc)
TITLE_130 = (
    "Sunday Turbo Tournament with a deliberately long name that runs well past "
    "the one hundred character Discord limit for scheduled ev"
)
GUILD = "734185035623825559"


class ScheduledEventWireTest(_DiscordTaskTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = GUILD
        self.org.save()
        self.ev = self.make_event(
            name=TITLE_130,
            description="Snacks & <b>drinks</b>",
            scheduled_at=START,
            discord_create_event=True,
            discord_sync_signups=True,
            max_players=10,
        )

    @patch("events.tasks.req.post")
    def test_create_scheduled_event_json_literal(self, mock_post: MagicMock) -> None:
        self.assertEqual(len(TITLE_130), 130)
        mock_post.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={"id": "888"})
        )

        create_discord_scheduled_event(self.ev.pk)

        mock_post.assert_called_once()
        self.assertEqual(
            mock_post.call_args.args[0],
            f"https://discord.com/api/v10/guilds/{GUILD}/scheduled-events",
        )
        self.assertEqual(
            mock_post.call_args.kwargs["json"],
            {
                "name": TITLE_130,
                "description": "Snacks &amp; <b>drinks</b>",
                "scheduled_start_time": "2030-01-05T18:00:00+00:00",
                "scheduled_end_time": "2030-01-05T21:00:00+00:00",
                "privacy_level": 2,
                "entity_type": 3,
                "entity_metadata": {"location": "DraftForge"},
            },
        )

    @patch("events.tasks.req.post")
    def test_create_scheduled_event_custom_title_and_end_literal(
        self, mock_post: MagicMock
    ) -> None:
        Event.objects.filter(pk=self.ev.pk).update(
            discord_event_title="Custom Title",
            discord_event_description="Custom & description",
            ends_at=datetime(2030, 1, 5, 20, 30, tzinfo=timezone.utc),
        )
        mock_post.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={"id": "888"})
        )

        create_discord_scheduled_event(self.ev.pk)

        self.assertEqual(
            mock_post.call_args.kwargs["json"],
            {
                "name": "Custom Title",
                "description": "Custom & description",
                "scheduled_start_time": "2030-01-05T18:00:00+00:00",
                "scheduled_end_time": "2030-01-05T20:30:00+00:00",
                "privacy_level": 2,
                "entity_type": 3,
                "entity_metadata": {"location": "DraftForge"},
            },
        )

    @patch("events.tasks.req.patch")
    @patch("events.tasks.get_first_message_log")
    def test_sync_scheduled_event_json_literal(
        self, mock_first_log: MagicMock, mock_patch: MagicMock
    ) -> None:
        mock_first_log.return_value = MagicMock(discord_message_id="777")
        mock_patch.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={})
        )
        for i, status in enumerate(
            [SignupStatus.RSVP, SignupStatus.RSVP, SignupStatus.CONFIRMED]
        ):
            EventSignup.objects.create(
                event=self.ev,
                user=CustomUser.objects.create_user(username=f"sync_{i}", password="x"),
                status=status,
            )

        sync_discord_event_signups(self.ev.pk)

        mock_patch.assert_called_once()
        self.assertEqual(
            mock_patch.call_args.args[0],
            f"https://discord.com/api/v10/guilds/{GUILD}/scheduled-events/777",
        )
        self.assertEqual(
            mock_patch.call_args.kwargs["json"],
            {
                "description": (
                    "Snacks &amp; <b>drinks</b>\n\nSignups: 3/10 | Confirmed: 1"
                )
            },
        )

    @patch("events.tasks.req.patch")
    @patch("events.tasks.get_first_message_log")
    def test_sync_scheduled_event_unlimited_literal(
        self, mock_first_log: MagicMock, mock_patch: MagicMock
    ) -> None:
        Event.objects.filter(pk=self.ev.pk).update(max_players=None, description="")
        mock_first_log.return_value = MagicMock(discord_message_id="777")
        mock_patch.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value={})
        )

        sync_discord_event_signups(self.ev.pk)

        self.assertEqual(
            mock_patch.call_args.kwargs["json"],
            {"description": "\n\nSignups: 0/∞ | Confirmed: 0"},
        )


class StartMentionWireTest(_DiscordTaskTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ev = self.make_event(
            name="Weekly Inhouse",
            scheduled_at=START,
            state=EventState.ROLL_CALL,
            discord_start_mention=True,
            discord_start_mention_scope=StartMentionScope.ALL_ACTIVE,
        )
        DiscordEventMsgSignup.objects.create(
            event=self.ev,
            channel_id="5550001",
            thread_id="5550002",
            message_id="5550003",
            has_posted=True,
        )
        for name, discord_id, status in [
            ("alpha", "100000000000000001", SignupStatus.RSVP),
            ("bravo", "100000000000000002", SignupStatus.RSVP),
            ("charlie", "100000000000000003", SignupStatus.WAITLISTED),
            ("nodiscord", None, SignupStatus.RSVP),
        ]:
            user = CustomUser.objects.create_user(
                username=name, password="x", discordId=discord_id
            )
            EventSignup.objects.create(event=self.ev, user=user, status=status)

    def _posts(self, mock_req: MagicMock) -> list[dict[str, Any]]:
        return [
            {"url": c.args[1], "json": c.kwargs["json"]}
            for c in mock_req.call_args_list
            if c.args[0] == "POST"
        ]

    @patch("discordbot.utils._rate_limited_request")
    def test_start_mention_bodies_literal(self, mock_req: MagicMock) -> None:
        cases = [
            (
                StartMentionScope.ALL_ACTIVE,
                "Weekly Inhouse starts <t:1893866400:R>.\n"
                "<@100000000000000001> <@100000000000000002> <@100000000000000003>",
                ["100000000000000001", "100000000000000002", "100000000000000003"],
                {
                    "type": "start_mention",
                    "mentioned": 3,
                    "skipped_no_discord_id": 1,
                    "chunks": 1,
                },
            ),
            (
                StartMentionScope.MAIN,
                "Weekly Inhouse starts <t:1893866400:R>.\n"
                "<@100000000000000001> <@100000000000000002>",
                ["100000000000000001", "100000000000000002"],
                {
                    "type": "start_mention",
                    "mentioned": 2,
                    "skipped_no_discord_id": 1,
                    "chunks": 1,
                },
            ),
        ]
        for scope, content, users, embed_data in cases:
            with self.subTest(scope=scope):
                mock_req.reset_mock()
                mock_req.return_value = _ok_response({"id": "m1"})
                DiscordMessageLog.objects.filter(source="start_mention").delete()
                Event.objects.filter(pk=self.ev.pk).update(
                    discord_start_mention_scope=scope
                )

                send_start_mention(self.ev.pk)

                self.assertEqual(
                    self._posts(mock_req),
                    [
                        {
                            "url": "https://discord.com/api/v10/channels/5550002/messages",
                            "json": {
                                "embeds": [],
                                "content": content,
                                "allowed_mentions": {"users": users},
                                "message_reference": {
                                    "message_id": "5550003",
                                    "fail_if_not_exists": False,
                                },
                            },
                        }
                    ],
                )
                row = DiscordMessageLog.objects.get(
                    source="start_mention", source_id=self.ev.pk
                )
                self.assertEqual(row.embed_data, embed_data)

    @patch("discordbot.utils._rate_limited_request")
    def test_start_mention_manual_fire_bypasses_toggle(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.return_value = _ok_response({"id": "m1"})
        Event.objects.filter(pk=self.ev.pk).update(discord_start_mention=False)

        send_start_mention(self.ev.pk)
        self.assertEqual(self._posts(mock_req), [])

        send_start_mention(self.ev.pk, fired_by_user_id=self.admin.pk)

        self.assertEqual(
            self._posts(mock_req),
            [
                {
                    "url": "https://discord.com/api/v10/channels/5550002/messages",
                    "json": {
                        "embeds": [],
                        "content": (
                            "Weekly Inhouse starts <t:1893866400:R>.\n"
                            "<@100000000000000001> <@100000000000000002> "
                            "<@100000000000000003>"
                        ),
                        "allowed_mentions": {
                            "users": [
                                "100000000000000001",
                                "100000000000000002",
                                "100000000000000003",
                            ]
                        },
                        "message_reference": {
                            "message_id": "5550003",
                            "fail_if_not_exists": False,
                        },
                    },
                }
            ],
        )
