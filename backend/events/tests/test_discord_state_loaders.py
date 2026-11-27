from contextlib import ExitStack
from unittest.mock import patch

from discordbot.models import DiscordMessageLog
from discordbot.schemas import DiscordEventStateSchema
from events.discord.state import (
    latest_message_log_discord_id,
    load_discord_event_state,
    load_signups_for_embed,
    message_log_exists,
    signup_list_queryset,
)
from events.schemas import EventSignupSchema
from events.tests.test_discord_state_golden import HEADERS, DiscordStateFixture


def _boom(*args: object, **kwargs: object) -> None:
    raise AssertionError("loader made an HTTP call")


class DiscordStateLoaderTest(DiscordStateFixture):
    def test_load_signups_for_embed_matches_endpoint(self) -> None:
        event = self.seed_signups()
        endpoint = self.client.get(
            "/api/events/signups/", {"event": event.pk}, **HEADERS
        ).json()

        loaded = load_signups_for_embed(event.pk)

        self.assertEqual(
            [s.model_dump(mode="json") for s in loaded],
            [
                EventSignupSchema.model_validate(r).model_dump(mode="json")
                for r in endpoint
            ],
        )
        self.assertEqual(
            [(s.display_name, s.status, s.line_rank) for s in loaded],
            [
                ("Guildy", "confirmed", 1),
                ("RsvpNick", "rsvp", 2),
                ("Waiter", "waitlisted", 3),
                ("Gone", "cancelled", None),
            ],
        )

    def test_signup_list_queryset_filters_and_ranks(self) -> None:
        event = self.seed_signups()
        other = self.make_event(name="Other Event")
        self.assertEqual(signup_list_queryset(other.pk, for_list=True).count(), 0)
        self.assertEqual(signup_list_queryset(str(event.pk), for_list=True).count(), 4)
        self.assertGreaterEqual(signup_list_queryset(None, for_list=False).count(), 4)
        self.assertEqual(
            [s.line_rank for s in signup_list_queryset(event.pk, for_list=True)],
            [1, 2, 3, None],
        )
        self.assertFalse(
            hasattr(signup_list_queryset(event.pk, for_list=False).first(), "line_rank")
        )

    def test_load_discord_event_state_matches_endpoint(self) -> None:
        event, de = self.seed_discord_event()
        bare = self.make_event(name="Bare Event")

        for pk in (event.pk, bare.pk):
            with self.subTest(event=pk):
                endpoint = self.client.get(
                    f"/api/internal/discord/event-state/{pk}/", **HEADERS
                ).json()
                state = load_discord_event_state(pk)
                self.assertIsInstance(state, DiscordEventStateSchema)
                self.assertEqual(
                    state, DiscordEventStateSchema.model_validate(endpoint)
                )

        state = load_discord_event_state(event.pk)
        self.assertEqual(state.discord_event_pk, de.pk)
        self.assertEqual(state.fired_actions, ["start_mention", "signup_reminder"])
        self.assertTrue(state.has_dms)
        self.assertEqual(state.signup_thread_id, "880002")
        self.assertEqual(state.signup_channel_type, "forum")

    def test_message_log_exists_matches_endpoint(self) -> None:
        for source_id, success in ((101, None), (102, True), (103, False)):
            DiscordMessageLog.objects.create(
                channel_id="1",
                embed_data={},
                source="event_reminder",
                source_id=source_id,
                success=success,
            )

        self.assertEqual(
            [message_log_exists("event_reminder", i) for i in (101, 102, 103, 104)],
            [True, True, False, False],
        )

    def test_latest_message_log_discord_id_matches_endpoint(self) -> None:
        rows = [
            ("create_discord_event", 201, "sent", True),
            ("create_discord_event", 202, "failed", False),
            ("create_discord_event", 203, "pending", None),
            ("event_reminder", 204, "other-source", True),
        ]
        for source, source_id, message_id, success in rows:
            DiscordMessageLog.objects.create(
                channel_id="1",
                embed_data={},
                source=source,
                source_id=source_id,
                discord_message_id=message_id,
                success=success,
            )

        for source_id in (201, 202, 203, 204, 205):
            with self.subTest(source_id=source_id):
                endpoint = self.client.get(
                    "/api/internal/discord/message-logs/",
                    {
                        "source": "create_discord_event",
                        "source_id": source_id,
                        "success": "true",
                        "limit": 1,
                    },
                    **HEADERS,
                ).json()
                expected = endpoint[0]["discord_message_id"] if endpoint else None
                self.assertEqual(
                    latest_message_log_discord_id("create_discord_event", source_id),
                    expected,
                )
        self.assertEqual(
            latest_message_log_discord_id("create_discord_event", 201), "sent"
        )
        self.assertIsNone(latest_message_log_discord_id("create_discord_event", 202))

    def test_loaders_do_no_http(self) -> None:
        event, _ = self.seed_discord_event()
        signup_event = self.seed_signups()
        with ExitStack() as stack:
            for target in (
                "requests.request",
                "requests.get",
                "requests.post",
                "requests.Session.request",
                "app.internal_client.transport.get",
                "app.internal_client.transport.api_get",
                "app.internal_client.transport.post",
            ):
                stack.enter_context(patch(target, side_effect=_boom))
            load_signups_for_embed(signup_event.pk)
            load_discord_event_state(event.pk)
            message_log_exists("event_reminder", 1)
            latest_message_log_discord_id("create_discord_event", 1)
