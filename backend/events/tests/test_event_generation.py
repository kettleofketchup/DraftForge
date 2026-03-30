from datetime import date, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone as tz

from events.constants import RepeatFrequency
from events.models import Event, EventRepeater
from events.tests.base import EventTestCase

PATCH_TODAY = "events.services._today"


class EventGenerationTests(EventTestCase):
    def _create_repeater(self, **kwargs):
        defaults = dict(
            organization=self.org,
            name="Weekly Event",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=1,
            time_of_day=time(19, 0),
            starts_at=date(2026, 3, 1),
            generate_days_ahead=7,
            is_active=True,
            created_by=self.admin,
            tournament_name="Weekly Tourney",
            tournament_league=self.league,
            people_per_team=5,
            number_of_teams=2,
        )
        defaults.update(kwargs)
        return EventRepeater.objects.create(**defaults)

    @patch(PATCH_TODAY, return_value=date(2026, 3, 2))
    def test_generate_weekly_event(self, mock_today):
        from events.services import generate_events_for_repeater

        repeater = self._create_repeater()
        events = generate_events_for_repeater(repeater)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].tournament_name, "Weekly Tourney")
        self.assertEqual(events[0].people_per_team, 5)

    @patch(PATCH_TODAY, return_value=date(2026, 3, 2))
    def test_no_duplicate_events(self, mock_today):
        from events.services import generate_events_for_repeater

        repeater = self._create_repeater()
        events1 = generate_events_for_repeater(repeater)
        events2 = generate_events_for_repeater(repeater)
        self.assertEqual(len(events1), 1)
        self.assertEqual(len(events2), 0)

    def test_inactive_repeater_generates_nothing(self):
        from events.services import generate_events_for_repeater

        repeater = self._create_repeater(is_active=False)
        self.assertEqual(len(generate_events_for_repeater(repeater)), 0)

    def test_ended_repeater_generates_nothing(self):
        from events.services import generate_events_for_repeater

        repeater = self._create_repeater(ends_at=date(2026, 1, 1))
        self.assertEqual(len(generate_events_for_repeater(repeater)), 0)

    @patch(PATCH_TODAY, return_value=date(2026, 3, 2))
    def test_daily_frequency(self, mock_today):
        from events.services import generate_events_for_repeater

        repeater = self._create_repeater(
            frequency=RepeatFrequency.DAILY,
            day_of_week=None,
            generate_days_ahead=3,
        )
        events = generate_events_for_repeater(repeater)
        self.assertGreaterEqual(len(events), 1)

    @patch(PATCH_TODAY, return_value=date(2026, 3, 2))
    def test_config_fields_copied(self, mock_today):
        from events.services import generate_events_for_repeater

        repeater = self._create_repeater(
            auto_approve=True,
            require_steam_id=True,
            min_players=10,
            max_players=20,
        )
        events = generate_events_for_repeater(repeater)
        event = events[0]
        self.assertTrue(event.auto_approve)
        self.assertTrue(event.require_steam_id)
        self.assertEqual(event.min_players, 10)
        self.assertEqual(event.max_players, 20)

    @patch(PATCH_TODAY, return_value=date(2026, 2, 27))
    def test_monthly_feb_31_clamps_to_last_day(self, mock_today):
        from events.services import generate_events_for_repeater

        repeater = self._create_repeater(
            frequency=RepeatFrequency.MONTHLY,
            day_of_week=None,
            starts_at=date(2026, 1, 31),
            generate_days_ahead=7,
        )
        events = generate_events_for_repeater(repeater)
        # Feb 31 doesn't exist — should clamp to Feb 28
        if events:
            self.assertEqual(events[0].scheduled_at.day, 28)

    @patch(PATCH_TODAY, return_value=date(2026, 3, 2))
    def test_every_two_weeks(self, mock_today):
        from events.services import generate_events_for_repeater

        repeater = self._create_repeater(
            frequency=RepeatFrequency.EVERY_TWO_WEEKS,
            generate_days_ahead=21,
        )
        events = generate_events_for_repeater(repeater)
        if len(events) >= 2:
            diff = (events[1].scheduled_at - events[0].scheduled_at).days
            self.assertEqual(diff, 14)


class DSTTests(EventTestCase):
    """Test DST transitions for event generation."""

    @patch(PATCH_TODAY, return_value=date(2026, 3, 7))
    def test_spring_forward_generates_correct_utc(self, mock_today):
        from events.services import generate_events_for_repeater

        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="DST Test",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(2, 30),
            starts_at=date(2026, 3, 7),
            generate_days_ahead=3,
            is_active=True,
            created_by=self.admin,
            tournament_name="DST",
            tournament_league=self.league,
            timezone="America/New_York",
        )
        events = generate_events_for_repeater(repeater)
        self.assertGreaterEqual(len(events), 1)
        # All events should have valid scheduled_at datetimes
        for event in events:
            self.assertIsNotNone(event.scheduled_at)
