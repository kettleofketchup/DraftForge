"""sync_future_events realigns occurrences when the repeater's schedule changes.

Pre-PR-2 behavior: editing a repeater's day_of_week left existing UPCOMING
events on their old days, while the next hourly generate_events_for_repeater
created NEW events at the new schedule — admins saw duplicate occurrences.

PR-2 fix: when the caller signals realign_schedule=True, delete UPCOMING
rows whose scheduled_at is no longer in the new occurrence set, then
generate_events_for_repeater fills in any missing ones.
"""

from datetime import datetime, time, timedelta, timezone as dt_tz
from unittest.mock import patch

from events.models import Event, EventRepeater
from events.services import sync_future_events
from events.tests.test_discord_tasks import _DiscordTaskTestCase


class SyncFutureEventsRealignTest(_DiscordTaskTestCase):
    def _make_repeater(self, day_of_week=1, time_of_day=time(20, 0)):
        # starts_at must be today or earlier — generate_events_for_repeater
        # uses _today() as its from_date and won't generate events before that
        from django.utils import timezone

        return EventRepeater.objects.create(
            organization=self.event.organization,
            name="Realign Test Repeater",
            frequency="weekly",
            day_of_week=day_of_week,
            time_of_day=time_of_day,
            timezone="UTC",
            starts_at=timezone.now().date() - timedelta(days=1),
            generate_days_ahead=14,
            is_active=True,
        )

    def test_realign_false_preserves_existing_scheduled_at(self):
        repeater = self._make_repeater()
        original_at = datetime(2099, 1, 5, 20, 0, tzinfo=dt_tz.utc)
        ev = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Future",
            scheduled_at=original_at,
            state="upcoming",
            discord_announcement_channel_id="ch_1",
        )
        sync_future_events(repeater, realign_schedule=False)
        ev.refresh_from_db()
        self.assertEqual(ev.scheduled_at, original_at)

    def test_realign_true_deletes_stale_occurrence_outside_new_set(self):
        # day_of_week=1 (Monday in Sunday=0 convention)
        repeater = self._make_repeater(day_of_week=1)
        # Stale row at a date that won't match the new occurrence set
        # (a fixed historical date the generator won't produce)
        stale_at = datetime(2099, 1, 5, 20, 0, tzinfo=dt_tz.utc)
        stale_event = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Stale",
            scheduled_at=stale_at,
            state="upcoming",
            discord_announcement_channel_id="ch_1",
        )
        # Repeater is now-aligned; realign=True should delete the stale row
        # and regenerate the correct occurrences.
        sync_future_events(repeater, realign_schedule=True)
        self.assertFalse(Event.objects.filter(pk=stale_event.pk).exists())

    def test_realign_true_keeps_rows_already_in_new_set(self):
        # Use today's _today() helper so we know what generate_events_for_repeater
        # will produce. Pick day_of_week to match next-week's weekday so
        # generate_events_for_repeater will produce a row 7 days from today.
        from events.services import _get_next_occurrences, _today

        repeater = self._make_repeater(day_of_week=1)
        today = _today()
        to_date = today + timedelta(days=repeater.generate_days_ahead)
        new_occurrences = list(_get_next_occurrences(repeater, today, to_date))
        if not new_occurrences:
            self.skipTest("No occurrences in the test window — adjust generate_days_ahead")

        # Pre-create a row at the FIRST occurrence — realign should keep it
        kept_event = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Already aligned",
            scheduled_at=new_occurrences[0],
            state="upcoming",
            discord_announcement_channel_id="ch_1",
        )
        sync_future_events(repeater, realign_schedule=True)
        # The kept row should still be there
        self.assertTrue(Event.objects.filter(pk=kept_event.pk).exists())

    def test_realign_false_default_no_regeneration(self):
        # If sync_future_events is called without realign_schedule (default False),
        # generate_events_for_repeater should NOT be invoked — rows stay as-is.
        repeater = self._make_repeater()
        with patch("events.services.generate_events_for_repeater") as mock_gen:
            sync_future_events(repeater)
            mock_gen.assert_not_called()

    def test_realign_true_calls_generate_events_for_repeater(self):
        repeater = self._make_repeater()
        with patch("events.services.generate_events_for_repeater") as mock_gen:
            mock_gen.return_value = []
            sync_future_events(repeater, realign_schedule=True)
            mock_gen.assert_called_once_with(repeater)
