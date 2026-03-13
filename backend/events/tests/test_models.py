from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone as tz

from events.models import (
    EventState,
    GameType,
    RepeatFrequency,
    RollCallMode,
    SignupStatus,
    SignupType,
)
from events.tests.base import EventTestCase


class EnumTests(TestCase):
    def test_game_type_values(self):
        self.assertEqual(GameType.DOTA2, 1)
        self.assertEqual(GameType.DEADLOCK, 2)

    def test_event_state_values(self):
        states = [c[0] for c in EventState.choices]
        expected = [
            "upcoming",
            "signups_open",
            "roll_call",
            "in_progress",
            "completed",
            "cancelled",
        ]
        for s in expected:
            self.assertIn(s, states)

    def test_signup_status_values(self):
        statuses = [c[0] for c in SignupStatus.choices]
        expected = [
            "rsvp",
            "pending_approval",
            "approved",
            "confirmed",
            "waitlisted",
            "rejected",
            "cancelled",
        ]
        for s in expected:
            self.assertIn(s, statuses)

    def test_signup_type_values(self):
        self.assertEqual(SignupType.USER, "user")
        self.assertEqual(SignupType.TEAM, "team")

    def test_repeat_frequency_has_every_two_weeks(self):
        freqs = [c[0] for c in RepeatFrequency.choices]
        self.assertIn("every_two_weeks", freqs)
        self.assertNotIn("biweekly", freqs)

    def test_roll_call_mode_values(self):
        self.assertEqual(RollCallMode.MANUAL, "manual")


class EventRepeaterModelTests(EventTestCase):
    def test_create_event_repeater(self):
        from events.models import EventRepeater, RepeatFrequency

        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Tuesday Inhouses",
            description="Weekly inhouse games",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=1,
            time_of_day="19:00:00",
            starts_at="2026-03-01",
            generate_days_ahead=7,
            is_active=True,
            created_by=self.admin,
            tournament_name="Tuesday Inhouse",
            tournament_league=self.league,
        )
        self.assertEqual(repeater.name, "Tuesday Inhouses")
        self.assertEqual(repeater.frequency, RepeatFrequency.WEEKLY)
        self.assertTrue(repeater.auto_start)

    def test_event_repeater_str(self):
        from events.models import EventRepeater, RepeatFrequency

        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Tuesday Inhouses",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=1,
            time_of_day="19:00:00",
            starts_at="2026-03-01",
            generate_days_ahead=7,
            created_by=self.admin,
            tournament_name="Tuesday Inhouse",
            tournament_league=self.league,
        )
        self.assertEqual(str(repeater), "Tuesday Inhouses (weekly)")

    def test_description_sanitized_on_save(self):
        from events.models import EventRepeater, RepeatFrequency

        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Test",
            description='<script>alert("xss")</script><b>Bold</b>',
            frequency=RepeatFrequency.DAILY,
            time_of_day="19:00:00",
            starts_at="2026-03-01",
            generate_days_ahead=1,
            created_by=self.admin,
            tournament_name="Test",
            tournament_league=self.league,
        )
        self.assertNotIn("<script>", repeater.description)
        self.assertIn("<b>Bold</b>", repeater.description)
