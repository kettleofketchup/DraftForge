from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.test import RequestFactory

from app.models import CustomUser
from events.admission import NOT_ACCEPTING_MESSAGE
from events.constants import (
    ActorRole,
    Commitment,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
    StaffReasonPolicy,
)
from events.ledger import (
    REMOVED_STATUS_FOR,
    RESTORABLE_ACTIONS,
    SignupActor,
    latest_restorable_withdrawal,
    record_signup_change,
    snapshot,
)
from events.line import waitlist_rank
from events.models import Event, EventSignup, SignupLedgerEntry
from events.overrides import StaffReasonRequired
from events.schemas import SignupSnapshot
from events.services import (
    VOID_NO_HISTORY_MESSAGE,
    VOID_NOT_REMOVED_MESSAGE,
    _next_waitlist_position,
    cancel_signup,
    create_tentative_signup,
    decline_signup,
    process_rsvp,
    reject_signup,
    void_withdrawal,
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


@patch("events.services.notify_signup_changed")
class VoidWithdrawalCoreTests(LedgerContractMixin, EventTestCase):
    def _row(self, signup: EventSignup) -> EventSignup:
        return EventSignup.objects.nocache().get(pk=signup.pk)

    def _join(self, event: Event, user: CustomUser | None = None) -> EventSignup:
        user = user or self.make_user()
        actor = SignupActor(user=user, role=ActorRole.MEMBER, means=SignupMeans.WEB)
        return process_rsvp(event, user, actor=actor)

    def _withdraw(self, signup: EventSignup) -> SignupLedgerEntry:
        actor = SignupActor(
            user=signup.user, role=ActorRole.MEMBER, means=SignupMeans.WEB
        )
        cancel_signup(self._row(signup), actor=actor)
        entry = SignupLedgerEntry.objects.filter(
            signup=signup, action=SignupAction.WITHDREW
        ).latest("pk")
        return entry

    def _void_entries(self, signup: EventSignup) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                signup=signup, action=SignupAction.VOIDED_WITHDRAWAL
            )
        )

    def _other_staff(self) -> SignupActor:
        user = self.make_user()
        self.org.staff.add(user)
        return SignupActor(user=user, role=ActorRole.STAFF, means=SignupMeans.WEB)

    def test_restores_exact_fields(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._join(event, self.subject)
        withdrew = self._withdraw(signup)
        later = signup.signed_up_at + timedelta(hours=1)
        EventSignup.objects.filter(pk=signup.pk).update(
            line_seq=999, signed_up_at=later
        )

        restored = void_withdrawal(self._row(signup), actor=self.staff_actor)

        snap = SignupSnapshot.model_validate(withdrew.before)
        row = self._row(restored)
        self.assertEqual(row.status, snap.status)
        self.assertEqual(row.commitment, snap.commitment)
        self.assertEqual(row.rsvp_class, snap.rsvp_class)
        self.assertEqual(row.signed_up_at, snap.signed_up_at)
        self.assertEqual(row.line_seq, snap.line_seq)
        self.assertEqual(restored.status, snap.status)

    def test_maybe_restored_as_tentative_maybe(self, _notify: Any) -> None:
        event = self.make_event()
        signup = create_tentative_signup(event, self.subject, actor=self.member_actor)
        self._withdraw(signup)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        row = self._row(signup)
        self.assertEqual(row.status, SignupStatus.TENTATIVE)
        self.assertEqual(row.commitment, Commitment.MAYBE)

    def test_ledger_entry_shape(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._join(event, self.subject)
        withdrew = self._withdraw(signup)

        void_withdrawal(
            self._row(signup), actor=self.staff_actor, reason="mistaken withdrawal"
        )

        [entry] = self._void_entries(signup)
        self.assertEqual(entry.action, SignupAction.VOIDED_WITHDRAWAL)
        self.assertEqual(entry.reason, "mistaken withdrawal")
        self.assertEqual(entry.caused_by_id, withdrew.pk)
        self.assertEqual(entry.rules_overridden, [])
        self.assertEqual(entry.before["status"], SignupStatus.CANCELLED)
        self.assertEqual(entry.after["status"], withdrew.before["status"])
        self.assertEqual(entry.after["extra"], {"voided_entry_id": withdrew.pk})

    def test_staff_power_from_withdrawal_does_not_leak(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._join(event, self.staff)
        self_staff = SignupActor(
            user=self.staff,
            role=ActorRole.MEMBER,
            means=SignupMeans.WEB,
            staff_power=True,
        )
        cancel_signup(self._row(signup), actor=self_staff)
        withdrew = SignupLedgerEntry.objects.get(
            signup=signup, action=SignupAction.WITHDREW
        )
        self.assertIs(withdrew.after["extra"]["staff_power"], True)

        void_withdrawal(self._row(signup), actor=self._other_staff())

        [entry] = self._void_entries(signup)
        self.assertNotIn("staff_power", entry.after["extra"])
        self.assertEqual(entry.after["extra"]["voided_entry_id"], withdrew.pk)

    def test_before_extra_is_carried_forward(self, _notify: Any) -> None:
        signup = EventSignup.objects.create(
            event=self.make_event(), user=self.subject, status=SignupStatus.CANCELLED
        )
        before = snapshot(signup).model_copy(
            update={
                "status": SignupStatus.APPROVED,
                "extra": {"e4_marker": 1, "staff_power": True},
            }
        )
        withdrew = record_signup_change(
            event=signup.event,
            subject=signup.user,
            actor=self.member_actor,
            action=SignupAction.WITHDREW,
            signup=signup,
            before=before,
            after=snapshot(signup),
        )

        void_withdrawal(self._row(signup), actor=self._other_staff())

        [entry] = self._void_entries(signup)
        self.assertEqual(
            entry.after["extra"], {"e4_marker": 1, "voided_entry_id": withdrew.pk}
        )
        self.assertEqual(self._row(signup).status, SignupStatus.APPROVED)

    def test_self_staff_void_adds_staff_power(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._join(event, self.staff)
        withdrew = self._withdraw(signup)
        request = RequestFactory().post("/")
        request.user = self.staff
        actor = SignupActor.for_request_on(request, self.staff, event, staff_only=True)

        void_withdrawal(self._row(signup), actor=actor)

        [entry] = self._void_entries(signup)
        self.assertEqual(
            entry.after["extra"],
            {"voided_entry_id": withdrew.pk, "staff_power": True},
        )

    def test_waitlisted_restore_sets_waitlist_position_and_rank(
        self, _notify: Any
    ) -> None:
        event = self.make_event(max_players=1)
        self._join(event)
        first = self._join(event)
        signup = self._join(event, self.subject)
        self._join(event)
        self.assertEqual(self._row(first).status, SignupStatus.WAITLISTED)
        self.assertEqual(waitlist_rank(self._row(signup)), 2)
        withdrew = self._withdraw(signup)
        self.assertEqual(withdrew.before["waitlist_position"], 2)
        expected_position = _next_waitlist_position(event)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        row = self._row(signup)
        self.assertEqual(row.status, SignupStatus.WAITLISTED)
        self.assertEqual(row.waitlist_position, expected_position)
        self.assertEqual(waitlist_rank(row), 2)
        [entry] = self._void_entries(signup)
        self.assertEqual(entry.after["waitlist_position"], 2)

    def test_waitlisted_restore_next_to_free_seat_is_promoted(
        self, _notify: Any
    ) -> None:
        event = self.make_event(max_players=1)
        seated = self._join(event)
        signup = self._join(event, self.subject)
        self.assertEqual(self._row(signup).status, SignupStatus.WAITLISTED)
        self._withdraw(signup)
        self._withdraw(seated)

        restored = void_withdrawal(self._row(signup), actor=self.staff_actor)

        row = self._row(signup)
        self.assertEqual(row.status, SignupStatus.APPROVED)
        self.assertEqual(restored.status, SignupStatus.APPROVED)
        [void_entry] = self._void_entries(signup)
        self.assertEqual(void_entry.after["status"], SignupStatus.WAITLISTED)
        promoted = SignupLedgerEntry.objects.get(
            signup=signup, action=SignupAction.PROMOTED
        )
        self.assertEqual(promoted.caused_by_id, void_entry.pk)

    def test_never_mutates_other_rows(self, _notify: Any) -> None:
        event = self.make_event(max_players=2)
        signup = self._join(event, self.subject)
        other = self._join(event)
        waiting = self._join(event)
        self.assertEqual(self._row(waiting).status, SignupStatus.WAITLISTED)
        self._withdraw(signup)
        self.assertEqual(self._row(waiting).status, SignupStatus.APPROVED)
        self._withdraw(other)
        promoted = self._row(waiting)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        after = self._row(waiting)
        self.assertEqual(after.status, promoted.status)
        self.assertEqual(after.line_seq, promoted.line_seq)
        self.assertEqual(after.waitlist_position, promoted.waitlist_position)
        self.assertEqual(self._row(signup).status, SignupStatus.APPROVED)

    def test_rejected_void_in_signups_open(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._join(event, self.subject)
        reject_signup(self._row(signup), actor=self.staff_actor)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        self.assertEqual(self._row(signup).status, SignupStatus.APPROVED)

    def test_non_removed_status_raises(self, _notify: Any) -> None:
        signup = self._join(self.make_event(), self.subject)

        with self.assertRaisesMessage(ValueError, VOID_NOT_REMOVED_MESSAGE):
            void_withdrawal(self._row(signup), actor=self.staff_actor)

    def test_no_history_raises(self, _notify: Any) -> None:
        signup = EventSignup.objects.create(
            event=self.make_event(), user=self.subject, status=SignupStatus.CANCELLED
        )

        with self.assertRaisesMessage(ValueError, VOID_NO_HISTORY_MESSAGE):
            void_withdrawal(signup, actor=self.staff_actor)

    def test_closed_event_raises(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._join(event, self.subject)
        self._withdraw(signup)
        stale = self._row(signup)
        Event.objects.filter(pk=event.pk).update(state=EventState.IN_PROGRESS)

        with self.assertRaisesMessage(ValueError, NOT_ACCEPTING_MESSAGE):
            void_withdrawal(stale, actor=self.staff_actor)
        self.assertEqual(self._void_entries(signup), [])

    def test_roll_call_event_is_voidable(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._join(event, self.subject)
        self._withdraw(signup)
        Event.objects.filter(pk=event.pk).update(state=EventState.ROLL_CALL)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        self.assertEqual(self._row(signup).status, SignupStatus.APPROVED)

    def test_double_void_from_stale_instance_records_once(self, _notify: Any) -> None:
        signup = self._join(self.make_event(), self.subject)
        self._withdraw(signup)
        first = self._row(signup)
        stale = self._row(signup)

        void_withdrawal(first, actor=self.staff_actor)
        with self.assertRaisesMessage(ValueError, VOID_NOT_REMOVED_MESSAGE):
            void_withdrawal(stale, actor=self.staff_actor)
        with self.assertRaisesMessage(ValueError, VOID_NOT_REMOVED_MESSAGE):
            void_withdrawal(first, actor=self.staff_actor)

        self.assertEqual(len(self._void_entries(signup)), 1)
        self.assertEqual(stale.status, SignupStatus.APPROVED)

    def test_reason_required_under_placements_policy(self, _notify: Any) -> None:
        event = self.make_event(staff_reason_policy=StaffReasonPolicy.PLACEMENTS)
        signup = self._join(event, self.subject)
        self._withdraw(signup)

        with self.assertRaises(StaffReasonRequired):
            void_withdrawal(self._row(signup), actor=self.staff_actor, reason="  ")

        self.assertEqual(self._row(signup).status, SignupStatus.CANCELLED)
        self.assertEqual(self._void_entries(signup), [])

    def test_reason_optional_under_optional_policy(self, _notify: Any) -> None:
        event = self.make_event(staff_reason_policy=StaffReasonPolicy.OPTIONAL)
        signup = self._join(event, self.subject)
        self._withdraw(signup)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        self.assertEqual(self._row(signup).status, SignupStatus.APPROVED)
