from collections.abc import Sequence
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.test import RequestFactory
from structlog.testing import capture_logs

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
from events.models import (
    Event,
    EventSignup,
    ReadyCheck,
    ReadyCheckEntry,
    SignupLedgerEntry,
)
from events.overrides import (
    OverrideReasonRequired,
    OverrideRequired,
    StaffReasonRequired,
)
from events.ready_check_constants import ReadyCheckEntryState
from events.schemas import SignupSnapshot
from events.services import (
    VOID_NO_HISTORY_MESSAGE,
    VOID_NOT_REMOVED_MESSAGE,
    VOID_OVER_CAPACITY_MESSAGE,
    _next_waitlist_position,
    cancel_signup,
    create_tentative_signup,
    create_tournament_for_event,
    decline_signup,
    process_rsvp,
    reject_signup,
    void_withdrawal,
)
from events.tests.base import EventTestCase
from events.tests.test_signup_ledger_contract import LedgerContractMixin
from org.settings_constants import StaffOverridePolicy
from tests.helpers.override_policy import set_org_override_policy
from tournament.models import Team, Tournament


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


class _VoidFixtures(LedgerContractMixin, EventTestCase):
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
        return SignupLedgerEntry.objects.filter(
            signup=signup, action=SignupAction.WITHDREW
        ).latest("pk")

    def _void_entries(self, signup: EventSignup) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                signup=signup, action=SignupAction.VOIDED_WITHDRAWAL
            )
        )

    def _set_policy(
        self, policy: str, codes: Sequence[str] = ("over_capacity",)
    ) -> None:
        set_org_override_policy(self.org, policy, codes)


