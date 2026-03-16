from datetime import timedelta

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


class EventModelTests(EventTestCase):
    def test_create_standalone_event(self):
        from events.models import Event, EventState

        event = Event.objects.create(
            organization=self.org,
            name="Standalone",
            scheduled_at=tz.now() + timedelta(days=7),
            state=EventState.UPCOMING,
            created_by=self.admin,
            tournament_name="Standalone Tourney",
            tournament_league=self.league,
        )
        self.assertIsNone(event.event_repeater)
        self.assertIsNone(event.tournament)

    def test_state_transition_valid(self):
        from events.models import Event, EventState

        event = Event.objects.create(
            organization=self.org,
            name="Test",
            scheduled_at=tz.now() + timedelta(days=7),
            created_by=self.admin,
            tournament_name="Test",
            tournament_league=self.league,
        )
        event.transition_state(EventState.SIGNUPS_OPEN)
        self.assertEqual(event.state, EventState.SIGNUPS_OPEN)

    def test_state_transition_invalid(self):
        from events.models import Event, EventState

        event = Event.objects.create(
            organization=self.org,
            name="Test",
            scheduled_at=tz.now() + timedelta(days=7),
            created_by=self.admin,
            tournament_name="Test",
            tournament_league=self.league,
        )
        with self.assertRaises(ValueError):
            event.transition_state(EventState.IN_PROGRESS)

    def test_cancel_from_any_pre_game_state(self):
        from events.models import Event, EventState

        for initial in [
            EventState.UPCOMING,
            EventState.SIGNUPS_OPEN,
            EventState.ROLL_CALL,
        ]:
            event = Event.objects.create(
                organization=self.org,
                name=f"Cancel {initial}",
                scheduled_at=tz.now() + timedelta(days=7),
                created_by=self.admin,
                tournament_name="Test",
                tournament_league=self.league,
                state=initial,
                **(
                    {"roll_call_enabled": True}
                    if initial == EventState.ROLL_CALL
                    else {}
                ),
            )
            event.transition_state(EventState.CANCELLED)
            self.assertEqual(event.state, EventState.CANCELLED)

    def test_unique_repeater_scheduled_at(self):
        from django.db import IntegrityError

        from events.models import Event, EventRepeater, RepeatFrequency

        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=1,
            time_of_day="19:00:00",
            starts_at="2026-03-01",
            generate_days_ahead=7,
            created_by=self.admin,
            tournament_name="Weekly",
            tournament_league=self.league,
        )
        scheduled = tz.now() + timedelta(days=7)
        Event.objects.create(
            organization=self.org,
            event_repeater=repeater,
            name="Week 1",
            scheduled_at=scheduled,
            created_by=self.admin,
            tournament_name="Week 1",
            tournament_league=self.league,
        )
        with self.assertRaises(IntegrityError):
            Event.objects.create(
                organization=self.org,
                event_repeater=repeater,
                name="Duplicate",
                scheduled_at=scheduled,
                created_by=self.admin,
                tournament_name="Dup",
                tournament_league=self.league,
            )

    def test_description_sanitized(self):
        from events.models import Event

        event = Event.objects.create(
            organization=self.org,
            name="XSS",
            description="<script>bad</script><p>Good</p>",
            scheduled_at=tz.now() + timedelta(days=7),
            created_by=self.admin,
            tournament_name="Test",
            tournament_league=self.league,
        )
        self.assertNotIn("<script>", event.description)


class EventTeamModelTests(EventTestCase):
    def setUp(self):
        from events.models import Event

        self.event = Event.objects.create(
            organization=self.org,
            name="Team Event",
            scheduled_at=tz.now() + timedelta(days=7),
            created_by=self.admin,
            tournament_name="Test",
            tournament_league=self.league,
            allow_team_signups=True,
        )

    def test_create_event_team(self):
        from events.models import EventTeam

        team = EventTeam.objects.create(
            event=self.event,
            name="Team Alpha",
            captain=self.admin,
        )
        team.members.add(self.admin, self.user)
        self.assertEqual(team.members.count(), 2)

    def test_event_team_str(self):
        from events.models import EventTeam

        team = EventTeam.objects.create(
            event=self.event,
            name="Team Alpha",
            captain=self.admin,
        )
        self.assertEqual(str(team), "Team Alpha (Team Event)")


class EventSignupModelTests(EventTestCase):
    def setUp(self):
        from events.models import Event

        self.event = Event.objects.create(
            organization=self.org,
            name="Signup Event",
            scheduled_at=tz.now() + timedelta(days=7),
            created_by=self.admin,
            tournament_name="Test",
            tournament_league=self.league,
        )

    def test_create_user_signup(self):
        from events.models import EventSignup, SignupStatus, SignupType

        signup = EventSignup.objects.create(
            event=self.event,
            user=self.user,
            signup_type=SignupType.USER,
        )
        self.assertEqual(signup.status, SignupStatus.RSVP)
        self.assertIsNone(signup.event_team)

    def test_unique_user_per_event(self):
        from django.db import IntegrityError

        from events.models import EventSignup, SignupType

        EventSignup.objects.create(
            event=self.event, user=self.user, signup_type=SignupType.USER
        )
        with self.assertRaises(IntegrityError):
            EventSignup.objects.create(
                event=self.event, user=self.user, signup_type=SignupType.USER
            )
