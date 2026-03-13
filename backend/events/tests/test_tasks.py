from datetime import date, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone as tz

from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventState,
    RepeatFrequency,
    SignupStatus,
    SignupType,
)
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


class AutoStartTournamentsTaskTests(EventTestCase):
    def test_task_auto_starts_due_events(self):
        from events.tasks import auto_start_tournaments

        event = Event.objects.create(
            organization=self.org,
            name="Due",
            scheduled_at=tz.now() - timedelta(minutes=5),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
            tournament_name="Auto",
            tournament_league=self.league,
            auto_start=True,
            roll_call_enabled=False,
        )
        EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.CONFIRMED
        )
        result = auto_start_tournaments()
        self.assertIn("Started", result)
        event.refresh_from_db()
        self.assertEqual(event.state, EventState.IN_PROGRESS)

    def test_task_skips_future_events(self):
        from events.tasks import auto_start_tournaments

        Event.objects.create(
            organization=self.org,
            name="Future",
            scheduled_at=tz.now() + timedelta(hours=1),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
            tournament_name="Future",
            tournament_league=self.league,
            auto_start=True,
        )
        result = auto_start_tournaments()
        self.assertIn("Started 0", result)
