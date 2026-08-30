"""One-off (off-schedule) events attached to a series, and series reactivation."""

from datetime import time, timedelta
from unittest.mock import patch

from django.utils import timezone as tz
from rest_framework.test import APIClient

from events.constants import EventState, RepeatFrequency
from events.models import Event, EventRepeater
from events.serializers import EventSerializer
from events.tests.base import EventTestCase


class OffScheduleFieldTest(EventTestCase):
    def test_event_defaults_to_on_schedule(self):
        self.assertFalse(self.event.is_off_schedule)

    def test_serializer_exposes_field_read_only(self):
        self.assertIn("is_off_schedule", EventSerializer.Meta.fields)
        self.assertIn("is_off_schedule", EventSerializer.Meta.read_only_fields)


class RepeaterCopyFieldsTest(EventTestCase):
    def _create_repeater(self, **kwargs):
        defaults = dict(
            organization=self.org,
            name="Sunday Turbo",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
        )
        defaults.update(kwargs)
        return EventRepeater.objects.create(**defaults)

    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_generation_inherits_discord_tournament_fields(self, _notify, _create):
        # Both fields default True on BOTH models, so the repeater must be set
        # away from the default or the assertion passes without the fix.
        repeater = self._create_repeater(
            discord_send_draft_link=False,
            discord_send_herodraft_link=False,
        )
        from events.services import generate_events_for_repeater

        created = generate_events_for_repeater(repeater)
        self.assertTrue(created)
        for event in created:
            self.assertFalse(event.discord_send_draft_link)
            self.assertFalse(event.discord_send_herodraft_link)


class SyncFutureEventsShieldTest(EventTestCase):
    def setUp(self):
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Sunday Turbo",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
        )
        self.extra = Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Holiday Special",
            scheduled_at=tz.now() + timedelta(days=3, hours=7),
            state=EventState.UPCOMING,
            is_off_schedule=True,
        )

    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_realign_does_not_delete_off_schedule_event(self, _n, _c):
        from events.services import sync_future_events

        self.repeater.day_of_week = 3
        self.repeater.save()
        sync_future_events(self.repeater, realign_schedule=True)

        self.assertTrue(Event.objects.filter(pk=self.extra.pk).exists())

    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_cascade_does_not_revert_off_schedule_overrides(self, _n, _c):
        from events.services import sync_future_events

        sync_future_events(self.repeater)
        self.extra.refresh_from_db()
        self.assertEqual(self.extra.name, "Holiday Special")

    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_realign_skipped_for_inactive_repeater(self, _n, _c):
        from events.services import sync_future_events

        on_schedule = Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Sunday Turbo",
            scheduled_at=tz.now() + timedelta(days=2),
            state=EventState.UPCOMING,
        )
        self.repeater.is_active = False
        self.repeater.day_of_week = 3
        self.repeater.save()

        result = sync_future_events(self.repeater, realign_schedule=True)

        self.assertIsInstance(result, list)
        self.assertTrue(Event.objects.filter(pk=on_schedule.pk).exists())

    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_cascade_still_runs_for_inactive_repeater(self, _n, _c):
        from events.services import sync_future_events

        on_schedule = Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Old Name",
            scheduled_at=tz.now() + timedelta(days=2),
            state=EventState.UPCOMING,
        )
        self.repeater.is_active = False
        self.repeater.name = "Renamed Series"
        self.repeater.save()

        sync_future_events(self.repeater)

        on_schedule.refresh_from_db()
        self.assertEqual(on_schedule.name, "Renamed Series")

    @patch("events.tasks.delete_discord_scheduled_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_realign_delete_tears_down_discord(self, _n, _c, mock_delete):
        from discordbot.models import DiscordEvent
        from events.services import sync_future_events

        self.org.discord_server_id = "734185035623825559"
        self.org.save(update_fields=["discord_server_id"])
        stale = Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Sunday Turbo",
            scheduled_at=tz.now() + timedelta(days=2, hours=3),
            state=EventState.UPCOMING,
        )
        DiscordEvent.objects.create(
            event=stale,
            guild_id="734185035623825559",
            scheduled_event_id="1529289108529352788",
        )

        self.repeater.day_of_week = 3
        self.repeater.save()
        sync_future_events(self.repeater, realign_schedule=True)

        self.assertFalse(Event.objects.filter(pk=stale.pk).exists())
        mock_delete.delay.assert_called_once_with(
            "734185035623825559", "1529289108529352788"
        )


