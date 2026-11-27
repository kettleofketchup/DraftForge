"""Pure scheduled-event and start-mention builders shared by tasks and preview."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from app.models import CustomUser
from discordbot.models import DiscordEventMsgSignup
from events.constants import EventState, SignupStatus, StartMentionScope
from events.discord.embeds import (
    build_scheduled_event_payload,
    build_scheduled_event_sync_payload,
)
from events.models import Event, EventSignup
from events.start_mention import (
    MentionChunk,
    StartMentionPreview,
    build_start_mention_header,
    build_start_mention_messages,
    start_mention_payload,
)
from events.tasks import send_start_mention
from events.tests._internal_client_orm import (
    _get_event_for_task_orm,
    _get_event_signups_orm,
)
from events.tests.test_discord_tasks import _DiscordTaskTestCase, _ok_response

START = datetime(2030, 1, 5, 18, 0, tzinfo=timezone.utc)
TITLE_130 = (
    "Sunday Turbo Tournament with a deliberately long name that runs well past "
    "the one hundred character Discord limit for scheduled ev"
)


class ScheduledEventBuilderTest(_DiscordTaskTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ev = self.make_event(
            name=TITLE_130,
            description="Snacks & <b>drinks</b>",
            scheduled_at=START,
            max_players=10,
        )

    def _shapes(self) -> list[Any]:
        return [Event.objects.get(pk=self.ev.pk), _get_event_for_task_orm(self.ev.pk)]

    def test_create_payload_matches_literal_for_model_and_schema(self) -> None:
        for event in self._shapes():
            with self.subTest(shape=type(event).__name__):
                self.assertEqual(
                    build_scheduled_event_payload(event),
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

    def test_create_payload_custom_title_description_and_end(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(
            discord_event_title="Custom Title",
            discord_event_description="x" * 1200,
            ends_at=datetime(2030, 1, 5, 20, 30, tzinfo=timezone.utc),
        )
        for event in self._shapes():
            with self.subTest(shape=type(event).__name__):
                payload = build_scheduled_event_payload(event)
                self.assertEqual(payload["name"], "Custom Title")
                self.assertEqual(payload["description"], "x" * 1000)
                self.assertEqual(
                    payload["scheduled_end_time"], "2030-01-05T20:30:00+00:00"
                )

    def test_sync_payload_matches_literal_for_model_and_schema(self) -> None:
        for event in self._shapes():
            with self.subTest(shape=type(event).__name__):
                self.assertEqual(
                    build_scheduled_event_sync_payload(event, 3, 1),
                    {
                        "description": (
                            "Snacks &amp; <b>drinks</b>\n\n"
                            "Signups: 3/10 | Confirmed: 1"
                        )
                    },
                )

    def test_sync_payload_unlimited(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(max_players=None, description="")
        for event in self._shapes():
            with self.subTest(shape=type(event).__name__):
                self.assertEqual(
                    build_scheduled_event_sync_payload(event, 0, 0),
                    {"description": "\n\nSignups: 0/∞ | Confirmed: 0"},
                )

    def test_builders_do_not_touch_network_or_db(self) -> None:
        event = Event.objects.get(pk=self.ev.pk)
        with (
            patch("events.tasks.req") as mock_req,
            self.assertNumQueries(0),
        ):
            build_scheduled_event_payload(event)
            build_scheduled_event_sync_payload(event, 1, 1)
        mock_req.assert_not_called()


class StartMentionBuilderTest(_DiscordTaskTestCase):
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

    def _add_users(self, with_ids: int, without_ids: int) -> None:
        for i in range(with_ids):
            user = CustomUser.objects.create_user(
                username=f"pm_{i}", password="x", discordId=str(200000000000000000 + i)
            )
            EventSignup.objects.create(
                event=self.ev, user=user, status=SignupStatus.RSVP
            )
        for i in range(without_ids):
            user = CustomUser.objects.create_user(username=f"pm_none_{i}", password="x")
            EventSignup.objects.create(
                event=self.ev, user=user, status=SignupStatus.RSVP
            )

    def test_header_uses_custom_title_truncated_to_100(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(discord_event_title="T" * 150)
        for event in (
            Event.objects.get(pk=self.ev.pk),
            _get_event_for_task_orm(self.ev.pk),
        ):
            with self.subTest(shape=type(event).__name__):
                self.assertEqual(
                    build_start_mention_header(event),
                    f"{'T' * 100} starts <t:1893866400:R>.",
                )

    def test_reply_reference_keeps_fail_if_not_exists_false(self) -> None:
        chunk = MentionChunk(content="hi <@1>", user_ids=["1"])
        self.assertEqual(
            start_mention_payload(chunk, "9"),
            {
                "content": "hi <@1>",
                "embeds": [],
                "allowed_mentions": {"users": ["1"]},
                "message_reference": {"message_id": "9", "fail_if_not_exists": False},
            },
        )
        self.assertIsNone(start_mention_payload(chunk, None)["message_reference"])

    @patch("discordbot.utils._rate_limited_request")
    def test_messages_match_task_bodies_for_model_and_schema(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.return_value = _ok_response({"id": "m"})
        self._add_users(85, 2)
        signups = _get_event_signups_orm(self.ev.pk)

        send_start_mention(self.ev.pk)
        sent = [
            c.kwargs["json"] for c in mock_req.call_args_list if c.args[0] == "POST"
        ]

        for event in (
            Event.objects.get(pk=self.ev.pk),
            _get_event_for_task_orm(self.ev.pk),
        ):
            with self.subTest(shape=type(event).__name__):
                preview = build_start_mention_messages(event, signups)
                self.assertIsInstance(preview, StartMentionPreview)
                self.assertEqual(preview.mentioned, 85)
                self.assertEqual(preview.skipped_no_discord_id, 2)
                self.assertEqual(
                    preview.header, "Weekly Inhouse starts <t:1893866400:R>."
                )
                self.assertEqual(len(preview.chunks), 2)
                bodies = []
                for chunk in preview.chunks:
                    payload = start_mention_payload(chunk, "5550003")
                    bodies.append(
                        {
                            "embeds": payload["embeds"],
                            "content": payload["content"],
                            "allowed_mentions": payload["allowed_mentions"],
                            "message_reference": payload["message_reference"],
                        }
                    )
                self.assertEqual(bodies, sent)

    def test_messages_scope_main_skips_waitlist(self) -> None:
        self._add_users(2, 0)
        waiter = CustomUser.objects.create_user(
            username="waiter", password="x", discordId="300000000000000001"
        )
        EventSignup.objects.create(
            event=self.ev, user=waiter, status=SignupStatus.WAITLISTED
        )
        Event.objects.filter(pk=self.ev.pk).update(
            discord_start_mention_scope=StartMentionScope.MAIN
        )
        preview = build_start_mention_messages(
            _get_event_for_task_orm(self.ev.pk), _get_event_signups_orm(self.ev.pk)
        )
        self.assertEqual(preview.mentioned, 2)
        self.assertEqual(
            preview.chunks[0].user_ids, ["200000000000000000", "200000000000000001"]
        )
