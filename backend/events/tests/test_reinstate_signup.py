"""Tests for `events.services.reinstate_signup`.

Covers two distinct behaviors gated on event state:

  1. signups_open  — restore a CANCELLED signup back into the active list
                     (RSVP if there's room, WAITLISTED if the event is full).
                     Must reject anything other than CANCELLED.

  2. roll_call     — restore a CANCELLED or REJECTED signup directly to
                     APPROVED so admins can undo a roll-call rejection
                     without leaving the rollcall page.

  3. anything else — raise ValueError; reinstate is not allowed outside
                     the two states above.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone as tz

from app.models import CustomUser, Organization, PositionsModel
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.services import reinstate_signup


class ReinstateSignupTest(TestCase):
    """Regression coverage for the two-state reinstate path added on PR #203."""

    def setUp(self):
        self.org = Organization.objects.create(name="Reinstate Org")
        self.user = CustomUser.objects.create(
            username="reinstate_user",
            positions=PositionsModel.objects.create(),
        )

    def _make_event(self, *, state, max_players=None):
        return Event.objects.create(
            name=f"Event ({state})",
            organization=self.org,
            scheduled_at=tz.now() + timedelta(days=1),
            timezone="UTC",
            roll_call_enabled=False,
            state=state,
            max_players=max_players,
        )

    def _make_signup(self, event, *, status, user=None):
        return EventSignup.objects.create(
            event=event,
            user=user or self.user,
            status=status,
        )

    # ---- roll_call branch -------------------------------------------------

    @patch("events.services.notify_signup_changed")
    def test_roll_call_rejected_to_approved(self, _notify):
        """Rejected → Approved during roll_call (the rollcall 'Restore' flow)."""
        event = self._make_event(state=EventState.ROLL_CALL)
        signup = self._make_signup(event, status=SignupStatus.REJECTED)

        result = reinstate_signup(signup)

        self.assertEqual(result.status, SignupStatus.APPROVED)
        self.assertIsNone(result.waitlist_position)

    @patch("events.services.notify_signup_changed")
    def test_roll_call_cancelled_to_approved(self, _notify):
        """Cancelled → Approved during roll_call (admin-removed player restored)."""
        event = self._make_event(state=EventState.ROLL_CALL)
        signup = self._make_signup(event, status=SignupStatus.CANCELLED)

        result = reinstate_signup(signup)

        self.assertEqual(result.status, SignupStatus.APPROVED)
        self.assertIsNone(result.waitlist_position)

    @patch("events.services.notify_signup_changed")
    def test_roll_call_rejects_non_terminal_signup(self, _notify):
        """During roll_call, only REJECTED/CANCELLED can be reinstated.

        Reinstating an APPROVED or CONFIRMED signup should raise — the admin
        meant to do something else (unconfirm, confirm) and we shouldn't
        silently rewrite state.
        """
        event = self._make_event(state=EventState.ROLL_CALL)
        signup = self._make_signup(event, status=SignupStatus.APPROVED)

        with self.assertRaisesRegex(
            ValueError, "Only removed or rejected signups can be reinstated"
        ):
            reinstate_signup(signup)

    # ---- signups_open branch (existing behavior preserved) ----------------

    @patch("events.services.notify_signup_changed")
    def test_signups_open_cancelled_to_rsvp_when_room(self, _notify):
        """Cancelled → RSVP in signups_open with capacity available."""
        event = self._make_event(
            state=EventState.SIGNUPS_OPEN, max_players=10
        )
        signup = self._make_signup(event, status=SignupStatus.CANCELLED)

        result = reinstate_signup(signup)

        self.assertEqual(result.status, SignupStatus.RSVP)
        self.assertIsNone(result.waitlist_position)

    @patch("events.services.notify_signup_changed")
    def test_signups_open_cancelled_to_waitlisted_when_full(self, _notify):
        """Cancelled → Waitlisted when active signup count is at max_players."""
        event = self._make_event(
            state=EventState.SIGNUPS_OPEN, max_players=2
        )
        # Fill the event with two active signups.
        u1 = CustomUser.objects.create(
            username="rsvp_a", positions=PositionsModel.objects.create()
        )
        u2 = CustomUser.objects.create(
            username="rsvp_b", positions=PositionsModel.objects.create()
        )
        self._make_signup(event, status=SignupStatus.RSVP, user=u1)
        self._make_signup(event, status=SignupStatus.RSVP, user=u2)
        signup = self._make_signup(event, status=SignupStatus.CANCELLED)

        result = reinstate_signup(signup)

        self.assertEqual(result.status, SignupStatus.WAITLISTED)
        # First slot in the waitlist (no one ahead).
        self.assertEqual(result.waitlist_position, 1)

    @patch("events.services.notify_signup_changed")
    def test_signups_open_rejected_raises(self, _notify):
        """During signups_open, only CANCELLED is reinstatable; REJECTED is terminal."""
        event = self._make_event(state=EventState.SIGNUPS_OPEN)
        signup = self._make_signup(event, status=SignupStatus.REJECTED)

        with self.assertRaisesRegex(
            ValueError, "Only cancelled signups can be reinstated"
        ):
            reinstate_signup(signup)

    # ---- other states all reject -----------------------------------------

    @patch("events.services.notify_signup_changed")
    def test_upcoming_state_raises(self, _notify):
        event = self._make_event(state=EventState.UPCOMING)
        signup = self._make_signup(event, status=SignupStatus.CANCELLED)

        with self.assertRaisesRegex(ValueError, "not accepting signups"):
            reinstate_signup(signup)

    @patch("events.services.notify_signup_changed")
    def test_in_progress_state_raises(self, _notify):
        event = self._make_event(state=EventState.IN_PROGRESS)
        signup = self._make_signup(event, status=SignupStatus.CANCELLED)

        with self.assertRaisesRegex(ValueError, "not accepting signups"):
            reinstate_signup(signup)

    @patch("events.services.notify_signup_changed")
    def test_completed_state_raises(self, _notify):
        event = self._make_event(state=EventState.COMPLETED)
        signup = self._make_signup(event, status=SignupStatus.CANCELLED)

        with self.assertRaisesRegex(ValueError, "not accepting signups"):
            reinstate_signup(signup)
