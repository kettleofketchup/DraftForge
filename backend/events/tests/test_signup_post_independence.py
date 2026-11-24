from itertools import product
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

from events.discord.dispatch import notify_event_announced, notify_signup_changed
from events.scheduling.registry import REMINDERS
from events.tasks import sync_discord_events


def destination_pairs(channel: str) -> list[tuple[bool, str | None]]:
    return [(False, None), (False, channel), (True, None), (True, channel)]


def event_fixture(
    signup: tuple[bool, str | None], announcement: tuple[bool, str | None]
) -> SimpleNamespace:
    return SimpleNamespace(
        pk=17,
        state="signups_open",
        discord_post_signups=signup[0],
        discord_post_signups_channel_id=signup[1],
        discord_announcement=announcement[0],
        discord_announcement_channel_id=announcement[1],
        discord_create_event=False,
    )


def sync_fixture(event: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        active_events=[vars(event)],
        existing_logs=[],
        events_with_signup=[],
        events_with_scheduled=[],
        events_with_recent_attempt=[],
    )


class SyncSignupPostEligibilityTest(SimpleTestCase):
    def test_sync_destination_matrix(self) -> None:
        for signup, announcement in product(
            destination_pairs("signup-channel"),
            destination_pairs("announcement-channel"),
        ):
            with self.subTest(signup=signup, announcement=announcement):
                event = event_fixture(signup, announcement)
                with (
                    patch(
                        "events.tasks.get_sync_discord_state",
                        return_value=sync_fixture(event),
                    ),
                    patch("events.tasks.send_event_announcement") as send,
                ):
                    sync_discord_events()
                if (signup[0] and signup[1]) or (announcement[0] and announcement[1]):
                    send.assert_called_once_with(event.pk)
                else:
                    send.assert_not_called()

    def test_sync_preserves_state_and_dedup_guards(self) -> None:
        for guard in ("state", "signup", "legacy"):
            with self.subTest(guard=guard):
                event = event_fixture((True, "signup-channel"), (False, None))
                state = sync_fixture(event)
                if guard == "state":
                    state.active_events[0]["state"] = "upcoming"
                elif guard == "signup":
                    state.events_with_signup = [event.pk]
                else:
                    state.existing_logs = [("event_announcement", event.pk)]
                with (
                    patch("events.tasks.get_sync_discord_state", return_value=state),
                    patch("events.tasks.send_event_announcement") as send,
                ):
                    sync_discord_events()
                send.assert_not_called()

    def test_timed_announcement_remains_announcement_specific(self) -> None:
        reminder = next(
            r
            for r in REMINDERS
            if r.task_name == "events.tasks.send_event_announcement"
        )
        self.assertEqual(reminder.enabled_field, "discord_announcement")


class SignupPostDispatchEligibilityTest(SimpleTestCase):
    def test_initial_dispatch_destination_matrix(self) -> None:
        for signup, announcement in product(
            destination_pairs("signup-channel"),
            destination_pairs("announcement-channel"),
        ):
            with self.subTest(signup=signup, announcement=announcement):
                event = event_fixture(signup, announcement)
                with (
                    patch(
                        "events.discord.dispatch._current_interaction_id",
                        return_value="interaction",
                    ),
                    patch("events.tasks.send_event_announcement.delay") as send,
                ):
                    notify_event_announced(event)
                if (signup[0] and signup[1]) or (announcement[0] and announcement[1]):
                    send.assert_called_once_with(event.pk, interaction_id="interaction")
                else:
                    send.assert_not_called()

    def test_update_dispatch_destination_matrix(self) -> None:
        for signup, announcement in product(
            destination_pairs("signup-channel"),
            destination_pairs("announcement-channel"),
        ):
            with self.subTest(signup=signup, announcement=announcement):
                event = event_fixture(signup, announcement)
                with (
                    patch(
                        "events.discord.dispatch._current_interaction_id",
                        return_value="interaction",
                    ),
                    patch("events.discord.dispatch.mark_dirty") as dirty,
                    patch(
                        "events.discord.dispatch.mark_pending", return_value=True
                    ) as pending,
                    patch("events.tasks.send_signup_update.apply_async") as send,
                ):
                    notify_signup_changed(event)
                if (signup[0] and signup[1]) or (announcement[0] and announcement[1]):
                    dirty.assert_called_once_with(event.pk)
                    pending.assert_called_once_with(event.pk)
                    send.assert_called_once_with(
                        (event.pk,),
                        {"interaction_id": "interaction"},
                        countdown=settings.SIGNUP_POST.debounce_seconds,
                    )
                else:
                    dirty.assert_not_called()
                    pending.assert_not_called()
                    send.assert_not_called()

    def test_update_pending_does_not_enqueue_twice(self) -> None:
        event = event_fixture((True, "signup-channel"), (False, None))
        with (
            patch("events.discord.dispatch.mark_dirty") as dirty,
            patch("events.discord.dispatch.mark_pending", return_value=False),
            patch("events.tasks.send_signup_update.apply_async") as send,
        ):
            notify_signup_changed(event)
        dirty.assert_called_once_with(event.pk)
        send.assert_not_called()