class CreateOffScheduleEventTest(EventTestCase):
    def setUp(self):
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Sunday Turbo",
            description="Weekly turbo night",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
            max_players=20,
            discord_send_draft_link=False,
        )

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_creates_off_schedule_event_with_inherited_config(
        self, mock_notify, mock_discord_event, mock_tournament, mock_ensure
    ):
        from events.services import create_off_schedule_event

        when = tz.now() + timedelta(days=2, hours=5)
        event = create_off_schedule_event(
            self.repeater, scheduled_at=when, created_by=self.admin
        )

        self.assertEqual(event.event_repeater_id, self.repeater.pk)
        self.assertTrue(event.is_off_schedule)
        self.assertEqual(event.state, EventState.UPCOMING)
        self.assertEqual(event.name, "Sunday Turbo")
        self.assertEqual(event.max_players, 20)  # EventConfigMixin
        self.assertFalse(event.discord_send_draft_link)  # DiscordTournamentConfigMixin
        self.assertEqual(event.tournament_date, when)

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_applies_overrides(self, *_mocks):
        from events.services import create_off_schedule_event

        event = create_off_schedule_event(
            self.repeater,
            scheduled_at=tz.now() + timedelta(days=2, hours=5),
            created_by=self.admin,
            overrides={"name": "Holiday Special", "max_players": 10},
        )
        self.assertEqual(event.name, "Holiday Special")
        self.assertEqual(event.max_players, 10)

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_dispatches_discord_notifications(
        self, mock_notify_new, mock_notify_create, *_mocks
    ):
        from events.services import create_off_schedule_event

        self.repeater.discord_notify_new_events = True
        self.repeater.discord_create_event = True
        self.repeater.save()

        event = create_off_schedule_event(
            self.repeater,
            scheduled_at=tz.now() + timedelta(days=2, hours=5),
            created_by=self.admin,
        )
        mock_notify_new.assert_called_once_with(event)
        mock_notify_create.assert_called_once_with(event)

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_rejects_collision_with_existing_row(self, *_mocks):
        from events.services import OccurrenceCollision, create_off_schedule_event

        when = tz.now() + timedelta(days=2, hours=5)
        Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Sunday Turbo",
            scheduled_at=when,
            state=EventState.UPCOMING,
        )
        with self.assertRaises(OccurrenceCollision):
            create_off_schedule_event(
                self.repeater, scheduled_at=when, created_by=self.admin
            )

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_rejects_collision_with_future_occurrence(self, *_mocks):
        from events.services import (
            OccurrenceCollision,
            _get_next_occurrences,
            _today,
            create_off_schedule_event,
            generate_events_for_repeater,
        )

        occurrences = _get_next_occurrences(
            self.repeater, _today(), _today() + timedelta(days=14)
        )
        target = occurrences[0]

        with self.assertRaises(OccurrenceCollision):
            create_off_schedule_event(
                self.repeater, scheduled_at=target, created_by=self.admin
            )

        # The real recurring event is still generated afterwards.
        created = generate_events_for_repeater(self.repeater)
        self.assertIn(target, [e.scheduled_at for e in created])


