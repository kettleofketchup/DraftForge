from datetime import timedelta

from django.test import TestCase
from django.utils import timezone as tz

from events.models import Event, EventSignup, EventState, SignupStatus, SignupType
from events.tests.base import EventTestCase


class SignupProcessingTests(EventTestCase):
    def setUp(self):
        self.event = Event.objects.create(
            organization=self.org,
            name="Signup Test",
            scheduled_at=tz.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
            tournament_name="Test",
            tournament_league=self.league,
        )

    def test_rsvp_creates_signup(self):
        from events.services import process_rsvp

        signup = process_rsvp(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.RSVP)
        self.assertEqual(signup.signup_type, SignupType.USER)

    def test_rsvp_duplicate_raises(self):
        from events.services import process_rsvp

        process_rsvp(self.event, self.user)
        with self.assertRaises(ValueError):
            process_rsvp(self.event, self.user)

    def test_rsvp_when_not_signups_open_raises(self):
        from events.services import process_rsvp

        self.event.state = EventState.UPCOMING
        self.event.save(update_fields=["state"])
        with self.assertRaises(ValueError):
            process_rsvp(self.event, self.user)

    def test_auto_approve_requirements_met(self):
        from events.services import process_rsvp

        self.event.auto_approve = True
        self.event.require_steam_id = True
        self.event.save()
        signup = process_rsvp(self.event, self.user)  # user has steamid
        self.assertEqual(signup.status, SignupStatus.APPROVED)

    def test_auto_approve_requirements_not_met(self):
        from events.services import process_rsvp

        self.event.auto_approve = True
        self.event.require_steam_id = True
        self.event.save()
        signup = process_rsvp(self.event, self.user_incomplete)  # no steamid
        self.assertEqual(signup.status, SignupStatus.PENDING_APPROVAL)

    def test_auto_approve_and_auto_confirm(self):
        from events.services import process_rsvp

        self.event.auto_approve = True
        self.event.auto_confirm = True
        self.event.save()
        signup = process_rsvp(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.CONFIRMED)

    def test_no_auto_approve_stays_rsvp(self):
        from events.services import process_rsvp

        signup = process_rsvp(self.event, self.user)
        self.assertEqual(signup.status, SignupStatus.RSVP)

    def test_waitlist_when_max_players_reached(self):
        from events.services import process_rsvp

        self.event.max_players = 1
        self.event.save()
        process_rsvp(self.event, self.user)
        signup2 = process_rsvp(self.event, self.user_incomplete)
        self.assertEqual(signup2.status, SignupStatus.WAITLISTED)
        self.assertEqual(signup2.waitlist_position, 1)

    def test_approve_signup(self):
        from events.services import approve_signup, process_rsvp

        signup = process_rsvp(self.event, self.user)
        approved = approve_signup(signup)
        self.assertEqual(approved.status, SignupStatus.APPROVED)

    def test_approve_only_from_valid_states(self):
        from events.services import approve_signup

        signup = EventSignup.objects.create(
            event=self.event,
            user=self.user,
            status=SignupStatus.CONFIRMED,
        )
        with self.assertRaises(ValueError):
            approve_signup(signup)

    def test_reject_signup(self):
        from events.services import process_rsvp, reject_signup

        signup = process_rsvp(self.event, self.user)
        rejected = reject_signup(signup)
        self.assertEqual(rejected.status, SignupStatus.REJECTED)

    def test_confirm_signup(self):
        from events.services import approve_signup, confirm_signup, process_rsvp

        signup = process_rsvp(self.event, self.user)
        signup = approve_signup(signup)
        confirmed = confirm_signup(signup)
        self.assertEqual(confirmed.status, SignupStatus.CONFIRMED)

    def test_confirm_only_approved(self):
        from events.services import confirm_signup, process_rsvp

        signup = process_rsvp(self.event, self.user)
        with self.assertRaises(ValueError):
            confirm_signup(signup)

    def test_cancel_signup(self):
        from events.services import cancel_signup, process_rsvp

        signup = process_rsvp(self.event, self.user)
        cancelled = cancel_signup(signup)
        self.assertEqual(cancelled.status, SignupStatus.CANCELLED)


class WaitlistPromotionTests(EventTestCase):
    def setUp(self):
        self.event = Event.objects.create(
            organization=self.org,
            name="Waitlist Test",
            scheduled_at=tz.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
            tournament_name="Test",
            tournament_league=self.league,
            max_players=1,
        )

    def test_cancel_promotes_next_waitlisted(self):
        from events.services import cancel_signup, process_rsvp

        signup1 = process_rsvp(self.event, self.user)
        signup2 = process_rsvp(self.event, self.user_incomplete)
        self.assertEqual(signup2.status, SignupStatus.WAITLISTED)
        cancel_signup(signup1)
        signup2.refresh_from_db()
        self.assertIn(
            signup2.status,
            [SignupStatus.RSVP, SignupStatus.APPROVED, SignupStatus.CONFIRMED],
        )
        self.assertIsNone(signup2.waitlist_position)

    def test_reject_promotes_next_waitlisted(self):
        from events.services import process_rsvp, reject_signup

        signup1 = process_rsvp(self.event, self.user)
        signup2 = process_rsvp(self.event, self.user_incomplete)
        reject_signup(signup1)
        signup2.refresh_from_db()
        self.assertNotEqual(signup2.status, SignupStatus.WAITLISTED)

    def test_promotion_respects_order(self):
        from app.models import CustomUser, PositionsModel
        from events.services import cancel_signup, process_rsvp

        user3 = CustomUser.objects.create_user(username="third", password="p")
        user3.positions = PositionsModel.objects.create()
        user3.save()

        signup1 = process_rsvp(self.event, self.user)
        signup2 = process_rsvp(self.event, self.user_incomplete)
        signup3 = process_rsvp(self.event, user3)
        self.assertEqual(signup2.waitlist_position, 1)
        self.assertEqual(signup3.waitlist_position, 2)
        cancel_signup(signup1)
        signup2.refresh_from_db()
        signup3.refresh_from_db()
        self.assertNotEqual(signup2.status, SignupStatus.WAITLISTED)
        self.assertEqual(signup3.status, SignupStatus.WAITLISTED)
