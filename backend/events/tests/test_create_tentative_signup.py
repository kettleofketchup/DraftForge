from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, GameType, Organization
from events.models import Event, EventState, EventSignup, SignupStatus
from events.services import create_tentative_signup


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
        signup = create_tentative_signup(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)
        self.assertEqual(signup.user, self.user)

    def test_upgrades_active_signup_to_tentative(self):
        # Active signups (RSVP/APPROVED/CONFIRMED/etc.) are cancelled and
        # replaced with a fresh TENTATIVE row. Only one row remains.
        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.RSVP
        )
        signup = create_tentative_signup(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)
        self.assertEqual(
            EventSignup.objects.filter(event=self.event, user=self.user).count(), 1
        )

    def test_rejects_duplicate_tentative(self):
        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.TENTATIVE
        )
        with self.assertRaises(ValueError):
            create_tentative_signup(self.event, self.user)

    def test_cleans_up_cancelled_row(self):
        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CANCELLED
        )
        signup = create_tentative_signup(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)
        self.assertEqual(
            EventSignup.objects.filter(event=self.event, user=self.user).count(), 1
        )

    def test_state_must_be_signups_open(self):
        # EventState has no CLOSED; CANCELLED is the appropriate non-open state.
        self.event.state = EventState.CANCELLED
        self.event.save()
        with self.assertRaises(ValueError):
            create_tentative_signup(self.event, self.user)
