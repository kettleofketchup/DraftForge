import json
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.utils import timezone as tz

from events.discord import embeds
from events.discord.embeds import (
    SITE_URL,
    _build_reminder_embed,
    _signup_counts,
    build_announcement_embeds,
    build_announcement_v2,
    build_attendance_reminder_embed,
    build_new_event_embed,
    build_profile_reminder_embed,
    build_signup_reminder_embed,
    build_subscriber_dm_embed,
)
from events.models import Event, EventRepeater, normalize_event_fields
from events.schemas import EventSignupSchema
from events.tests.base import EventTestCase

Builder = Callable[..., Any]


def _reminder(event: Event, **kwargs: Any) -> Any:
    return _build_reminder_embed(
        event, title="t", description="d", color=1, include_buttons=True, **kwargs
    )


BUILDERS: dict[str, Builder] = {
    "_signup_counts": _signup_counts,
    "build_announcement_embeds": build_announcement_embeds,
    "build_announcement_v2": build_announcement_v2,
    "_build_reminder_embed": _reminder,
    "build_signup_reminder_embed": build_signup_reminder_embed,
    "build_attendance_reminder_embed": build_attendance_reminder_embed,
    "build_profile_reminder_embed": build_profile_reminder_embed,
    "build_subscriber_dm_embed": build_subscriber_dm_embed,
}


def _signups() -> list[EventSignupSchema]:
    return [
        EventSignupSchema(id=1, event=1, user=1, username="Alice", status="confirmed"),
        EventSignupSchema(id=2, event=1, user=2, username="Bob", status="rsvp"),
        EventSignupSchema(id=3, event=1, user=3, username="Cara", status="tentative"),
        EventSignupSchema(id=4, event=1, user=4, username="Dan", status="cancelled"),
        EventSignupSchema(
            id=5,
            event=1,
            user=5,
            username="Eve",
            status="waitlisted",
            waitlist_position=1,
        ),
    ]


class SignupsInjectionTest(EventTestCase):
    def test_builders_signups_injected_equals_patched_loopback(self) -> None:
        signups = _signups()
        for name, build in BUILDERS.items():
            with self.subTest(builder=name):
                with patch.object(
                    embeds, "get_event_signups", return_value=signups
                ) as loopback:
                    default = build(self.event)
                    self.assertGreater(loopback.call_count, 0)
                with patch.object(
                    embeds, "get_event_signups", return_value=signups
                ) as loopback:
                    injected = build(self.event, signups=signups)
                    self.assertEqual(loopback.call_count, 0)
                self.assertEqual(default, injected)

    def test_signups_none_still_loops_back(self) -> None:
        with patch.object(embeds, "get_event_signups", return_value=[]) as loopback:
            build_announcement_v2(self.event)
        loopback.assert_called_once_with(self.event.pk)


class UnsavedEventUrlTest(EventTestCase):
    def _unsaved(self) -> Event:
        return Event(
            organization=self.org,
            name="x",
            scheduled_at=tz.now() + timedelta(days=3),
            timezone="UTC",
        )

    def test_unsaved_event_has_no_events_none_url(self) -> None:
        event = self._unsaved()
        self.assertIsNone(event.pk)
        cases: dict[str, Callable[[], Any]] = {
            "build_announcement_v2": lambda: build_announcement_v2(event, signups=[]),
            "build_new_event_embed": lambda: build_new_event_embed(event),
            "build_subscriber_dm_embed": lambda: build_subscriber_dm_embed(
                event, signups=[]
            ),
            "build_signup_reminder_embed": lambda: build_signup_reminder_embed(
                event, signups=[]
            ),
            "build_attendance_reminder_embed": lambda: build_attendance_reminder_embed(
                event, signups=[]
            ),
            "build_profile_reminder_embed": lambda: build_profile_reminder_embed(
                event, signups=[]
            ),
        }
        with patch.object(embeds, "get_event_signups") as loopback:
            for name, build in cases.items():
                with self.subTest(builder=name):
                    dumped = json.dumps(build())
                    self.assertNotIn("/events/None", dumped)
                    self.assertIn(json.dumps(f"{SITE_URL}/events")[1:-1], dumped)
        self.assertEqual(loopback.call_count, 0)


class NormalizeEventFieldsTest(EventTestCase):
    DESCRIPTION = "Snacks & drinks <b>x</b><script>y</script>"

    def _make(self, model: type[Event] | type[EventRepeater]) -> Event | EventRepeater:
        if model is Event:
            return Event(
                organization=self.org,
                name="Norm",
                description=self.DESCRIPTION,
                scheduled_at=tz.now() + timedelta(days=3),
                created_by=self.admin,
            )
        return EventRepeater(
            organization=self.org,
            name="Norm Series",
            description=self.DESCRIPTION,
            frequency="weekly",
            day_of_week=3,
            time_of_day="19:00:00",
            starts_at="2026-01-01",
        )

    def test_normalize_event_fields_matches_save(self) -> None:
        models: Sequence[type[Event] | type[EventRepeater]] = (Event, EventRepeater)
        for model in models:
            with self.subTest(model=model.__name__):
                in_memory = self._make(model)
                normalize_event_fields(in_memory)
                self.assertIsNone(in_memory.pk)

                saved = self._make(model)
                saved.save()
                refetched = model.objects.get(pk=saved.pk)

                self.assertEqual(in_memory.description, refetched.description)
                self.assertNotEqual(in_memory.description, self.DESCRIPTION)
                self.assertIn("&amp;", in_memory.description)

    def test_normalize_event_fields_skips_empty_description(self) -> None:
        event = self._make(Event)
        event.description = ""
        normalize_event_fields(event)
        self.assertEqual(event.description, "")