@patch("events.services.notify_signup_changed")
class VoidCapacityTests(_VoidFixtures):
    def setUp(self) -> None:
        super().setUp()
        self._set_policy(StaffOverridePolicy.CONFIRM)

    def _full_after_withdrawal(
        self,
    ) -> tuple[Event, EventSignup, EventSignup, SignupLedgerEntry]:
        event = self.make_event(max_players=2)
        self._join(event)
        signup = self._join(event, self.subject)
        waiting = self._join(event)
        self.assertEqual(self._row(waiting).status, SignupStatus.WAITLISTED)
        withdrew = self._withdraw(signup)
        self.assertEqual(self._row(waiting).status, SignupStatus.APPROVED)
        return event, signup, waiting, withdrew

    def test_full_event_confirm_requires_override(self, _notify: Any) -> None:
        _event, signup, _waiting, _withdrew = self._full_after_withdrawal()

        with self.assertRaises(OverrideRequired) as ctx:
            void_withdrawal(
                self._row(signup), actor=self.staff_actor, reason="mistaken"
            )

        [violation] = ctx.exception.violations
        self.assertEqual(violation.code, "over_capacity")
        self.assertEqual(violation.rule, "capacity")
        self.assertEqual(violation.category, "seating")
        self.assertEqual(violation.message, VOID_OVER_CAPACITY_MESSAGE)
        self.assertEqual(violation.params, {"capacity": 2, "seated": 2})
        self.assertFalse(ctx.exception.blocked)
        self.assertEqual(self._row(signup).status, SignupStatus.CANCELLED)
        self.assertEqual(self._void_entries(signup), [])

    def test_full_event_confirm_acknowledged_restores(self, _notify: Any) -> None:
        _event, signup, waiting, withdrew = self._full_after_withdrawal()
        promoted = self._row(waiting)

        void_withdrawal(
            self._row(signup),
            actor=self.staff_actor,
            reason="mistaken",
            acknowledged_codes=["over_capacity"],
        )

        snap = SignupSnapshot.model_validate(withdrew.before)
        row = self._row(signup)
        self.assertEqual(row.status, SignupStatus.APPROVED)
        self.assertEqual(row.line_seq, snap.line_seq)
        self.assertEqual(row.signed_up_at, snap.signed_up_at)
        self.assertEqual(row.commitment, snap.commitment)
        self.assertEqual(row.rsvp_class, snap.rsvp_class)
        after = self._row(waiting)
        self.assertEqual(after.status, promoted.status)
        self.assertEqual(after.line_seq, promoted.line_seq)
        [entry] = self._void_entries(signup)
        self.assertEqual(entry.rules_overridden, ["over_capacity"])
        self.assertEqual(entry.reason, "mistaken")

    def test_acknowledged_without_reason_raises_reason_required(
        self, _notify: Any
    ) -> None:
        _event, signup, _waiting, _withdrew = self._full_after_withdrawal()

        with self.assertRaises(OverrideReasonRequired):
            void_withdrawal(
                self._row(signup),
                actor=self.staff_actor,
                reason="",
                acknowledged_codes=["over_capacity"],
            )

        self.assertEqual(self._row(signup).status, SignupStatus.CANCELLED)
        self.assertEqual(self._void_entries(signup), [])

    def test_silent_policy_over_seats_and_records_code(self, _notify: Any) -> None:
        self._set_policy(StaffOverridePolicy.SILENT)
        _event, signup, waiting, _withdrew = self._full_after_withdrawal()
        promoted = self._row(waiting)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        self.assertEqual(self._row(signup).status, SignupStatus.APPROVED)
        after = self._row(waiting)
        self.assertEqual(after.status, promoted.status)
        self.assertEqual(after.line_seq, promoted.line_seq)
        [entry] = self._void_entries(signup)
        self.assertEqual(entry.rules_overridden, ["over_capacity"])

    def test_block_policy_blocks(self, _notify: Any) -> None:
        self._set_policy(StaffOverridePolicy.BLOCK)
        _event, signup, _waiting, _withdrew = self._full_after_withdrawal()

        with self.assertRaises(OverrideRequired) as ctx:
            void_withdrawal(
                self._row(signup),
                actor=self.staff_actor,
                reason="mistaken",
                acknowledged_codes=["over_capacity"],
            )

        self.assertTrue(ctx.exception.blocked)
        self.assertEqual(self._row(signup).status, SignupStatus.CANCELLED)
        self.assertEqual(self._void_entries(signup), [])

    def test_waitlisted_restore_on_full_event_needs_no_override(
        self, _notify: Any
    ) -> None:
        event = self.make_event(max_players=1)
        self._join(event)
        signup = self._join(event, self.subject)
        self.assertEqual(self._row(signup).status, SignupStatus.WAITLISTED)
        self._withdraw(signup)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        self.assertEqual(self._row(signup).status, SignupStatus.WAITLISTED)
        [entry] = self._void_entries(signup)
        self.assertEqual(entry.rules_overridden, [])

    def test_unknown_acknowledged_codes_ignored(self, _notify: Any) -> None:
        _event, signup, _waiting, _withdrew = self._full_after_withdrawal()

        with self.assertRaises(OverrideRequired):
            void_withdrawal(
                self._row(signup),
                actor=self.staff_actor,
                reason="mistaken",
                acknowledged_codes=["bogus"],
            )

        self.assertEqual(self._void_entries(signup), [])

    def test_override_required_is_logged(self, _notify: Any) -> None:
        _event, signup, _waiting, _withdrew = self._full_after_withdrawal()

        with capture_logs() as logs, self.assertRaises(OverrideRequired):
            void_withdrawal(self._row(signup), actor=self.staff_actor)

        [record] = [r for r in logs if r["event"] == "void_override_required"]
        self.assertEqual(record["system"], "events")
        self.assertEqual(record["subsystem"], "void")
        self.assertEqual(record["signup_id"], signup.pk)
        self.assertEqual(record["codes"], ["over_capacity"])
        self.assertIs(record["blocked"], False)


