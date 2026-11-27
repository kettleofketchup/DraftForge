from typing import Any
from unittest.mock import patch

from events.constants import SignupAction, SignupStatus
from events.ledger import (
    REMOVED_STATUS_FOR,
    RESTORABLE_ACTIONS,
    latest_restorable_withdrawal,
    record_signup_change,
    snapshot,
)
from events.models import Event, EventSignup, SignupLedgerEntry
from events.schemas import SignupSnapshot
from events.services import (
    cancel_signup,
    decline_signup,
    process_rsvp,
    reject_signup,
)
from events.tests.base import EventTestCase
from events.tests.test_signup_ledger_contract import LedgerContractMixin


@patch("events.services.notify_signup_changed")
class RestorableLookupTests(LedgerContractMixin, EventTestCase):
    def _row(self, signup: EventSignup) -> EventSignup:
        return EventSignup.objects.nocache().get(pk=signup.pk)

    def _withdrawn(self, event: Event | None = None) -> tuple[EventSignup, str]:
        event = event or self.make_event()
        signup = process_rsvp(event, self.subject, actor=self.member_actor)
        prior = signup.status
        cancel_signup(signup, actor=self.member_actor)
        return self._row(signup), prior

    def _later(
        self,
        signup: EventSignup,
        action: SignupAction,
        *,
        after_status: str,
    ) -> SignupLedgerEntry:
        after = snapshot(signup).model_copy(update={"status": after_status})
        return record_signup_change(
            event=signup.event,
            subject=signup.user,
            actor=self.staff_actor,
            action=action,
            signup=signup,
            before=snapshot(signup),
            after=after,
        )

    def test_constants(self, _notify: Any) -> None:
        self.assertEqual(
            RESTORABLE_ACTIONS,
            frozenset(
                {SignupAction.WITHDREW, SignupAction.DECLINED, SignupAction.REJECTED}
            ),
        )
        self.assertEqual(
            REMOVED_STATUS_FOR,
            {
                SignupAction.WITHDREW: SignupStatus.CANCELLED,
                SignupAction.DECLINED: SignupStatus.CANCELLED,
                SignupAction.REJECTED: SignupStatus.REJECTED,
            },
        )

    def test_withdrew_entry_is_restorable(self, _notify: Any) -> None:
        signup, prior = self._withdrawn()

        entry = latest_restorable_withdrawal(signup)

        assert entry is not None
        self.assertEqual(entry.action, SignupAction.WITHDREW)
        self.assertEqual(entry.before["status"], prior)

    def test_rejected_and_declined_are_restorable(self, _notify: Any) -> None:
        event = self.make_event()
        rejected = process_rsvp(event, self.subject, actor=self.member_actor)
        reject_signup(rejected, actor=self.staff_actor)
        declined = process_rsvp(event, self.make_user(), actor=self.staff_actor)
        decline_signup(event, declined.user, actor=self.member_actor)

        rejected_entry = latest_restorable_withdrawal(self._row(rejected))
        declined_entry = latest_restorable_withdrawal(self._row(declined))

        assert rejected_entry is not None and declined_entry is not None
        self.assertEqual(rejected_entry.action, SignupAction.REJECTED)
        self.assertEqual(declined_entry.action, SignupAction.DECLINED)

    def test_bare_decline_returns_none(self, _notify: Any) -> None:
        signup = decline_signup(
            self.make_event(), self.subject, actor=self.member_actor
        )

        self.assertIsNone(latest_restorable_withdrawal(self._row(signup)))

    def test_no_history_returns_none(self, _notify: Any) -> None:
        signup = EventSignup.objects.create(
            event=self.make_event(), user=self.subject, status=SignupStatus.CANCELLED
        )

        self.assertIsNone(latest_restorable_withdrawal(signup))

    def test_after_status_mismatch_returns_none(self, _notify: Any) -> None:
        signup, _prior = self._withdrawn()
        EventSignup.objects.filter(pk=signup.pk).update(status=SignupStatus.WAITLISTED)

        self.assertIsNone(latest_restorable_withdrawal(self._row(signup)))

    def test_resignup_then_withdraw_uses_latest(self, _notify: Any) -> None:
        event = self.make_event(line_withdraw_forfeits=True)
        signup = process_rsvp(event, self.subject, actor=self.member_actor)
        s1 = self._row(signup).line_seq
        cancel_signup(signup, actor=self.member_actor)
        process_rsvp(event, self.make_user(), actor=self.staff_actor)
        again = process_rsvp(event, self.subject, actor=self.member_actor)
        s2 = self._row(again).line_seq
        self.assertNotEqual(s1, s2)
        cancel_signup(self._row(again), actor=self.member_actor)

        entry = latest_restorable_withdrawal(self._row(signup))

        second = (
            SignupLedgerEntry.objects.filter(
                signup=signup, action=SignupAction.WITHDREW
            )
            .order_by("-occurred_at", "-pk")
            .first()
        )
        assert entry is not None and second is not None
        self.assertEqual(entry.pk, second.pk)
        self.assertEqual(entry.before["line_seq"], s2)

    def test_already_voided_returns_none(self, _notify: Any) -> None:
        signup, prior = self._withdrawn()
        self._later(signup, SignupAction.VOIDED_WITHDRAWAL, after_status=prior)

        self.assertIsNone(latest_restorable_withdrawal(self._row(signup)))

    def test_later_moved_event_disqualifies(self, _notify: Any) -> None:
        signup, _prior = self._withdrawn()
        self._later(
            signup, SignupAction.MOVED_EVENT, after_status=SignupStatus.CANCELLED
        )

        self.assertIsNone(latest_restorable_withdrawal(self._row(signup)))

    def test_later_transferred_out_disqualifies(self, _notify: Any) -> None:
        signup, _prior = self._withdrawn()
        self._later(
            signup, SignupAction.TRANSFERRED_OUT, after_status=SignupStatus.CANCELLED
        )

        self.assertIsNone(latest_restorable_withdrawal(self._row(signup)))

    def test_later_status_neutral_entry_does_not_disqualify(self, _notify: Any) -> None:
        signup, _prior = self._withdrawn()
        withdrew = SignupLedgerEntry.objects.get(
            signup=signup, action=SignupAction.WITHDREW
        )
        self._later(
            signup,
            SignupAction.READY_CHECK_WITHDRAWN,
            after_status=SignupStatus.CANCELLED,
        )
        record_signup_change(
            event=signup.event,
            subject=signup.user,
            actor=self.staff_actor,
            action=SignupAction.READY_CHECK_NUDGED,
            signup=signup,
        )

        entry = latest_restorable_withdrawal(self._row(signup))

        assert entry is not None
        self.assertEqual(entry.pk, withdrew.pk)

    def test_before_status_removed_returns_none(self, _notify: Any) -> None:
        signup = EventSignup.objects.create(
            event=self.make_event(), user=self.subject, status=SignupStatus.CANCELLED
        )
        removed = snapshot(signup)
        record_signup_change(
            event=signup.event,
            subject=signup.user,
            actor=self.staff_actor,
            action=SignupAction.WITHDREW,
            signup=signup,
            before=removed,
            after=removed,
        )

        self.assertIsNone(latest_restorable_withdrawal(signup))

    def test_null_after_falls_back_to_removed_status(self, _notify: Any) -> None:
        signup = EventSignup.objects.create(
            event=self.make_event(), user=self.subject, status=SignupStatus.REJECTED
        )
        record_signup_change(
            event=signup.event,
            subject=signup.user,
            actor=self.staff_actor,
            action=SignupAction.REJECTED,
            signup=signup,
            before=SignupSnapshot(
                status=SignupStatus.APPROVED, commitment="main", rsvp_class="main"
            ),
            after=None,
        )

        entry = latest_restorable_withdrawal(signup)

        assert entry is not None
        self.assertEqual(entry.action, SignupAction.REJECTED)
