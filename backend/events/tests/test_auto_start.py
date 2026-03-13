from datetime import timedelta

from django.test import TestCase
from django.utils import timezone as tz

from app.models import Tournament
from events.models import Event, EventSignup, EventState, SignupStatus, SignupType
from events.tests.base import EventTestCase


class AutoStartTournamentTests(EventTestCase):
    def _create_due_event(self, **kwargs):
        defaults = dict(
            organization=self.org,
            name="Auto Start Event",
            scheduled_at=tz.now() - timedelta(minutes=5),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
            tournament_name="Auto Tourney",
            tournament_league=self.league,
            people_per_team=5,
            number_of_teams=2,
            auto_start=True,
            roll_call_enabled=False,
        )
        defaults.update(kwargs)
        return Event.objects.create(**defaults)

    def test_auto_start_creates_tournament(self):
        from events.services import auto_start_event

        event = self._create_due_event()
        EventSignup.objects.create(
            event=event,
            user=self.user,
            signup_type=SignupType.USER,
            status=SignupStatus.CONFIRMED,
        )
        tournament = auto_start_event(event)
        self.assertIsNotNone(tournament)
        self.assertEqual(tournament.name, "Auto Tourney")
        event.refresh_from_db()
        self.assertEqual(event.state, EventState.IN_PROGRESS)
        self.assertEqual(event.tournament, tournament)

    def test_auto_start_adds_users(self):
        from events.services import auto_start_event

        event = self._create_due_event()
        EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.CONFIRMED
        )
        EventSignup.objects.create(
            event=event, user=self.admin, status=SignupStatus.APPROVED
        )
        tournament = auto_start_event(event)
        self.assertEqual(tournament.users.count(), 2)

    def test_skips_if_roll_call_enabled(self):
        from events.services import auto_start_event

        event = self._create_due_event(roll_call_enabled=True, auto_start=False)
        self.assertIsNone(auto_start_event(event))

    def test_skips_if_auto_start_disabled(self):
        from events.services import auto_start_event

        event = self._create_due_event(auto_start=False)
        self.assertIsNone(auto_start_event(event))

    def test_skips_wrong_state(self):
        from events.services import auto_start_event

        event = self._create_due_event(state=EventState.UPCOMING)
        self.assertIsNone(auto_start_event(event))

    def test_idempotent_wont_double_create(self):
        from events.services import auto_start_event

        event = self._create_due_event()
        EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.CONFIRMED
        )
        t1 = auto_start_event(event)
        t2 = auto_start_event(event)  # event now in_progress, should return None
        self.assertIsNotNone(t1)
        self.assertIsNone(t2)
        self.assertEqual(Tournament.objects.filter(name="Auto Tourney").count(), 1)
