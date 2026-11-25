"""Discord previews for unsaved events and series: create, one-off and repeaters."""

import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import datetime, time, timedelta
from datetime import timezone as dt_tz
from typing import Any
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz

from app.models import CustomUser
from discordbot.models import DiscordEvent, DiscordEventLog, DiscordMessageLog
from events.constants import EventState, RepeatFrequency, SignupStatus
from events.discord.preview import build_discord_preview
from events.discord.preview_schema import (
    DiscordPreviewResponse,
    EventContext,
    NewEventContext,
    NewRepeaterContext,
    PreviewContext,
    PreviewKind,
    RepeaterContext,
    SeriesOneOffContext,
)
from events.models import Event, EventRepeater
from events.services import _today
from events.tests.test_discord_preview import ALL_KINDS, _PreviewTestCase
from org.models import Organization

SIGNUP_CHANNEL = "100000000000000771"
ANNOUNCE_CHANNEL = "100000000000000772"
NEW_EVENT_VALUES: dict[str, Any] = {
    "name": "Fresh Inhouse",
    "description": "Bring & share",
    "scheduled_at": "2031-03-01T19:00:00Z",
    "timezone": "UTC",
    "discord_create_event": True,
    "discord_post_signups": True,
    "discord_post_signups_channel_id": SIGNUP_CHANNEL,
    "discord_announcement": True,
    "discord_announcement_channel_id": ANNOUNCE_CHANNEL,
    "discord_start_mention": True,
}