class CreateEventEndpointTest(EventTestCase):
    def setUp(self):
        self.client = APIClient()
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Sunday Turbo",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
        )
        self.url = f"/api/events/repeaters/{self.repeater.pk}/create-event/"
        self.when = (tz.now() + timedelta(days=2, hours=5)).isoformat()

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_staff_creates_off_schedule_event(self, *_mocks):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.url, {"scheduled_at": self.when}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(resp.data["is_off_schedule"])
        self.assertEqual(resp.data["event_repeater"], self.repeater.pk)

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_open_signups_flag_transitions_state(self, *_mocks):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            self.url,
            {"scheduled_at": self.when, "open_signups": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["state"], EventState.SIGNUPS_OPEN)

    def test_non_staff_forbidden(self):
        self.client.force_authenticate(self.unrelated_user)
        resp = self.client.post(self.url, {"scheduled_at": self.when}, format="json")
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertFalse(Event.objects.filter(is_off_schedule=True).exists())

    def test_anonymous_forbidden(self):
        resp = self.client.post(self.url, {"scheduled_at": self.when}, format="json")
        # SessionAuthentication supplies no WWW-Authenticate header, so DRF
        # downgrades NotAuthenticated to 403 — there is no 401 path here.
        self.assertEqual(resp.status_code, 403, resp.content)

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_collision_returns_409(self, *_mocks):
        Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Sunday Turbo",
            scheduled_at=tz.now() + timedelta(days=2, hours=5),
            state=EventState.UPCOMING,
        )
        self.client.force_authenticate(self.admin)
        before = Event.objects.count()
        resp = self.client.post(
            self.url,
            {"scheduled_at": Event.objects.latest("id").scheduled_at.isoformat()},
            format="json",
        )
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(Event.objects.count(), before)

    def test_past_scheduled_at_rejected(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            self.url,
            {"scheduled_at": (tz.now() - timedelta(days=1)).isoformat()},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_invalid_game_mode_for_game_type_rejected(self):
        self.repeater.game_type = 2
        self.repeater.save(update_fields=["game_type"])
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            self.url,
            {"scheduled_at": self.when, "game_mode": "captains_mode"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(Event.objects.filter(is_off_schedule=True).exists())

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_overrides_are_coerced_not_raw(self, *_mocks):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            self.url,
            {
                "scheduled_at": self.when,
                "tournament_league": self.league.pk,
                "max_players": "12",
                "discord_announcement": "false",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        event = Event.objects.get(pk=resp.data["id"])
        self.assertEqual(event.tournament_league_id, self.league.pk)
        self.assertIsInstance(event.max_players, int)
        self.assertEqual(event.max_players, 12)
        self.assertIs(event.discord_announcement, False)

    def test_foreign_org_league_rejected(self):
        from app.models import League, Organization

        other_org = Organization.objects.create(name="Other Org", owner=self.admin)
        other = League.objects.create(name="Other", organization=other_org)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            self.url,
            {"scheduled_at": self.when, "tournament_league": other.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    @patch("app.cache_utils.invalidate_after_commit")
    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_invalidates_repeater_cache(self, _n, _c, _t, _e, mock_invalidate):
        self.client.force_authenticate(self.admin)
        self.client.post(self.url, {"scheduled_at": self.when}, format="json")
        invalidated = [a for call in mock_invalidate.call_args_list for a in call.args]
        self.assertTrue(any(obj.pk == self.repeater.pk for obj in invalidated))


class ReactivateEndpointTest(EventTestCase):
    def setUp(self):
        self.client = APIClient()
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Sunday Turbo",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
            is_active=False,
        )
        self.url = f"/api/events/repeaters/{self.repeater.pk}/reactivate/"

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_reactivate_flips_flag_and_generates(self, *_mocks):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.repeater.refresh_from_db()
        self.assertTrue(self.repeater.is_active)
        self.assertGreater(resp.data["created_count"], 0)
        self.assertEqual(
            Event.objects.filter(event_repeater=self.repeater).count(),
            resp.data["created_count"],
        )

    def test_non_staff_forbidden(self):
        self.client.force_authenticate(self.unrelated_user)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 403, resp.content)
        self.repeater.refresh_from_db()
        self.assertFalse(self.repeater.is_active)

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_ended_series_reports_zero(self, *_mocks):
        self.repeater.ends_at = tz.now().date() - timedelta(days=1)
        self.repeater.save(update_fields=["ends_at"])
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["created_count"], 0)
        self.assertIn("end date", resp.data["detail"].lower())

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_reactivate_realigns_after_schedule_change(self, *_mocks):
        stale = Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Sunday Turbo",
            scheduled_at=tz.now() + timedelta(days=1, hours=2),
            state=EventState.UPCOMING,
        )
        self.repeater.day_of_week = 3
        self.repeater.name = "Renamed While Paused"
        self.repeater.save()

        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200, resp.content)

        self.assertFalse(Event.objects.filter(pk=stale.pk).exists())
        survivors = Event.objects.filter(event_repeater=self.repeater)
        self.assertTrue(survivors.exists())
        self.assertEqual(
            survivors.count(),
            survivors.values("scheduled_at").distinct().count(),
        )
        for event in survivors:
            self.assertEqual(event.name, "Renamed While Paused")

    @patch("app.cache_utils.invalidate_after_commit")
    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_invalidates_repeater_cache(self, _n, _c, _t, _e, mock_invalidate):
        self.client.force_authenticate(self.admin)
        self.client.post(self.url)
        invalidated = [a for call in mock_invalidate.call_args_list for a in call.args]
        self.assertTrue(any(obj.pk == self.repeater.pk for obj in invalidated))