@patch("events.services.notify_mark_interested")
@patch("events.services.notify_signup_changed")
class VoidEligibilityRosterTests(_VoidFixtures):
    def _require_steam_id(self, event: Event) -> None:
        Event.objects.filter(pk=event.pk).update(require_steam_id=True)

    def test_restored_approved_clears_eligibility(self, *_mocks: Any) -> None:
        event = self.make_event()
        member = self.make_user()
        signup = self._join(event, member)
        self.assertEqual(self._row(signup).status, SignupStatus.APPROVED)
        self._withdraw(signup)
        self._require_steam_id(event)
        EventSignup.objects.filter(pk=signup.pk).update(
            unmet_requirements=["stale"], eligibility_reasons=[{"code": "stale"}]
        )

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        row = self._row(signup)
        self.assertEqual(row.status, SignupStatus.APPROVED)
        self.assertEqual(row.unmet_requirements, [])
        self.assertEqual(row.eligibility_reasons, [])
        self.assertIsNone(row.eligibility_checked_at)

    def _clear_stamp(self, signup: EventSignup) -> None:
        EventSignup.objects.filter(pk=signup.pk).update(
            unmet_requirements=[], eligibility_reasons=[], eligibility_checked_at=None
        )

    def test_restored_pending_approval_is_stamped(self, *_mocks: Any) -> None:
        event = self.make_event(require_steam_id=True)
        signup = self._join(event, self.make_user())
        self.assertEqual(self._row(signup).status, SignupStatus.PENDING_APPROVAL)
        self._withdraw(signup)
        self._clear_stamp(signup)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        row = self._row(signup)
        self.assertEqual(row.status, SignupStatus.PENDING_APPROVAL)
        self.assertNotEqual(row.eligibility_reasons, [])
        self.assertIsNotNone(row.eligibility_checked_at)

    def test_restored_rsvp_is_stamped(self, *_mocks: Any) -> None:
        event = self.make_event(auto_approve=False)
        signup = self._join(event, self.make_user())
        self.assertEqual(self._row(signup).status, SignupStatus.RSVP)
        self._withdraw(signup)
        self._require_steam_id(event)
        self._clear_stamp(signup)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        row = self._row(signup)
        self.assertEqual(row.status, SignupStatus.RSVP)
        self.assertNotEqual(row.eligibility_reasons, [])
        self.assertIsNotNone(row.eligibility_checked_at)

    def _tournament_event(self) -> Event:
        event = self.make_event(roll_call_enabled=False)
        create_tournament_for_event(event)
        event.refresh_from_db()
        return event

    def _roster(self, event: Event) -> set[int]:
        tournament = Tournament.objects.nocache().get(pk=event.tournament_id)
        return set(tournament.users.values_list("pk", flat=True))

    def test_roster_membership_readded(self, *_mocks: Any) -> None:
        event = self._tournament_event()
        member = self.make_user()
        signup = self._join(event, member)
        self.assertIn(member.pk, self._roster(event))
        self._withdraw(signup)
        self.assertNotIn(member.pk, self._roster(event))

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        self.assertEqual(self._row(signup).status, SignupStatus.APPROVED)
        self.assertIn(member.pk, self._roster(event))

    def test_team_membership_not_restored(self, *_mocks: Any) -> None:
        event = self._tournament_event()
        captain, member = self.make_user(), self.make_user()
        self._join(event, captain)
        signup = self._join(event, member)
        team = Team.objects.create(
            tournament=event.tournament, name="Void Team", captain=captain
        )
        team.members.add(captain, member)
        self._withdraw(signup)
        self.assertFalse(team.members.filter(pk=member.pk).exists())

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        self.assertIn(member.pk, self._roster(event))
        fresh = Team.objects.nocache().get(pk=team.pk)
        self.assertFalse(fresh.members.filter(pk=member.pk).exists())

    def _roll_call_with_check(self) -> tuple[Event, EventSignup, ReadyCheck]:
        event = self.make_event()
        signup = self._join(event, self.subject)
        Event.objects.filter(pk=event.pk).update(state=EventState.ROLL_CALL)
        check = ReadyCheck.objects.create(
            event=event,
            settings_snapshot={
                "ready_check_scope": "main_only",
                "effective_mode": "manual",
            },
        )
        self._withdraw(signup)
        return event, signup, check

    def test_live_ready_check_enrols_and_correlates(self, *_mocks: Any) -> None:
        _event, signup, check = self._roll_call_with_check()

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        entry = check.entries.get(user_id=signup.user_id)
        self.assertEqual(entry.signup_id, signup.pk)
        self.assertEqual(entry.state, ReadyCheckEntryState.PENDING)
        [void_entry] = self._void_entries(signup)
        self.assertEqual(void_entry.correlation_id, f"rc{check.pk}:void")

    def test_live_ready_check_dropped_entry_is_excused(self, *_mocks: Any) -> None:
        _event, signup, check = self._roll_call_with_check()
        ReadyCheckEntry.objects.create(
            ready_check=check,
            signup=signup,
            user_id=signup.user_id,
            state=ReadyCheckEntryState.DROPPED,
        )

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        entry = check.entries.get(user_id=signup.user_id)
        self.assertEqual(entry.state, ReadyCheckEntryState.EXCUSED)

    def test_no_ready_check_leaves_correlation_empty(self, *_mocks: Any) -> None:
        signup = self._join(self.make_event(), self.subject)
        self._withdraw(signup)

        void_withdrawal(self._row(signup), actor=self.staff_actor)

        [void_entry] = self._void_entries(signup)
        self.assertEqual(void_entry.correlation_id, "")
