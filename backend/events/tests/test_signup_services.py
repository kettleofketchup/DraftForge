from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone as tz

from app.models import CustomUser, Organization, PositionsModel
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.services import process_rsvp, staff_add_signup


class StaffAddSignupTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = CustomUser.objects.create_user(username="staff_a", password="x")
        cls.admin.positions = PositionsModel.objects.create()
        cls.admin.save()
        cls.user = CustomUser.objects.create_user(username="player_a", password="x")
        cls.user.positions = PositionsModel.objects.create()
        cls.user.save()
        cls.org = Organization.objects.create(name="StaffAdd Org", owner=cls.admin)

    def _make_event(self, state):
        return Event.objects.create(
            organization=self.org,
            name=f"Test {state}",
            scheduled_at=tz.now() + timedelta(days=1),
            state=state,
            created_by=self.admin,
            tournament_name="T",
            max_players=10,
        )

    def test_staff_add_succeeds_in_signups_open(self):
        event = self._make_event(EventState.SIGNUPS_OPEN)
        signup = staff_add_signup(event, self.user)
        assert signup.pk is not None
        assert signup.event_id == event.pk

    def test_staff_add_succeeds_in_roll_call(self):
        event = self._make_event(EventState.ROLL_CALL)
        signup = staff_add_signup(event, self.user)
        assert signup.pk is not None

    def test_staff_add_rejects_other_states(self):
        for state in (
            EventState.UPCOMING,
            EventState.IN_PROGRESS,
            EventState.COMPLETED,
            EventState.CANCELLED,
        ):
            event = self._make_event(state)
            with self.assertRaises(ValueError):
                staff_add_signup(event, self.user)

    def test_process_rsvp_still_rejects_roll_call(self):
        """Regression: public path stays locked during roll call."""
        event = self._make_event(EventState.ROLL_CALL)
        with self.assertRaises(ValueError):
            process_rsvp(event, self.user)

    def test_process_rsvp_still_rejects_other_states(self):
        for state in (
            EventState.UPCOMING,
            EventState.IN_PROGRESS,
            EventState.COMPLETED,
            EventState.CANCELLED,
        ):
            event = self._make_event(state)
            with self.assertRaises(ValueError):
                process_rsvp(event, self.user)

    @patch("events.services.invalidate_after_commit")
    def test_staff_add_invalidates_cache(self, mock_invalidate):
        event = self._make_event(EventState.ROLL_CALL)
        staff_add_signup(event, self.user)
        mock_invalidate.assert_called_with(event)

    def test_staff_add_waitlists_when_at_capacity(self):
        event = self._make_event(EventState.ROLL_CALL)
        event.max_players = 1
        event.save()
        # Pre-fill capacity with another user
        other = CustomUser.objects.create_user(username="other", password="x")
        other.positions = PositionsModel.objects.create()
        other.save()
        EventSignup.objects.create(
            event=event,
            user=other,
            status=SignupStatus.APPROVED,
        )
        signup = staff_add_signup(event, self.user)
        assert signup.status == SignupStatus.WAITLISTED
        assert signup.waitlist_position == 1

    def test_staff_add_rejects_duplicate_active_signup(self):
        event = self._make_event(EventState.ROLL_CALL)
        EventSignup.objects.create(
            event=event,
            user=self.user,
            status=SignupStatus.APPROVED,
        )
        with self.assertRaises(ValueError):
            staff_add_signup(event, self.user)

    def test_staff_add_re_rsvps_after_cancellation(self):
        """Cancelled signups can be staff-added again (covers _create_signup re-RSVP branch)."""
        event = self._make_event(EventState.ROLL_CALL)
        EventSignup.objects.create(
            event=event,
            user=self.user,
            status=SignupStatus.CANCELLED,
        )
        signup = staff_add_signup(event, self.user)
        # The original cancelled row was deleted; the new one should NOT be cancelled.
        assert signup.status != SignupStatus.CANCELLED

    def test_staff_add_auto_confirm_during_roll_call(self):
        """Auto-confirm + roll_call_enabled=False adds the user to the tournament."""
        event = self._make_event(EventState.ROLL_CALL)
        event.auto_approve = True
        event.auto_confirm = True
        event.roll_call_enabled = False
        # Avoid require_* gates so check_requirements returns True
        event.require_steam_id = False
        event.require_mmr_verified = False
        event.require_profile_complete = False
        event.save()
        signup = staff_add_signup(event, self.user)
        assert signup.status == SignupStatus.CONFIRMED

    @patch("events.services.invalidate_after_commit")
    def test_process_rsvp_still_invalidates_cache(self, mock_invalidate):
        """Regression guard: extracting _create_signup must not drop the public-path invalidation."""
        event = self._make_event(EventState.SIGNUPS_OPEN)
        process_rsvp(event, self.user)
        mock_invalidate.assert_called_with(event)
