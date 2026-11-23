from datetime import time, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from django.utils import timezone as tz
from rest_framework.response import Response
from rest_framework.test import APIClient

from draft.models import Draft, DraftOptions, TimeoutAction
from events.constants import RepeatFrequency
from events.models import Event, EventRepeater, OrgEventDefaults
from events.services import (
    changed_draft_option_fields,
    create_tournament_for_event,
    event_draft_option_values,
    generate_events_for_repeater,
    sync_future_events,
    sync_tournament_from_event,
)
from events.tests.base import EventTestCase
from tournament.models import Team, Tournament

CUSTOM_SETTINGS: dict[str, Any] = {
    "draft_timer_enabled": False,
    "draft_grace_time_ms": 45000,
    "draft_reserve_time_ms": 120000,
    "draft_timeout_action": TimeoutAction.SKIP_TURN.value,
    "hero_timer_enabled": False,
    "hero_grace_time_ms": 20000,
    "hero_reserve_time_ms": 60000,
}

EXPECTED_OPTIONS: dict[str, Any] = {
    "timer_enabled": False,
    "grace_time_ms": 45000,
    "reserve_time_ms": 120000,
    "timeout_action": TimeoutAction.SKIP_TURN.value,
    "hero_timer_enabled": False,
    "hero_grace_time_ms": 20000,
    "hero_reserve_time_ms": 60000,
}


def _options(tournament: Tournament) -> dict[str, Any]:
    opts = DraftOptions.objects.nocache().get(tournament=tournament)
    return {key: getattr(opts, key) for key in EXPECTED_OPTIONS}


def _customise_tournament(tournament: Tournament) -> None:
    DraftOptions.objects.filter(tournament=tournament).update(**EXPECTED_OPTIONS)
    Draft.objects.create(tournament=tournament)
    Team.objects.create(tournament=tournament, name="Reserve", draft_reserve_ms=5000)


def _reserves(tournament: Tournament) -> list[int | None]:
    return list(
        Team.objects.nocache()
        .filter(tournament=tournament)
        .values_list("draft_reserve_ms", flat=True)
    )


class EventDraftOptionsServiceTests(EventTestCase):
    def make_event(self, **fields: Any) -> Event:
        return Event.objects.create(
            organization=self.org,
            name="Timer Night",
            scheduled_at=tz.now() + timedelta(days=3),
            **fields,
        )

    def test_defaults_match_draft_options_defaults(self) -> None:
        tournament = create_tournament_for_event(self.make_event())
        self.assertEqual(
            _options(tournament),
            {
                "timer_enabled": True,
                "grace_time_ms": 30000,
                "reserve_time_ms": 30000,
                "timeout_action": TimeoutAction.SKIP_TURN.value,
                "hero_timer_enabled": True,
                "hero_grace_time_ms": 30000,
                "hero_reserve_time_ms": 90000,
            },
        )

    def test_create_tournament_copies_custom_settings(self) -> None:
        tournament = create_tournament_for_event(self.make_event(**CUSTOM_SETTINGS))
        self.assertEqual(_options(tournament), EXPECTED_OPTIONS)

    def test_sync_applies_to_future_tournament(self) -> None:
        event = self.make_event()
        tournament = create_tournament_for_event(event)
        before = event_draft_option_values(event)
        for field, value in CUSTOM_SETTINGS.items():
            setattr(event, field, value)
        event.save()
        result = sync_tournament_from_event(
            event, changed_draft_option_fields(before, event)
        )
        self.assertTrue(result["synced"])
        self.assertEqual(_options(tournament), EXPECTED_OPTIONS)

    def test_sync_without_draft_changes_keeps_tournament_options(self) -> None:
        event = self.make_event()
        tournament = create_tournament_for_event(event)
        _customise_tournament(tournament)
        event.description = "Edited"
        event.save()
        self.assertTrue(sync_tournament_from_event(event)["synced"])
        self.assertEqual(_options(tournament), EXPECTED_OPTIONS)
        self.assertEqual(_reserves(tournament), [5000])

    def test_sync_applies_only_changed_fields(self) -> None:
        event = self.make_event()
        tournament = create_tournament_for_event(event)
        _customise_tournament(tournament)
        before = event_draft_option_values(event)
        event.hero_grace_time_ms = 15000
        event.save()
        sync_tournament_from_event(event, changed_draft_option_fields(before, event))
        self.assertEqual(
            _options(tournament), {**EXPECTED_OPTIONS, "hero_grace_time_ms": 15000}
        )
        self.assertEqual(_reserves(tournament), [5000])

    def test_sync_skips_in_progress_tournament(self) -> None:
        event = self.make_event()
        tournament = create_tournament_for_event(event)
        Tournament.objects.filter(pk=tournament.pk).update(state="in_progress")
        event.refresh_from_db()
        event.draft_timer_enabled = False
        event.save()
        result = sync_tournament_from_event(event)
        self.assertFalse(result["synced"])
        self.assertTrue(_options(tournament)["timer_enabled"])