class _ContextTestCase(_PreviewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.today = _today()
        self.series = EventRepeater.objects.create(
            organization=self.org,
            name="Daily Series",
            description="Series & friends",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=self.today - timedelta(days=1),
            generate_days_ahead=14,
            created_by=self.admin,
            discord_event_title="Series Title",
            discord_announcement=True,
            discord_announcement_channel_id=ANNOUNCE_CHANNEL,
            discord_post_signups=True,
            discord_post_signups_channel_id=SIGNUP_CHANNEL,
            discord_notify_new_events=True,
        )

    def other_org(self) -> Organization:
        owner = CustomUser.objects.create_user(username="ctx_other_owner", password="x")
        return Organization.objects.create(name="Other Org", owner=owner)

    def pv(
        self,
        kind: PreviewKind,
        context: PreviewContext,
        values: dict[str, Any] | None = None,
        *,
        user: CustomUser | None = None,
        open_signups: bool = False,
    ) -> DiscordPreviewResponse:
        return build_discord_preview(
            kind, context, values or {}, user or self.admin, open_signups=open_signups
        )

    def new_event(self) -> NewEventContext:
        return NewEventContext(type="new_event", organization_id=self.org.pk)

    def one_off(self, repeater: EventRepeater | None = None) -> SeriesOneOffContext:
        return SeriesOneOffContext(
            type="series_one_off", repeater_id=(repeater or self.series).pk
        )

    def series_ctx(self, repeater: EventRepeater | None = None) -> RepeaterContext:
        return RepeaterContext(
            type="repeater", repeater_id=(repeater or self.series).pk
        )

    def new_repeater(self) -> NewRepeaterContext:
        return NewRepeaterContext(type="new_repeater", organization_id=self.org.pk)

    def series_event(self, days: int, state: str = EventState.UPCOMING) -> Event:
        return self.make_event(
            name="Daily Series",
            event_repeater=self.series,
            scheduled_at=tz.now() + timedelta(days=days),
            state=state,
        )

    def new_repeater_values(self, **extra: Any) -> dict[str, Any]:
        return {
            "name": "Brand New Series",
            "frequency": RepeatFrequency.DAILY,
            "time_of_day": "20:00",
            "starts_at": self.today.isoformat(),
            "timezone": "UTC",
            "discord_create_event": True,
            **extra,
        }


class UnsavedSafetyTest(_ContextTestCase):
    def test_new_event_lists_no_other_events_signups(self) -> None:
        for kind in ("start_mention", "signup_post", "announcement_notice"):
            with self.subTest(kind=kind):
                response = self.pv(kind, self.new_event(), NEW_EVENT_VALUES)
                self.assertEqual(response.status, "ok")
                self.assertEqual(response.mentions.users, {})
                dumped = response.model_dump_json()
                for name in ("alpha", "bravo", "charlie", "100000000000000001"):
                    self.assertNotIn(name, dumped)
        mention = self.pv("start_mention", self.new_event(), NEW_EVENT_VALUES)
        self.assertEqual(mention.messages, [])
        self.assertIn("no_recipients", mention.gate.reasons)

    def test_unsaved_payloads_contain_no_events_none(self) -> None:
        contexts: list[tuple[PreviewContext, dict[str, Any]]] = [
            (self.new_event(), NEW_EVENT_VALUES),
            (self.one_off(), {"scheduled_at": "2031-03-02T19:00:00Z"}),
            (self.new_repeater(), self.new_repeater_values()),
        ]
        for context, values in contexts:
            for kind in ALL_KINDS:
                with self.subTest(context=context.type, kind=kind):
                    response = self.pv(kind, context, values)
                    self.assertEqual(response.status, "ok")
                    self.assertFalse(response.saved)
                    self.assertIn("unsaved_links", response.notes)
                    self.assertNotIn(
                        "/events/None", json.dumps(response.model_dump(mode="json"))
                    )

    def test_new_event_missing_scheduled_at_needs_input(self) -> None:
        values = {k: v for k, v in NEW_EVENT_VALUES.items() if k != "scheduled_at"}
        response = self.pv("signup_post", self.new_event(), values)
        self.assertEqual(response.status, "needs_input")
        self.assertEqual(response.missing, ["scheduled_at"])
        self.assertEqual(response.messages, [])

    def test_new_event_blank_name_needs_input(self) -> None:
        response = self.pv(
            "signup_post", self.new_event(), {**NEW_EVENT_VALUES, "name": "  "}
        )
        self.assertEqual(response.status, "needs_input")
        self.assertEqual(response.missing, ["name"])

    def test_one_off_missing_scheduled_at_needs_input(self) -> None:
        response = self.pv("scheduled_event", self.one_off())
        self.assertEqual(response.status, "needs_input")
        self.assertEqual(response.missing, ["scheduled_at"])

    def test_series_one_off_copies_repeater_fields(self) -> None:
        values = {"scheduled_at": "2031-03-02T19:00:00Z"}
        response = self.pv("scheduled_event", self.one_off(), values)
        self.assertEqual(response.scheduled_event.name, "Series Title")
        self.assertEqual(response.scheduled_event.description, "Series &amp; friends")
        notice = self.pv("new_event_post", self.one_off(), values)
        self.assertEqual(notice.destination.channel_id, ANNOUNCE_CHANNEL)
        self.assertEqual(notice.gate.reasons, [])
        overridden = self.pv(
            "scheduled_event",
            self.one_off(),
            {**values, "discord_event_title": "One-off Title"},
        )
        self.assertEqual(overridden.scheduled_event.name, "One-off Title")

    def test_open_signups_true_gives_signups_open_state(self) -> None:
        cases: list[tuple[PreviewContext, dict[str, Any]]] = [
            (self.new_event(), {**NEW_EVENT_VALUES, "signup_open_mode": "immediate"}),
            (
                self.one_off(),
                {
                    "scheduled_at": "2031-03-02T19:00:00Z",
                    "signup_open_mode": "immediate",
                },
            ),
        ]
        for context, values in cases:
            with self.subTest(context=context.type):
                closed = self.pv("signup_post", context, values)
                self.assertIn("state_not_signups_open", closed.gate.reasons)
                opened = self.pv("signup_post", context, values, open_signups=True)
                self.assertTrue(opened.gate.would_send, opened.gate.reasons)

    def test_open_signups_ignored_for_event_and_repeater(self) -> None:
        upcoming = self.series_event(3)
        for context in (
            EventContext(type="event", event_id=upcoming.pk),
            self.series_ctx(),
        ):
            with self.subTest(context=context.type):
                response = self.pv("signup_post", context, open_signups=True)
                self.assertIn("state_not_signups_open", response.gate.reasons)


class RepeaterContextTest(_ContextTestCase):
    def test_repeater_previews_first_upcoming_event_with_overrides_and_real_signups(
        self,
    ) -> None:
        first = self.series_event(3)
        self.series_event(5)
        self._signup(first, "series_player", "200000000000000001", SignupStatus.RSVP)
        repeater_before = list(EventRepeater.objects.filter(pk=self.series.pk).values())
        event_before = list(Event.objects.filter(pk=first.pk).values())

        response = self.pv(
            "scheduled_event",
            self.series_ctx(),
            {"discord_event_title": "Edited Title"},
        )
        self.assertTrue(response.saved)
        self.assertNotIn("unsaved_links", response.notes)
        self.assertEqual(response.scheduled_event.name, "Edited Title")
        self.assertEqual(
            datetime.fromisoformat(response.scheduled_event.scheduled_start_time),
            first.scheduled_at,
        )
        mention = self.pv("start_mention", self.series_ctx())
        self.assertEqual(
            mention.mentions.users, {"200000000000000001": "series_player"}
        )
        self.assertEqual(
            list(EventRepeater.objects.filter(pk=self.series.pk).values()),
            repeater_before,
        )
        self.assertEqual(list(Event.objects.filter(pk=first.pk).values()), event_before)

    def test_repeater_toggle_override_reaches_new_event_post(self) -> None:
        self.series_event(3)
        response = self.pv(
            "new_event_post", self.series_ctx(), {"discord_notify_new_events": False}
        )
        self.assertIn("toggle_off", response.gate.reasons)

    def test_repeater_notes_earlier_open_event(self) -> None:
        opened = self.series_event(1, state=EventState.SIGNUPS_OPEN)
        self.series_event(3)
        response = self.pv("signup_post", self.series_ctx())
        self.assertIn("next_event_already_open_not_updated", response.notes)
        self.assertEqual(
            response.note_args["scheduled_at"], opened.scheduled_at.isoformat()
        )

    def test_repeater_without_earlier_open_event_has_no_note(self) -> None:
        self.series_event(3)
        response = self.pv("signup_post", self.series_ctx())
        self.assertNotIn("next_event_already_open_not_updated", response.notes)

    def test_repeater_paused_gate(self) -> None:
        self.series_event(3)
        response = self.pv("signup_post", self.series_ctx(), {"is_active": False})
        self.assertEqual(response.status, "ok")
        self.assertEqual(response.messages, [])
        self.assertEqual(response.gate.reasons, ["series_paused"])
        self.assertFalse(response.gate.would_send)

    def test_repeater_ended_gate(self) -> None:
        yesterday = (self.today - timedelta(days=1)).isoformat()
        response = self.pv("scheduled_event", self.series_ctx(), {"ends_at": yesterday})
        self.assertEqual(response.gate.reasons, ["series_ended"])
        self.assertIsNone(response.scheduled_event)

    def test_repeater_synthesizes_only_when_no_event(self) -> None:
        response = self.pv("scheduled_event", self.series_ctx())
        self.assertFalse(response.saved)
        self.assertEqual(
            datetime.fromisoformat(response.scheduled_event.scheduled_start_time),
            datetime.combine(self.today, time(20, 0), tzinfo=dt_tz.utc),
        )
        far = (self.today + timedelta(days=3)).weekday()
        sunday_zero = (far + 1) % 7
        weekly = {
            "frequency": RepeatFrequency.WEEKLY,
            "day_of_week": sunday_zero,
            "generate_days_ahead": 1,
        }
        self.assertEqual(
            self.pv("scheduled_event", self.series_ctx(), weekly).missing, ["schedule"]
        )
        widened = self.pv(
            "scheduled_event", self.series_ctx(), {**weekly, "generate_days_ahead": 3}
        )
        self.assertEqual(
            datetime.fromisoformat(widened.scheduled_event.scheduled_start_time).date(),
            self.today + timedelta(days=3),
        )

    def test_repeater_synthesis_skips_taken_occurrence(self) -> None:
        self.make_event(
            name="Daily Series",
            event_repeater=self.series,
            scheduled_at=datetime.combine(self.today, time(20, 0), tzinfo=dt_tz.utc),
            state=EventState.SIGNUPS_OPEN,
        )
        response = self.pv("scheduled_event", self.series_ctx())
        self.assertEqual(
            datetime.fromisoformat(response.scheduled_event.scheduled_start_time),
            datetime.combine(
                self.today + timedelta(days=1), time(20, 0), tzinfo=dt_tz.utc
            ),
        )
        self.assertIn("next_event_already_open_not_updated", response.notes)

    def test_new_repeater_uses_first_occurrence(self) -> None:
        response = self.pv(
            "scheduled_event", self.new_repeater(), self.new_repeater_values()
        )
        self.assertEqual(response.status, "ok")
        self.assertEqual(response.scheduled_event.name, "Brand New Series")
        self.assertEqual(
            datetime.fromisoformat(response.scheduled_event.scheduled_start_time),
            datetime.combine(self.today, time(20, 0), tzinfo=dt_tz.utc),
        )
        reminder = self.pv(
            "signup_reminder", self.new_repeater(), self.new_repeater_values()
        )
        self.assertNotIn("not_a_series", reminder.gate.reasons)

    def test_new_repeater_without_day_needs_schedule(self) -> None:
        response = self.pv(
            "scheduled_event",
            self.new_repeater(),
            self.new_repeater_values(frequency=RepeatFrequency.WEEKLY),
        )
        self.assertEqual(response.status, "needs_input")
        self.assertEqual(response.missing, ["schedule"])

    def test_new_repeater_blank_name_needs_name(self) -> None:
        response = self.pv(
            "scheduled_event", self.new_repeater(), self.new_repeater_values(name="")
        )
        self.assertEqual(response.missing, ["name"])


class ContextAccessTest(_ContextTestCase):
    def test_other_org_repeater_permission_denied(self) -> None:
        other = EventRepeater.objects.create(
            organization=self.other_org(),
            name="Other Series",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(20, 0),
            starts_at=self.today,
        )
        for context in (self.one_off(other), self.series_ctx(other)):
            with (
                self.subTest(context=context.type),
                self.assertRaises(PermissionDenied),
            ):
                self.pv(
                    "signup_post", context, {"scheduled_at": "2031-03-02T19:00:00Z"}
                )

    def test_other_org_organization_permission_denied(self) -> None:
        org_id = self.other_org().pk
        for context in (
            NewEventContext(type="new_event", organization_id=org_id),
            NewRepeaterContext(type="new_repeater", organization_id=org_id),
        ):
            with (
                self.subTest(context=context.type),
                self.assertRaises(PermissionDenied),
            ):
                self.pv("signup_post", context, NEW_EVENT_VALUES)

    def test_non_staff_member_permission_denied_every_context(self) -> None:
        member = self.make_user()
        for context in (
            self.new_event(),
            self.one_off(),
            self.series_ctx(),
            self.new_repeater(),
        ):
            with (
                self.subTest(context=context.type),
                self.assertRaises(PermissionDenied),
            ):
                self.pv("signup_post", context, user=member)

    def test_invalid_values_from_outsider_still_permission_denied(self) -> None:
        member = self.make_user()
        with self.assertRaises(PermissionDenied):
            self.pv(
                "signup_post", self.new_event(), {"timezone": "Not/AZone"}, user=member
            )

    def test_missing_repeater_http404(self) -> None:
        for context in (
            SeriesOneOffContext(type="series_one_off", repeater_id=999999),
            RepeaterContext(type="repeater", repeater_id=999999),
        ):
            with self.subTest(context=context.type), self.assertRaises(Http404):
                self.pv("signup_post", context)

    def test_missing_organization_http404(self) -> None:
        with self.assertRaises(Http404):
            self.pv(
                "signup_post",
                NewEventContext(type="new_event", organization_id=999999),
            )

    def test_org_cannot_be_switched_via_values(self) -> None:
        other = self.other_org()
        response = self.pv(
            "new_event_post",
            self.new_event(),
            {**NEW_EVENT_VALUES, "organization": other.pk},
        )
        dumped = response.model_dump_json()
        self.assertIn(self.org.name, dumped)
        self.assertNotIn(other.name, dumped)
        repeater_response = self.pv(
            "new_event_post",
            self.new_repeater(),
            self.new_repeater_values(organization=other.pk),
        )
        self.assertNotIn(other.name, repeater_response.model_dump_json())


class ContextNoSideEffectTest(_ContextTestCase):
    @contextmanager
    def _guards(self) -> Iterator[MagicMock]:
        boom = AssertionError("network call during preview")
        with ExitStack() as stack:
            for name in ("get", "post", "patch", "put", "delete", "request"):
                stack.enter_context(patch(f"requests.{name}", side_effect=boom))
            for name in ("get", "post", "patch", "api_get"):
                stack.enter_context(
                    patch(f"app.internal_client.transport.{name}", side_effect=boom)
                )
            stack.enter_context(
                patch("discordbot.utils._rate_limited_request", side_effect=boom)
            )
            yield stack.enter_context(
                patch("events.discord.embeds.get_event_signups", side_effect=boom)
            )

    def _snapshot(self) -> tuple[Any, ...]:
        return (
            DiscordMessageLog.objects.count(),
            DiscordEvent.objects.count(),
            DiscordEventLog.objects.count(),
            list(Event.objects.order_by("pk").values()),
            list(EventRepeater.objects.order_by("pk").values()),
        )

    def test_no_side_effects_every_context(self) -> None:
        upcoming = self.series_event(3)
        self._signup(upcoming, "guarded", "300000000000000001", SignupStatus.RSVP)
        contexts: list[tuple[PreviewContext, dict[str, Any]]] = [
            (self.new_event(), NEW_EVENT_VALUES),
            (self.one_off(), {"scheduled_at": "2031-03-02T19:00:00Z"}),
            (
                self.series_ctx(),
                {
                    "name": "Edited",
                    "description": "Edited & more",
                    "signup_open_mode": "scheduled",
                },
            ),
            (self.new_repeater(), self.new_repeater_values()),
        ]
        before = self._snapshot()
        for context, values in contexts:
            for kind in ALL_KINDS:
                with self.subTest(context=context.type, kind=kind):
                    with (
                        self._guards() as spy,
                        CaptureQueriesContext(connection) as ctx,
                    ):
                        response = self.pv(kind, context, values, open_signups=True)
                    self.assertEqual(response.status, "ok")
                    self.assertEqual(spy.call_count, 0)
                    writes = [
                        q["sql"]
                        for q in ctx.captured_queries
                        if q["sql"]
                        .lstrip()
                        .upper()
                        .startswith(("INSERT", "UPDATE", "DELETE"))
                    ]
                    self.assertEqual(writes, [])
        self.assertEqual(self._snapshot(), before)
