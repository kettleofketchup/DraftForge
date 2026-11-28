from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, GameType
from events.models import (
    Event,
    EventSignup,
    EventState,
    SignupLedgerEntry,
    SignupStatus,
)
from events.services import create_tentative_signup
from events.tests.actors import SYSTEM
from org.models import Organization


class CreateTentativeSignupTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="alice")
        self.org = Organization.objects.create(name="Org")
        self.event = Event.objects.create(
            name="Evt",
            organization=self.org,
            game_type=GameType.DOTA2,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
        )

    def test_creates_tentative_signup(self):
        signup = create_tentative_signup(self.event, self.user, actor=SYSTEM)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)
        self.assertEqual(signup.user, self.user)

    def test_upgrades_active_signup_to_tentative(self):
        old = EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.RSVP
        )
        signup = create_tentative_signup(self.event, self.user, actor=SYSTEM)
        self.assertEqual(signup.pk, old.pk)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)
        self.assertEqual(
            EventSignup.objects.filter(event=self.event, user=self.user).count(), 1
        )

    def test_rejects_duplicate_tentative(self):
        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.TENTATIVE
        )
        with self.assertRaises(ValueError):
            create_tentative_signup(self.event, self.user, actor=SYSTEM)

    def test_reuses_cancelled_row(self):
        old = EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CANCELLED
        )
        signup = create_tentative_signup(self.event, self.user, actor=SYSTEM)
        self.assertEqual(signup.pk, old.pk)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)
        self.assertEqual(
            EventSignup.objects.filter(event=self.event, user=self.user).count(), 1
        )

    def test_state_must_be_signups_open(self):
        # EventState has no CLOSED; CANCELLED is the appropriate non-open state.
        self.event.state = EventState.CANCELLED
        self.event.save()
        with self.assertRaises(ValueError):
            create_tentative_signup(self.event, self.user, actor=SYSTEM)

    def test_ledger_snapshots_the_stored_event_not_a_stale_instance(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(name="Renamed")
        signup = create_tentative_signup(self.event, self.user, actor=SYSTEM)
        entry = SignupLedgerEntry.objects.get(signup=signup)
        self.assertEqual(entry.event_snapshot["name"], "Renamed")

    def test_stale_open_instance_does_not_admit_a_cancelled_event(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(state=EventState.CANCELLED)
        with self.assertRaises(ValueError):
            create_tentative_signup(self.event, self.user, actor=SYSTEM)
        self.assertFalse(EventSignup.objects.filter(user=self.user).exists())