@patch("events.services.notify_create_discord_event", MagicMock())
@patch("events.services.notify_new_event", MagicMock())
class RepeaterDraftOptionsCascadeTests(EventTestCase):
    def make_repeater(self, **fields: Any) -> EventRepeater:
        return EventRepeater.objects.create(
            organization=self.org,
            name="Daily Timers",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date() + timedelta(days=1),
            generate_days_ahead=2,
            created_by=self.admin,
            **fields,
        )

    def test_generated_events_and_tournaments_inherit_settings(self) -> None:
        events = generate_events_for_repeater(self.make_repeater(**CUSTOM_SETTINGS))
        self.assertTrue(events)
        for event in events:
            event.refresh_from_db()
            for field, value in CUSTOM_SETTINGS.items():
                self.assertEqual(getattr(event, field), value, field)
            self.assertEqual(_options(event.tournament), EXPECTED_OPTIONS)

    def test_series_edit_cascades_to_future_tournaments(self) -> None:
        repeater = self.make_repeater()
        events = generate_events_for_repeater(repeater)
        self.assertTrue(events)
        for field, value in CUSTOM_SETTINGS.items():
            setattr(repeater, field, value)
        repeater.save()
        sync_future_events(repeater)
        for event in Event.objects.filter(pk__in=[e.pk for e in events]):
            self.assertEqual(_options(event.tournament), EXPECTED_OPTIONS)

    def test_unrelated_series_edit_keeps_tournament_options(self) -> None:
        repeater = self.make_repeater()
        events = generate_events_for_repeater(repeater)
        self.assertTrue(events)
        for event in events:
            _customise_tournament(event.tournament)
        repeater.description = "New description"
        repeater.save()
        sync_future_events(repeater)
        for event in Event.objects.filter(pk__in=[e.pk for e in events]):
            self.assertEqual(event.description, "New description")
            self.assertEqual(_options(event.tournament), EXPECTED_OPTIONS)
            self.assertEqual(_reserves(event.tournament), [5000])


class EventDraftTimerSerializerTests(EventTestCase):
    TARGETS = ("event", "series", "defaults", "one_off")

    def setUp(self) -> None:
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date() + timedelta(days=30),
            created_by=self.admin,
        )
        self.defaults = OrgEventDefaults.objects.create(organization=self.org)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def write(self, target: str, data: dict[str, Any]) -> Response:
        if target == "event":
            return self.client.patch(
                f"/api/events/{self.event.pk}/", data, format="json"
            )
        if target == "series":
            return self.client.patch(
                f"/api/events/repeaters/{self.repeater.pk}/", data, format="json"
            )
        if target == "defaults":
            return self.client.patch(
                f"/api/events/defaults/{self.defaults.pk}/", data, format="json"
            )
        return self.client.post(
            f"/api/events/repeaters/{self.repeater.pk}/create-event/",
            {"scheduled_at": (tz.now() + timedelta(days=3)).isoformat(), **data},
            format="json",
        )

    @patch("events.services.notify_create_discord_event", MagicMock())
    @patch("events.services.notify_new_event", MagicMock())
    def test_round_trip(self) -> None:
        for target in self.TARGETS:
            with self.subTest(target=target):
                resp = self.write(target, CUSTOM_SETTINGS)
                self.assertIn(resp.status_code, (200, 201), resp.data)
                if target == "one_off":
                    event = Event.objects.get(pk=resp.data["id"])
                    for field, value in CUSTOM_SETTINGS.items():
                        self.assertEqual(getattr(event, field), value, field)
                    continue
                for field, value in CUSTOM_SETTINGS.items():
                    self.assertEqual(resp.data[field], value, field)

    def test_event_patch_syncs_future_tournament(self) -> None:
        tournament = create_tournament_for_event(self.event)
        resp = self.write("event", CUSTOM_SETTINGS)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(_options(tournament), EXPECTED_OPTIONS)

    def test_unrelated_event_patch_keeps_tournament_options(self) -> None:
        tournament = create_tournament_for_event(self.event)
        _customise_tournament(tournament)
        resp = self.write("event", {"description": "Just the blurb"})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(_options(tournament), EXPECTED_OPTIONS)
        self.assertEqual(_reserves(tournament), [5000])

    def test_out_of_range_times_refused(self) -> None:
        bad = {
            "draft_grace_time_ms": 999,
            "draft_reserve_time_ms": -1,
            "hero_grace_time_ms": 0,
            "hero_reserve_time_ms": -5,
        }
        for target in self.TARGETS:
            for field, value in bad.items():
                with self.subTest(target=target, field=field):
                    resp = self.write(target, {field: value})
                    self.assertEqual(resp.status_code, 400, resp.data)
                    self.assertIn(field, resp.data)

    def test_unknown_timeout_action_refused(self) -> None:
        for target in self.TARGETS:
            with self.subTest(target=target):
                resp = self.write(target, {"draft_timeout_action": "explode"})
                self.assertEqual(resp.status_code, 400, resp.data)
                self.assertIn("draft_timeout_action", resp.data)
