from collections.abc import Callable
from typing import Any

from django.test import SimpleTestCase

from events.discord import (
    attendance_reminder_channel,
    new_event_channel,
    profile_reminder_channel,
    reminder_channel,
)
from events.models import Event
from events.schemas import EventTaskSchema

OWN = "111111111111111111"
ANNOUNCE = "222222222222222222"

RESOLVERS: dict[str, Callable[[Any], str]] = {
    "discord_confirm_attendance_channel_id": attendance_reminder_channel,
    "discord_profile_reminder_channel_id": profile_reminder_channel,
    "discord_new_event_channel_id": new_event_channel,
}


def _event(**kwargs: Any) -> Event:
    return Event(**kwargs)


def _schema(**kwargs: Any) -> EventTaskSchema:
    return EventTaskSchema.model_construct(**kwargs)


class DiscordChannelResolverTests(SimpleTestCase):
    BUILDERS: tuple[Callable[..., Any], ...] = (_event, _schema)

    def test_own_channel_wins(self) -> None:
        for build in self.BUILDERS:
            for field, resolve in RESOLVERS.items():
                with self.subTest(build=build.__name__, field=field):
                    obj = build(
                        **{field: OWN, "discord_announcement_channel_id": ANNOUNCE}
                    )
                    self.assertEqual(resolve(obj), OWN)

    def test_blank_falls_back_to_announcement(self) -> None:
        for build in self.BUILDERS:
            for field, resolve in RESOLVERS.items():
                with self.subTest(build=build.__name__, field=field):
                    obj = build(
                        **{field: "", "discord_announcement_channel_id": ANNOUNCE}
                    )
                    self.assertEqual(resolve(obj), ANNOUNCE)

    def test_new_event_falls_back_with_announcement_off(self) -> None:
        for build in self.BUILDERS:
            with self.subTest(build=build.__name__):
                obj = build(
                    discord_announcement=False,
                    discord_new_event_channel_id="",
                    discord_announcement_channel_id=ANNOUNCE,
                )
                self.assertEqual(new_event_channel(obj), ANNOUNCE)

    def test_all_blank_returns_empty(self) -> None:
        for build in self.BUILDERS:
            for field, resolve in RESOLVERS.items():
                with self.subTest(build=build.__name__, field=field):
                    obj = build(**{field: "", "discord_announcement_channel_id": ""})
                    self.assertEqual(resolve(obj), "")

    def test_reminder_channel_routes_each_type(self) -> None:
        for build in self.BUILDERS:
            with self.subTest(build=build.__name__):
                obj = build(
                    discord_announcement_channel_id=ANNOUNCE,
                    discord_confirm_attendance_channel_id="333333333333333333",
                    discord_profile_reminder_channel_id="444444444444444444",
                    discord_new_event_channel_id="555555555555555555",
                )
                self.assertEqual(
                    reminder_channel(obj, "confirm_attendance"), "333333333333333333"
                )
                self.assertEqual(
                    reminder_channel(obj, "profile_reminder"), "444444444444444444"
                )
                self.assertEqual(reminder_channel(obj, "signup_reminder"), ANNOUNCE)

    def test_reminder_channel_blank_falls_back(self) -> None:
        obj = _event(discord_announcement_channel_id=ANNOUNCE)
        for reminder_type in ("confirm_attendance", "profile_reminder"):
            with self.subTest(reminder_type=reminder_type):
                self.assertEqual(reminder_channel(obj, reminder_type), ANNOUNCE)
