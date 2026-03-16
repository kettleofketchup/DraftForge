from datetime import date, time
from unittest.mock import patch

from events.models import Event, EventRepeater, RepeatFrequency
from events.tests.base import EventTestCase

PATCH_TODAY = "events.services._today"


class GenerateUpcomingEventsTaskTests(EventTestCase):
    @patch(PATCH_TODAY, return_value=date(2026, 3, 2))
    def test_task_generates_events(self, mock_today):
        from events.tasks import generate_upcoming_events

        EventRepeater.objects.create(
            organization=self.org,
            name="Daily",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(19, 0),
            starts_at=date(2026, 3, 1),
            generate_days_ahead=3,
            is_active=True,
            created_by=self.admin,
            tournament_name="Daily",
            tournament_league=self.league,
        )
        result = generate_upcoming_events()
        self.assertIn("Generated", result)
        self.assertTrue(Event.objects.exists())

    @patch(PATCH_TODAY, return_value=date(2026, 3, 2))
    def test_task_idempotent(self, mock_today):
        from events.tasks import generate_upcoming_events

        EventRepeater.objects.create(
            organization=self.org,
            name="Daily",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(19, 0),
            starts_at=date(2026, 3, 1),
            generate_days_ahead=3,
            is_active=True,
            created_by=self.admin,
            tournament_name="Daily",
            tournament_league=self.league,
        )
        generate_upcoming_events()
        count1 = Event.objects.count()
        generate_upcoming_events()
        self.assertEqual(Event.objects.count(), count1)
