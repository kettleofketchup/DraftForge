from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, GameType, Organization
from events.discord.handlers import handle_decline_button
from events.models import Event, EventSignup, EventState, SignupStatus
from events.services import decline_signup


class DeclineSignupServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create(username="alice")
        self.org = Organization.objects.create(name="Org")
        self.event = Event.objects.create(
            name="Evt",
            organization=self.org,
            game_type=GameType.DOTA2,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
        )

    def test_records_decline_without_prior_signup(self) -> None:
        signup = decline_signup(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.CANCELLED)
        self.assertEqual(
            EventSignup.objects.filter(event=self.event, user=self.user).count(), 1
        )

    def test_cancels_active_signup(self) -> None:
        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.RSVP
        )
        signup = decline_signup(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.CANCELLED)
        self.assertEqual(
            EventSignup.objects.filter(event=self.event, user=self.user).count(), 1
        )

    def test_cancels_tentative_signup(self) -> None:
        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.TENTATIVE
        )
        signup = decline_signup(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.CANCELLED)

    def test_rejects_duplicate_decline(self) -> None:
        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CANCELLED
        )
        with self.assertRaises(ValueError):
            decline_signup(self.event, self.user)


class HandleDeclineButtonTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Org")
        self.event = Event.objects.create(
            name="Evt",
            organization=self.org,
            game_type=GameType.DOTA2,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
        )

    def test_unregistered_discord_user_can_decline(self) -> None:
        result = handle_decline_button(
            self.event.pk, "900000000000000001", discord_username="newcomer"
        )
        self.assertEqual(result["action"], "declined")
        user = CustomUser.objects.get(discordId="900000000000000001")
        signup = EventSignup.objects.get(event=self.event, user=user)
        self.assertEqual(signup.status, SignupStatus.CANCELLED)

    def test_registered_user_without_signup_can_decline(self) -> None:
        user = CustomUser.objects.create(username="bob", discordId="900000000000000002")
        result = handle_decline_button(self.event.pk, "900000000000000002")
        self.assertEqual(result["action"], "declined")
        signup = EventSignup.objects.get(event=self.event, user=user)
        self.assertEqual(signup.status, SignupStatus.CANCELLED)

    def test_second_decline_reports_already_declined(self) -> None:
        handle_decline_button(self.event.pk, "900000000000000003", "carol")
        result = handle_decline_button(self.event.pk, "900000000000000003", "carol")
        self.assertEqual(result["action"], "already_declined")

    def test_missing_event(self) -> None:
        result = handle_decline_button(999999, "900000000000000004", "dave")
        self.assertEqual(result["action"], "error")
