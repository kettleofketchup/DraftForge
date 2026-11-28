from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

from django.utils import timezone
from structlog.testing import capture_logs

from app.models import CustomUser
from events.capacity import count_seats
from events.constants import (
    ActorRole,
    Commitment,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
)
from events.eligibility import EligibilityResult, Reason, ReasonCode, Rule, Severity
from events.exceptions import SpotTransferRefused
from events.ledger import SignupActor, latest_restorable_withdrawal
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import (
    TRANSFER_EVENT_STATES,
    SpotTransferResult,
    cancel_signup,
    create_tentative_signup,
    create_tournament_for_event,
    process_rsvp,
    reinstate_signup,
    transfer_spot,
)
from events.tests.base import EventTestCase
from tournament.models import Tournament

LineState = tuple[str, int | None, datetime | None, int | None]

GENERIC = {
    "code": "recipient_ineligible",
    "rule": "eligibility",
    "message": "Not eligible for this event",
}


def member(user: CustomUser) -> SignupActor:
    return SignupActor(user=user, role=ActorRole.MEMBER, means=SignupMeans.WEB)


class _TransferFixtures(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.notify_changed: MagicMock = patch(
            "events.services.notify_signup_changed"
        ).start()
        self.notify_interested: MagicMock = patch(
            "events.services.notify_mark_interested"
        ).start()
        self.addCleanup(patch.stopall)
        self.staff_actor = SignupActor(
            user=self.admin, role=ActorRole.STAFF, means=SignupMeans.WEB
        )

    def transfer_event(self, **overrides: Any) -> Event:
        fields: dict[str, Any] = {
            "allow_spot_transfer": True,
            "auto_approve": True,
            "auto_confirm": True,
        }
        fields.update(overrides)
        return self.make_event(**fields)

    def join(self, event: Event, user: CustomUser | None = None) -> EventSignup:
        user = user or self.make_user()
        return process_rsvp(event, user, actor=member(user))

    def row(self, signup: EventSignup) -> EventSignup:
        return EventSignup.objects.nocache().get(pk=signup.pk)

    def set_status(self, signup: EventSignup, status: str) -> EventSignup:
        EventSignup.objects.filter(pk=signup.pk).update(status=status)
        return self.row(signup)

    def line_state(self, event: Event) -> dict[int, LineState]:
        return {
            s.pk: (s.status, s.line_seq, s.signed_up_at, s.waitlist_position)
            for s in EventSignup.objects.nocache().filter(event=event)
        }

    def ledger_count(self, event: Event) -> int:
        return SignupLedgerEntry.objects.filter(event=event).count()

    def give(
        self, giver: EventSignup, recipient: CustomUser, **kwargs: Any
    ) -> SpotTransferResult:
        return transfer_spot(
            self.row(giver), recipient, actor=member(giver.user), **kwargs
        )

    def assert_refused(
        self, code: str, giver: EventSignup, recipient: CustomUser, **kwargs: Any
    ) -> SpotTransferRefused:
        event = giver.event
        state = self.line_state(event)
        entries = self.ledger_count(event)
        with self.assertRaises(SpotTransferRefused) as ctx:
            self.give(giver, recipient, **kwargs)
        self.assertEqual(ctx.exception.code, code)
        self.assertEqual(self.line_state(event), state)
        self.assertEqual(self.ledger_count(event), entries)
        return ctx.exception


class MemberTransferGuardTests(_TransferFixtures):
    def test_disabled_refused(self) -> None:
        event = self.transfer_event(allow_spot_transfer=False)
        giver = self.join(event)
        self.assert_refused("transfer_disabled", giver, self.make_user())

    def test_wrong_state_refused(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        recipient = self.make_user()
        for state in EventState.values:
            if state in TRANSFER_EVENT_STATES:
                continue
            with self.subTest(state=state):
                Event.objects.filter(pk=event.pk).update(state=state)
                self.assert_refused("event_state", giver, recipient)

    def test_giver_not_active_refused(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        cancel_signup(self.row(giver), actor=member(giver.user))
        self.assert_refused("giver_not_active", giver, self.make_user())

    def test_same_user_refused(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        self.assert_refused("same_user", giver, giver.user)

    def test_gate_distance_refused(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        with patch("events.services.same_gate_distance", return_value=False):
            self.assert_refused("gate_distance", giver, self.make_user())

    def test_recipient_removed_refused_for_member(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        for status in (SignupStatus.REJECTED, SignupStatus.DROPPED):
            with self.subTest(status=status):
                recipient = self.make_user()
                self.set_status(self.join(event, recipient), status)
                self.assert_refused("recipient_removed", giver, recipient)

    def test_second_call_refused_giver_not_active(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        recipient = self.make_user()
        entries = self.ledger_count(event)
        self.give(giver, recipient)

        with self.assertRaises(SpotTransferRefused) as ctx:
            transfer_spot(giver, self.make_user(), actor=member(giver.user))

        self.assertEqual(ctx.exception.code, "giver_not_active")
        self.assertEqual(self.ledger_count(event), entries + 2)


class MemberTransferTests(_TransferFixtures):
    def test_transfer_to_user_without_row(self) -> None:
        event = self.transfer_event()
        first = self.join(event)
        giver = self.join(event)
        third = self.join(event)
        recipient = self.make_user()
        giver = self.row(giver)
        others_before = {
            pk: state for pk, state in self.line_state(event).items() if pk != giver.pk
        }

        result = self.give(giver, recipient)

        self.assertEqual(result.mode, "transfer")
        placed = EventSignup.objects.nocache().get(event=event, user=recipient)
        self.assertEqual(placed.pk, result.recipient.pk)
        self.assertEqual(placed.line_seq, giver.line_seq)
        self.assertEqual(placed.signed_up_at, giver.signed_up_at)
        self.assertEqual(placed.status, giver.status)
        self.assertEqual(placed.waitlist_position, giver.waitlist_position)
        self.assertEqual(placed.commitment, Commitment.MAIN)
        gone = self.row(giver)
        self.assertEqual(gone.status, SignupStatus.CANCELLED)
        self.assertIsNone(gone.waitlist_position)
        other_seqs = [
            s.line_seq
            for s in EventSignup.objects.nocache()
            .filter(event=event)
            .exclude(pk=gone.pk)
        ]
        self.assertGreater(gone.line_seq, max(other_seqs))
        after = self.line_state(event)
        for pk, state in others_before.items():
            self.assertEqual(after[pk], state)
        self.assertIn(first.pk, after)
        self.assertIn(third.pk, after)
        self.assertFalse(
            SignupLedgerEntry.objects.filter(
                event=event, action=SignupAction.PROMOTED
            ).exists()
        )

    def test_transfer_full_event_no_promotion(self) -> None:
        event = self.transfer_event(max_players=2)
        giver = self.join(event)
        self.join(event)
        waiting = [self.join(event), self.join(event)]
        self.assertTrue(
            all(self.row(w).status == SignupStatus.WAITLISTED for w in waiting)
        )
        waiting_before = {w.pk: self.line_state(event)[w.pk] for w in waiting}
        seats = count_seats(event)

        self.give(giver, self.make_user())

        self.assertEqual(count_seats(event), seats)
        after = self.line_state(event)
        for pk, state in waiting_before.items():
            self.assertEqual(after[pk], state)
        self.assertFalse(
            SignupLedgerEntry.objects.filter(
                event=event, action=SignupAction.PROMOTED
            ).exists()
        )

    def test_new_row_first_signed_up_at_is_now(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        t0 = timezone.now()

        result = self.give(giver, self.make_user())

        placed = self.row(result.recipient)
        assert placed.first_signed_up_at is not None
        self.assertGreaterEqual(placed.first_signed_up_at, t0)
        self.assertNotEqual(placed.first_signed_up_at, self.row(giver).signed_up_at)
        self.assertNotEqual(placed.first_signed_up_at, placed.signed_up_at)

    def test_transfer_reuses_cancelled_row(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        recipient = self.make_user()
        old = self.join(event, recipient)
        cancel_signup(self.row(old), actor=member(recipient))
        old = self.row(old)
        firsts = (old.first_signed_up_at, old.first_commitment, old.first_rsvp_class)
        self.assertIsNotNone(old.first_signed_up_at)

        result = self.give(giver, recipient)

        placed = self.row(old)
        self.assertEqual(result.recipient.pk, old.pk)
        self.assertEqual(placed.line_seq, giver.line_seq)
        self.assertEqual(placed.status, SignupStatus.CONFIRMED)
        self.assertEqual(
            (
                placed.first_signed_up_at,
                placed.first_commitment,
                placed.first_rsvp_class,
            ),
            firsts,
        )
        self.assertIsNone(latest_restorable_withdrawal(placed))

    def test_giver_withdrawal_not_voidable(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        cancel_signup(self.row(giver), actor=member(giver.user))
        giver = self.set_status(giver, SignupStatus.CONFIRMED)
        probe = self.row(giver)
        probe.status = SignupStatus.CANCELLED
        self.assertIsNotNone(latest_restorable_withdrawal(probe))

        self.give(giver, self.make_user())

        gone = self.row(giver)
        self.assertEqual(gone.status, SignupStatus.CANCELLED)
        self.assertIsNone(latest_restorable_withdrawal(gone))
        with patch(
            "events.ledger._PLACE_HANDOFF_ACTIONS",
            frozenset({SignupAction.MOVED_EVENT}),
        ):
            self.assertIsNotNone(latest_restorable_withdrawal(gone))

    def test_transfer_moves_tournament_membership(self) -> None:
        event = self.transfer_event(roll_call_enabled=False)
        create_tournament_for_event(event)
        event.refresh_from_db()
        giver = self.join(event)
        recipient = self.make_user()
        tournament = Tournament.objects.nocache().get(pk=event.tournament_id)
        self.assertTrue(tournament.users.filter(pk=giver.user_id).exists())

        self.give(giver, recipient)

        users = set(tournament.users.values_list("pk", flat=True))
        self.assertIn(recipient.pk, users)
        self.assertNotIn(giver.user_id, users)

    def _back_of_line_after_return(self, rejoin: Any) -> None:
        event = self.transfer_event(line_withdraw_forfeits=False)
        giver = self.join(event)
        self.join(event)
        self.join(event)
        result = self.give(giver, self.make_user())
        placed_seq = self.row(result.recipient).line_seq

        back = rejoin(self.row(giver))

        back = self.row(back)
        self.assertNotEqual(back.status, SignupStatus.CANCELLED)
        others = EventSignup.objects.nocache().filter(event=event).exclude(pk=back.pk)
        self.assertGreater(back.line_seq, max(s.line_seq for s in others))
        self.assertEqual(self.row(result.recipient).line_seq, placed_seq)

    def test_giver_reinstate_goes_to_back(self) -> None:
        self._back_of_line_after_return(
            lambda row: reinstate_signup(row, actor=self.staff_actor)
        )

    def test_giver_resignup_keep_place_goes_to_back(self) -> None:
        self._back_of_line_after_return(
            lambda row: process_rsvp(row.event, row.user, actor=member(row.user))
        )

    def test_maybe_gives_place(self) -> None:
        event = self.transfer_event()
        maybe_user = self.make_user()
        giver = create_tentative_signup(event, maybe_user, actor=member(maybe_user))
        self.assertEqual(self.row(giver).status, SignupStatus.TENTATIVE)

        result = self.give(giver, self.make_user())

        placed = self.row(result.recipient)
        self.assertEqual(placed.status, SignupStatus.TENTATIVE)
        self.assertEqual(placed.commitment, Commitment.MAYBE)
        self.assertEqual(placed.line_seq, giver.line_seq)

    def test_member_cap_manual_approval(self) -> None:
        event = self.transfer_event(auto_approve=False)
        giver = self.set_status(self.join(event), SignupStatus.APPROVED)
        seats = count_seats(event)

        result = self.give(giver, self.make_user())

        placed = self.row(result.recipient)
        self.assertEqual(placed.status, SignupStatus.RSVP)
        self.assertEqual(placed.line_seq, giver.line_seq)
        self.assertEqual(count_seats(event), seats)

    def test_member_cap_auto_confirm_off(self) -> None:
        event = self.transfer_event(auto_confirm=False)
        giver = self.set_status(self.join(event), SignupStatus.CONFIRMED)

        result = self.give(giver, self.make_user())

        self.assertEqual(self.row(result.recipient).status, SignupStatus.APPROVED)


class MemberTransferEligibilityTests(_TransferFixtures):
    def _requiring_event(self) -> tuple[Event, EventSignup]:
        event = self.transfer_event()
        giver = self.join(event)
        Event.objects.filter(pk=event.pk).update(
            require_steam_id=True, require_mmr_verified=True
        )
        return event, self.row(giver)

    def test_ineligible_recipient_refused(self) -> None:
        _event, giver = self._requiring_event()

        exc = self.assert_refused("recipient_ineligible", giver, self.make_user())

        codes = {r["code"] for r in exc.reasons}
        self.assertIn(ReasonCode.STEAM_ID_MISSING, codes)
        self.assertIn(ReasonCode.MMR_UNVERIFIED, codes)
        for entry in exc.reasons:
            self.assertEqual(set(entry), {"code", "rule", "message"})

    def test_non_member_refused(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        outsider = CustomUser.objects.create_user(
            username="transfer_outsider", password="x"
        )
        self.assert_refused("not_org_member", giver, outsider)

    def test_conduct_block_collapsed(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        blocked = EligibilityResult(
            reasons=(
                Reason(
                    code=ReasonCode.CONDUCT_BELOW_THRESHOLD,
                    severity=Severity.BLOCK,
                    rule=Rule.CONDUCT_BLOCK,
                    message="Below threshold",
                    params={"tier": "block"},
                ),
            )
        )
        with patch("events.services.evaluate_signup", return_value=blocked):
            exc = self.assert_refused("recipient_ineligible", giver, self.make_user())
        self.assertEqual(list(exc.reasons), [GENERIC])

    def test_member_acknowledged_ignored(self) -> None:
        _event, giver = self._requiring_event()
        self.assert_refused(
            "recipient_ineligible",
            giver,
            self.make_user(),
            acknowledged=[ReasonCode.STEAM_ID_MISSING, ReasonCode.MMR_UNVERIFIED],
            reason="please",
        )

    def test_refusal_logged(self) -> None:
        _event, giver = self._requiring_event()
        recipient = self.make_user()
        with capture_logs() as logs:
            with self.assertRaises(SpotTransferRefused):
                self.give(giver, recipient)
        refused = [e for e in logs if e["event"] == "signup_spot_transfer_refused"]
        self.assertEqual(len(refused), 1)
        self.assertEqual(refused[0]["log_level"], "warning")
        self.assertEqual(refused[0]["code"], "recipient_ineligible")
        self.assertEqual(refused[0]["recipient_user_id"], recipient.pk)
        self.assertEqual(refused[0]["caller_user_id"], giver.user_id)
        self.assertNotIn("params", refused[0])

    def test_other_refusals_logged_at_info(self) -> None:
        event = self.transfer_event(allow_spot_transfer=False)
        giver = self.join(event)
        with capture_logs() as logs:
            with self.assertRaises(SpotTransferRefused):
                self.give(giver, self.make_user())
        refused = [e for e in logs if e["event"] == "signup_spot_transfer_refused"]
        self.assertEqual([e["log_level"] for e in refused], ["info"])


class MemberTransferRecordTests(_TransferFixtures):
    def test_ledger_pair(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        recipient = self.make_user()
        start = SignupLedgerEntry.objects.filter(event=event).count()

        result = self.give(giver, recipient)

        entries = list(
            SignupLedgerEntry.objects.filter(event=event).order_by("pk")[start:]
        )
        self.assertEqual(
            [e.action for e in entries],
            [SignupAction.TRANSFERRED_OUT, SignupAction.TRANSFERRED_IN],
        )
        out, into = entries
        self.assertEqual(out.subject_user_id, giver.user_id)
        self.assertEqual(into.subject_user_id, recipient.pk)
        self.assertEqual(out.correlation_id, into.correlation_id)
        self.assertTrue(out.correlation_id.startswith("xfer:"))
        self.assertEqual(result.correlation_id, out.correlation_id)
        self.assertEqual(out.after["extra"]["counterparty_user_id"], recipient.pk)
        self.assertEqual(into.after["extra"]["counterparty_user_id"], giver.user_id)
        self.assertEqual(out.after["status"], SignupStatus.CANCELLED)
        self.assertIsNone(into.before)
        self.assertEqual(into.signup_id, result.recipient.pk)

    def test_mark_interested_queued(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        recipient = self.make_user()
        self.notify_changed.reset_mock()
        self.notify_interested.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            result = self.give(giver, recipient)

        self.assertEqual(self.row(result.recipient).status, SignupStatus.CONFIRMED)
        self.notify_interested.assert_called_once()
        self.assertEqual(self.notify_interested.call_args.args[1], recipient.pk)
        self.notify_changed.assert_called_once()

    def test_success_logged(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        with capture_logs() as logs:
            with self.captureOnCommitCallbacks(execute=True):
                result = self.give(giver, self.make_user())
        done = [e for e in logs if e["event"] == "signup_spot_transferred"]
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["mode"], "transfer")
        self.assertEqual(done[0]["giver_signup_id"], giver.pk)
        self.assertEqual(done[0]["recipient_signup_id"], result.recipient.pk)
        self.assertEqual(done[0]["correlation_id"], result.correlation_id)
        self.assertEqual(done[0]["actor_role"], ActorRole.MEMBER)
