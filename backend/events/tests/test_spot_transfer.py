from datetime import datetime, timedelta
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
    StaffReasonPolicy,
)
from events.eligibility import EligibilityResult, Reason, ReasonCode, Rule, Severity
from events.eligibility.checks.requirements import MESSAGES
from events.exceptions import SpotTransferRefused
from events.ledger import SignupActor, latest_restorable_withdrawal
from events.models import (
    Event,
    EventSignup,
    ReadyCheck,
    ReadyCheckEntry,
    RollCallMode,
    SignupLedgerEntry,
)
from events.overrides import (
    OverrideReasonRequired,
    OverrideRequired,
    StaffReasonRequired,
)
from events.ready_check import ConfirmResult, _active_and_droppable, confirm_ready
from events.ready_check_constants import (
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckPhase,
    ReadyCheckScope,
)
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
from org.conduct.constants import Outcome
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome
from tournament.models import Tournament

LineState = tuple[str, int | None, datetime | None, int | None]

GENERIC = {
    "code": "recipient_ineligible",
    "severity": "block",
    "rule": "eligibility",
    "message": "Not eligible for this event",
    "fix": None,
    "params": {},
}
E2_KEYS = {"code", "severity", "rule", "message", "fix", "params"}
STEAM_REASON = Reason(
    code=ReasonCode.STEAM_ID_MISSING,
    severity=Severity.NEEDS_APPROVAL,
    rule=Rule.REQUIRE_STEAM_ID,
    message=MESSAGES[ReasonCode.STEAM_ID_MISSING],
)
CONDUCT_HOLD = Reason(
    code=ReasonCode.CONDUCT_BELOW_THRESHOLD,
    severity=Severity.NEEDS_APPROVAL,
    rule=Rule.CONDUCT_REQUIRE_APPROVAL,
    message="Below threshold",
    params={"tier": "require_approval"},
)


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

    def test_member_refused_when_user_signups_off(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        Event.objects.filter(pk=event.pk).update(allow_user_signups=False)
        exc = self.assert_refused("user_signups_disabled", giver, self.make_user())
        self.assertEqual(list(exc.reasons), [])

    def test_staff_transfer_allowed_when_user_signups_off(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        Event.objects.filter(pk=event.pk).update(allow_user_signups=False)
        result = transfer_spot(
            self.row(giver), self.make_user(), actor=self.staff_actor, reason="cover"
        )
        self.assertEqual(result.mode, "transfer")

    def test_deleted_giver_refused(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        stale = self.row(giver)
        EventSignup.objects.filter(pk=giver.pk).delete()
        entries = self.ledger_count(event)
        with self.assertRaises(SpotTransferRefused) as ctx:
            transfer_spot(stale, self.make_user(), actor=member(giver.user))
        self.assertEqual(ctx.exception.code, "giver_not_active")
        self.assertEqual(self.ledger_count(event), entries)

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
            self.assertEqual(set(entry), E2_KEYS)
        steam = next(r for r in exc.reasons if r["code"] == ReasonCode.STEAM_ID_MISSING)
        self.assertEqual(steam["severity"], Severity.NEEDS_APPROVAL)
        self.assertEqual(steam["message"], MESSAGES[ReasonCode.STEAM_ID_MISSING])
        self.assertEqual(steam["fix"]["kind"], "update_profile")

    def test_non_member_refused(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        outsider = CustomUser.objects.create_user(
            username="transfer_outsider", password="x"
        )
        with capture_logs() as logs:
            exc = self.assert_refused("recipient_ineligible", giver, outsider)
        self.assertEqual(list(exc.reasons), [GENERIC])
        refused = [e for e in logs if e["event"] == "signup_spot_transfer_refused"]
        self.assertEqual([e["code"] for e in refused], ["not_org_member"])
        self.assertEqual(refused[0]["log_level"], "warning")

    def test_non_member_indistinguishable_from_ineligible_member(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        outsider = CustomUser.objects.create_user(
            username="transfer_outsider_2", password="x"
        )
        pairs = (
            ((), (CONDUCT_HOLD,)),
            ((STEAM_REASON,), (CONDUCT_HOLD, STEAM_REASON)),
        )
        for outsider_reasons, member_reasons in pairs:
            with self.subTest(reasons=[str(r.code) for r in member_reasons]):
                with patch(
                    "events.services.evaluate_signup",
                    return_value=EligibilityResult(reasons=outsider_reasons),
                ):
                    hidden = self.assert_refused(
                        "recipient_ineligible", giver, outsider
                    )
                with patch(
                    "events.services.evaluate_signup",
                    return_value=EligibilityResult(reasons=member_reasons),
                ):
                    held = self.assert_refused(
                        "recipient_ineligible", giver, self.make_user()
                    )
                self.assertEqual(
                    (hidden.code, hidden.message, list(hidden.reasons)),
                    (held.code, held.message, list(held.reasons)),
                )

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


class TransferStandingTests(_TransferFixtures):
    def test_giver_records_no_late_cancel(self) -> None:
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=True, actor=None)
        event = self.transfer_event(scheduled_at=timezone.now() + timedelta(hours=1))
        giver = self.join(event)
        control = self.join(event)
        cancel_signup(self.row(control), actor=member(control.user))
        late = AttendanceOutcome.objects.nocache().filter(event=event)
        self.assertEqual(
            list(late.values_list("org_user__user_id", "outcome")),
            [(control.user_id, Outcome.LATE_CANCEL)],
        )

        self.give(giver, self.make_user())

        self.assertFalse(late.filter(org_user__user=giver.user).exists())


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


class MemberSwapTests(_TransferFixtures):
    FIRST_FIELDS = ("first_signed_up_at", "first_commitment", "first_rsvp_class")

    def seated_and_waitlisted(
        self, **overrides: Any
    ) -> tuple[Event, EventSignup, EventSignup]:
        event = self.transfer_event(max_players=1, auto_confirm=False, **overrides)
        seated = self.join(event)
        waiting = self.join(event)
        self.assertEqual(self.row(seated).status, SignupStatus.APPROVED)
        self.assertEqual(self.row(waiting).status, SignupStatus.WAITLISTED)
        return event, self.row(seated), self.row(waiting)

    def test_swap_seated_with_waitlisted(self) -> None:
        event, giver, recipient = self.seated_and_waitlisted()
        bystander = self.row(self.join(event))
        bystander_state = self.line_state(event)[bystander.pk]
        firsts = {
            row.pk: tuple(getattr(row, f) for f in self.FIRST_FIELDS)
            for row in (giver, recipient)
        }

        result = self.give(giver, recipient.user)

        self.assertEqual(result.mode, "swap")
        self.assertEqual(result.recipient.pk, recipient.pk)
        after_giver, after_recipient = self.row(giver), self.row(recipient)
        self.assertEqual(
            (
                after_giver.line_seq,
                after_giver.signed_up_at,
                after_giver.status,
                after_giver.waitlist_position,
            ),
            (
                recipient.line_seq,
                recipient.signed_up_at,
                recipient.status,
                recipient.waitlist_position,
            ),
        )
        self.assertEqual(
            (
                after_recipient.line_seq,
                after_recipient.signed_up_at,
                after_recipient.status,
                after_recipient.waitlist_position,
            ),
            (
                giver.line_seq,
                giver.signed_up_at,
                giver.status,
                giver.waitlist_position,
            ),
        )
        for before, after in ((giver, after_giver), (recipient, after_recipient)):
            self.assertEqual(after.commitment, before.commitment)
            self.assertEqual(
                tuple(getattr(after, f) for f in self.FIRST_FIELDS), firsts[before.pk]
            )
        self.assertEqual(self.line_state(event)[bystander.pk], bystander_state)
        self.assertFalse(
            SignupLedgerEntry.objects.filter(
                event=event, action=SignupAction.PROMOTED
            ).exists()
        )

    def test_swap_ledger(self) -> None:
        event, giver, recipient = self.seated_and_waitlisted()
        start = self.ledger_count(event)

        result = self.give(giver, recipient.user, reason=" covering ")

        entries = list(
            SignupLedgerEntry.objects.filter(event=event).order_by("pk")[start:]
        )
        self.assertEqual(
            [e.action for e in entries], [SignupAction.SWAPPED, SignupAction.SWAPPED]
        )
        out, into = entries
        self.assertEqual(out.subject_user_id, giver.user_id)
        self.assertEqual(into.subject_user_id, recipient.user_id)
        self.assertEqual(out.correlation_id, into.correlation_id)
        self.assertTrue(out.correlation_id.startswith("xfer:"))
        self.assertEqual(result.correlation_id, out.correlation_id)
        self.assertEqual(out.after["extra"]["counterparty_user_id"], recipient.user_id)
        self.assertEqual(into.after["extra"]["counterparty_user_id"], giver.user_id)
        self.assertEqual(out.before["status"], SignupStatus.APPROVED)
        self.assertEqual(out.after["status"], SignupStatus.WAITLISTED)
        self.assertEqual(into.before["status"], SignupStatus.WAITLISTED)
        self.assertEqual(into.after["status"], SignupStatus.APPROVED)
        self.assertEqual({out.reason, into.reason}, {"covering"})

    def test_swap_notifies_once_and_marks_new_seat(self) -> None:
        _event, giver, recipient = self.seated_and_waitlisted()
        self.notify_changed.reset_mock()
        self.notify_interested.reset_mock()

        with capture_logs() as logs:
            with self.captureOnCommitCallbacks(execute=True):
                result = self.give(giver, recipient.user)

        self.notify_changed.assert_called_once()
        self.notify_interested.assert_called_once()
        self.assertEqual(self.notify_interested.call_args.args[1], recipient.user_id)
        done = [e for e in logs if e["event"] == "signup_spot_transferred"]
        self.assertEqual([e["mode"] for e in done], ["swap"])
        self.assertEqual(done[0]["recipient_signup_id"], result.recipient.pk)

    def test_maybe_main_swap_refused(self) -> None:
        event = self.transfer_event()
        main = self.join(event)
        maybe_user = self.make_user()
        maybe = create_tentative_signup(event, maybe_user, actor=member(maybe_user))
        self.assertEqual(self.row(maybe).status, SignupStatus.TENTATIVE)
        self.assert_refused("commitment_mismatch", main, maybe_user)
        self.assert_refused("commitment_mismatch", maybe, main.user)

    def test_maybe_maybe_swap_ok(self) -> None:
        event = self.transfer_event()
        users = [self.make_user(), self.make_user()]
        giver, other = (
            self.row(create_tentative_signup(event, u, actor=member(u))) for u in users
        )
        self.assertLess(giver.line_seq, other.line_seq)

        result = self.give(giver, other.user)

        self.assertEqual(result.mode, "swap")
        after_giver, after_other = self.row(giver), self.row(other)
        self.assertEqual(after_giver.line_seq, other.line_seq)
        self.assertEqual(after_other.line_seq, giver.line_seq)
        for row in (after_giver, after_other):
            self.assertEqual(row.status, SignupStatus.TENTATIVE)
            self.assertEqual(row.commitment, Commitment.MAYBE)

    def test_member_cannot_pull_better_place_down(self) -> None:
        with self.subTest("waitlisted giver vs approved recipient"):
            _event, seated, waiting = self.seated_and_waitlisted()
            self.assert_refused("swap_would_demote_recipient", waiting, seated.user)
        with self.subTest("approved giver later in line"):
            event = self.transfer_event(auto_confirm=False)
            earlier = self.join(event)
            later = self.join(event)
            self.assertEqual(self.row(later).status, SignupStatus.APPROVED)
            self.assert_refused("swap_would_demote_recipient", later, earlier.user)
        with self.subTest("rsvp giver vs approved recipient"):
            event = self.transfer_event(auto_confirm=False)
            approved = self.join(event)
            rsvp = self.set_status(self.join(event), SignupStatus.RSVP)
            approved = self.set_status(approved, SignupStatus.APPROVED)
            self.assert_refused("swap_would_demote_recipient", rsvp, approved.user)

    def test_member_swap_keeps_recipient_approval(self) -> None:
        event = self.transfer_event(auto_approve=False)
        giver = self.set_status(self.join(event), SignupStatus.APPROVED)
        recipient = self.set_status(self.join(event), SignupStatus.APPROVED)

        self.give(giver, recipient.user)

        self.assertEqual(self.row(giver).status, SignupStatus.APPROVED)
        self.assertEqual(self.row(recipient).status, SignupStatus.APPROVED)
        self.assertEqual(self.row(recipient).line_seq, giver.line_seq)

    def test_member_swap_cannot_raise_giver_status(self) -> None:
        cases = (
            (SignupStatus.APPROVED, SignupStatus.CONFIRMED),
            (SignupStatus.RSVP, SignupStatus.PENDING_APPROVAL),
        )
        for giver_status, recipient_status in cases:
            with self.subTest(giver=giver_status, recipient=recipient_status):
                event = self.transfer_event(auto_approve=False)
                giver = self.set_status(self.join(event), giver_status)
                recipient = self.set_status(self.join(event), recipient_status)
                self.assert_refused(
                    "swap_would_demote_recipient", giver, recipient.user
                )

    def test_swap_moves_tournament_membership(self) -> None:
        event = self.transfer_event(
            max_players=1, auto_confirm=False, roll_call_enabled=False
        )
        create_tournament_for_event(event)
        event.refresh_from_db()
        giver = self.row(self.join(event))
        recipient = self.row(self.join(event))
        self.assertEqual(recipient.status, SignupStatus.WAITLISTED)
        tournament = Tournament.objects.nocache().get(pk=event.tournament_id)
        self.assertTrue(tournament.users.filter(pk=giver.user_id).exists())
        self.assertFalse(tournament.users.filter(pk=recipient.user_id).exists())

        self.give(self.row(giver), recipient.user)

        users = set(tournament.users.values_list("pk", flat=True))
        self.assertIn(recipient.user_id, users)
        self.assertNotIn(giver.user_id, users)


STEAM_MISSING = EligibilityResult(
    reasons=(
        Reason(
            code=ReasonCode.STEAM_ID_MISSING,
            severity=Severity.BLOCK,
            rule=Rule.REQUIRE_STEAM_ID,
            message="This event requires a Steam friend ID on your profile.",
        ),
    )
)


class StaffTransferTests(_TransferFixtures):
    def staff_give(
        self, giver: EventSignup, recipient: CustomUser, **kwargs: Any
    ) -> SpotTransferResult:
        return transfer_spot(
            self.row(giver), recipient, actor=self.staff_actor, **kwargs
        )

    def assert_staff_raises(
        self,
        exc_type: type[Exception],
        giver: EventSignup,
        recipient: CustomUser,
        **kwargs: Any,
    ) -> Exception:
        event = giver.event
        state = self.line_state(event)
        entries = self.ledger_count(event)
        with self.assertRaises(exc_type) as ctx:
            self.staff_give(giver, recipient, **kwargs)
        self.assertEqual(self.line_state(event), state)
        self.assertEqual(self.ledger_count(event), entries)
        return ctx.exception

    def new_entries(self, event: Event, start: int) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(event=event).order_by("pk")[start:]
        )

    def requiring_event(self, **overrides: Any) -> tuple[Event, EventSignup]:
        event = self.transfer_event(**overrides)
        giver = self.join(event)
        Event.objects.filter(pk=event.pk).update(
            require_steam_id=True, require_mmr_verified=True
        )
        return event, self.row(giver)

    def giver_only_ineligible(self, giver: EventSignup) -> Any:
        def evaluate(_event: Event, user: CustomUser, **_kw: Any) -> EligibilityResult:
            return STEAM_MISSING if user.pk == giver.user_id else EligibilityResult()

        return patch("events.services.evaluate_signup", side_effect=evaluate)

    def test_staff_ineligible_requires_override(self) -> None:
        _event, giver = self.requiring_event()

        exc = self.assert_staff_raises(OverrideRequired, giver, self.make_user())

        assert isinstance(exc, OverrideRequired)
        codes = {v.code for v in exc.violations}
        self.assertIn(ReasonCode.STEAM_ID_MISSING, codes)
        self.assertIn(ReasonCode.MMR_UNVERIFIED, codes)
        self.assertEqual({v.category for v in exc.violations}, {"eligibility"})

    def test_staff_override_succeeds(self) -> None:
        event, giver = self.requiring_event()
        recipient = self.make_user()
        codes = [ReasonCode.STEAM_ID_MISSING, ReasonCode.MMR_UNVERIFIED]
        start = self.ledger_count(event)

        result = self.staff_give(
            giver, recipient, acknowledged=codes, reason=" vouched for "
        )

        self.assertEqual(result.mode, "transfer")
        self.assertEqual(self.row(result.recipient).status, giver.status)
        out, into = self.new_entries(event, start)
        self.assertEqual(into.subject_user_id, recipient.pk)
        self.assertEqual(set(into.rules_overridden), set(codes))
        self.assertEqual(out.rules_overridden, [])
        self.assertEqual({out.reason, into.reason}, {"vouched for"})

    def test_staff_override_without_reason_refused(self) -> None:
        _event, giver = self.requiring_event()
        self.assert_staff_raises(
            OverrideReasonRequired,
            giver,
            self.make_user(),
            acknowledged=[ReasonCode.STEAM_ID_MISSING, ReasonCode.MMR_UNVERIFIED],
        )

    def test_staff_partial_acknowledgement_reprompts(self) -> None:
        _event, giver = self.requiring_event()
        codes = [ReasonCode.STEAM_ID_MISSING, ReasonCode.MMR_UNVERIFIED]
        exc = self.assert_staff_raises(
            OverrideRequired, giver, self.make_user(), acknowledged=codes[:1]
        )
        assert isinstance(exc, OverrideRequired)
        self.assertEqual([v.code for v in exc.violations], [ReasonCode.MMR_UNVERIFIED])

    def test_staff_non_member_override_creates_org_user(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        outsider = CustomUser.objects.create_user(
            username="staff_transfer_outsider", password="x"
        )

        exc = self.assert_staff_raises(OverrideRequired, giver, outsider)
        assert isinstance(exc, OverrideRequired)
        [violation] = exc.violations
        self.assertEqual(violation.code, "not_org_member")
        self.assertEqual(violation.rule, "membership")
        self.assertEqual(violation.category, "eligibility")
        self.assertFalse(
            OrgUser.objects.filter(user=outsider, organization=self.org).exists()
        )

        self.staff_give(
            giver, outsider, acknowledged=["not_org_member"], reason="new member"
        )

        self.assertTrue(
            OrgUser.objects.filter(user=outsider, organization=self.org).exists()
        )

    def test_staff_override_logged(self) -> None:
        _event, giver = self.requiring_event()
        with capture_logs() as logs:
            with self.assertRaises(OverrideRequired):
                self.staff_give(giver, self.make_user())
        prompts = [e for e in logs if e["event"] == "spot_transfer_override_required"]
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0]["subsystem"], "line")
        self.assertIn(ReasonCode.STEAM_ID_MISSING, prompts[0]["codes"])
        self.assertNotIn("params", prompts[0])

    def test_placements_policy_requires_reason(self) -> None:
        event = self.transfer_event(staff_reason_policy=StaffReasonPolicy.PLACEMENTS)
        giver = self.join(event)
        recipient = self.make_user()

        self.assert_staff_raises(StaffReasonRequired, giver, recipient)
        result = self.staff_give(giver, recipient, reason="swap requested")

        self.assertEqual(self.row(result.recipient).user_id, recipient.pk)

    def test_reason_before_override(self) -> None:
        _event, giver = self.requiring_event(
            staff_reason_policy=StaffReasonPolicy.PLACEMENTS
        )
        self.assert_staff_raises(StaffReasonRequired, giver, self.make_user())

    def test_staff_as_recipient_still_needs_reason(self) -> None:
        OrgUser.objects.get_or_create(user=self.admin, organization=self.org)
        with self.subTest("staff receives"):
            event = self.transfer_event(
                staff_reason_policy=StaffReasonPolicy.PLACEMENTS
            )
            giver = self.join(event)
            self.assert_staff_raises(StaffReasonRequired, giver, self.admin)
        with self.subTest("staff gives"):
            event = self.transfer_event(
                staff_reason_policy=StaffReasonPolicy.PLACEMENTS
            )
            giver = self.join(event, self.admin)
            self.assert_staff_raises(StaffReasonRequired, giver, self.make_user())

    def test_staff_may_place_rejected_and_dropped(self) -> None:
        event = self.transfer_event()
        for status in (SignupStatus.REJECTED, SignupStatus.DROPPED):
            with self.subTest(status=status):
                giver = self.row(self.join(event))
                recipient = self.make_user()
                held = self.set_status(self.join(event, recipient), status)

                result = self.staff_give(giver, recipient)

                self.assertEqual(result.mode, "transfer")
                self.assertEqual(result.recipient.pk, held.pk)
                placed = self.row(held)
                self.assertEqual(placed.status, giver.status)
                self.assertEqual(placed.line_seq, giver.line_seq)
                self.assertEqual(self.row(giver).status, SignupStatus.CANCELLED)

    def assert_staff_swapped(self, giver: EventSignup, recipient: EventSignup) -> None:
        self.staff_give(giver, recipient.user)
        after_giver, after_recipient = self.row(giver), self.row(recipient)
        self.assertEqual(
            (after_giver.status, after_giver.line_seq),
            (recipient.status, recipient.line_seq),
        )
        self.assertEqual(
            (after_recipient.status, after_recipient.line_seq),
            (giver.status, giver.line_seq),
        )

    def test_staff_may_demote_by_swap(self) -> None:
        with self.subTest("waitlisted giver vs approved recipient"):
            event = self.transfer_event(max_players=1, auto_confirm=False)
            seated = self.row(self.join(event))
            waiting = self.row(self.join(event))
            self.assertEqual(waiting.status, SignupStatus.WAITLISTED)
            self.assert_staff_swapped(waiting, seated)
        with self.subTest("approved giver later in line"):
            event = self.transfer_event(auto_confirm=False)
            earlier = self.row(self.join(event))
            later = self.row(self.join(event))
            self.assert_staff_swapped(later, earlier)
        with self.subTest("rsvp giver vs approved recipient"):
            event = self.transfer_event(auto_confirm=False)
            approved = self.join(event)
            rsvp = self.set_status(self.join(event), SignupStatus.RSVP)
            approved = self.set_status(approved, SignupStatus.APPROVED)
            self.assert_staff_swapped(rsvp, approved)

    def test_staff_swap_checks_giver_eligibility(self) -> None:
        event = self.transfer_event(auto_approve=False)
        giver = self.set_status(self.join(event), SignupStatus.PENDING_APPROVAL)
        recipient = self.set_status(self.join(event), SignupStatus.APPROVED)

        with self.giver_only_ineligible(giver):
            exc = self.assert_staff_raises(OverrideRequired, giver, recipient.user)
            assert isinstance(exc, OverrideRequired)
            [violation] = exc.violations
            self.assertEqual(violation.code, ReasonCode.STEAM_ID_MISSING)
            self.assertTrue(violation.message.startswith("Giver: "))

            start = self.ledger_count(event)
            self.staff_give(
                giver,
                recipient.user,
                acknowledged=[ReasonCode.STEAM_ID_MISSING],
                reason="cover",
            )

        out, into = self.new_entries(event, start)
        self.assertEqual(out.subject_user_id, giver.user_id)
        self.assertEqual(out.rules_overridden, [ReasonCode.STEAM_ID_MISSING])
        self.assertEqual(into.rules_overridden, [])
        self.assertEqual(self.row(giver).status, SignupStatus.APPROVED)
        self.assertEqual(self.row(recipient).status, SignupStatus.PENDING_APPROVAL)

    def test_staff_swap_skips_giver_when_not_raised(self) -> None:
        event = self.transfer_event(max_players=1, auto_confirm=False)
        giver = self.row(self.join(event))
        recipient = self.row(self.join(event))
        self.assertEqual(recipient.status, SignupStatus.WAITLISTED)

        with self.giver_only_ineligible(giver):
            result = self.staff_give(giver, recipient.user)

        self.assertEqual(result.mode, "swap")
        self.assertEqual(self.row(giver).status, SignupStatus.WAITLISTED)

    def test_staff_transfer_not_capped(self) -> None:
        event = self.transfer_event(auto_approve=False)
        giver = self.set_status(self.join(event), SignupStatus.APPROVED)

        result = self.staff_give(giver, self.make_user())

        self.assertEqual(self.row(result.recipient).status, SignupStatus.APPROVED)
        self.assertEqual(result.recipient.line_seq, giver.line_seq)


class RollCallTransferTests(_TransferFixtures):
    def roll_call(
        self, phase: str = ReadyCheckPhase.OPEN, **overrides: Any
    ) -> tuple[Event, ReadyCheck]:
        event = self.transfer_event(**overrides)
        return event, self.open_check(event, phase)

    def open_check(self, event: Event, phase: str) -> ReadyCheck:
        Event.objects.filter(pk=event.pk).update(state=EventState.ROLL_CALL)
        return ReadyCheck.objects.create(
            event=event,
            phase=phase,
            settings_snapshot={
                "ready_check_scope": ReadyCheckScope.MAIN_ONLY,
                "effective_mode": RollCallMode.MANUAL,
            },
        )

    def seated(
        self, event: Event, check: ReadyCheck, status: str, entry_state: str
    ) -> EventSignup:
        signup = EventSignup.objects.create(
            event=event, user=self.make_user(), status=status
        )
        entry = ReadyCheckEntry.for_signup(check, signup)
        entry.state = entry_state
        entry.save()
        return signup

    def entry_state(self, check: ReadyCheck, user_id: int) -> str | None:
        entry = check.entries.filter(user_id=user_id).first()
        return None if entry is None else entry.state

    def assert_counts_agree(self, event: Event, check: ReadyCheck) -> None:
        active, _ = _active_and_droppable(check)
        confirmed_entries = sum(
            1 for e in active if e.state == ReadyCheckEntryState.CONFIRMED
        )
        confirmed_signups = EventSignup.objects.nocache().filter(
            event=event, status=SignupStatus.CONFIRMED
        )
        self.assertEqual(confirmed_entries, confirmed_signups.count())

    def test_held_check_refused(self) -> None:
        event, check = self.roll_call(ReadyCheckPhase.HELD)
        giver = self.seated(
            event, check, SignupStatus.APPROVED, ReadyCheckEntryState.PENDING
        )
        recipient = self.make_user()

        self.assert_refused("ready_check_held", giver, recipient)
        with self.assertRaises(SpotTransferRefused) as ctx:
            transfer_spot(self.row(giver), recipient, actor=self.staff_actor)
        self.assertEqual(ctx.exception.code, "ready_check_held")

    def test_transfer_confirmed_giver_to_unanswered_recipient(self) -> None:
        event, check = self.roll_call()
        giver = self.seated(
            event, check, SignupStatus.CONFIRMED, ReadyCheckEntryState.CONFIRMED
        )
        recipient = self.make_user()

        result = self.give(giver, recipient)

        placed = self.row(result.recipient)
        self.assertEqual(placed.status, SignupStatus.APPROVED)
        self.assertEqual(
            self.entry_state(check, recipient.pk), ReadyCheckEntryState.PENDING
        )
        self.assertEqual(check.entries.get(user=recipient).signup_id, placed.pk)
        self.assertEqual(self.row(giver).status, SignupStatus.CANCELLED)
        self.assert_counts_agree(event, check)
        self.assertFalse(
            SignupLedgerEntry.objects.filter(
                event=event, action=SignupAction.PROMOTED
            ).exists()
        )
        self.assertFalse(
            SignupLedgerEntry.objects.filter(
                event=event,
                subject_user=recipient,
                action=SignupAction.CONFIRMED,
            ).exists()
        )

    def test_staff_transfer_confirmed_place_not_confirmed_for_recipient(
        self,
    ) -> None:
        event, check = self.roll_call()
        giver = self.seated(
            event, check, SignupStatus.CONFIRMED, ReadyCheckEntryState.CONFIRMED
        )
        recipient = self.make_user()

        result = transfer_spot(self.row(giver), recipient, actor=self.staff_actor)

        self.assertEqual(self.row(result.recipient).status, SignupStatus.APPROVED)
        entry = check.entries.get(user=recipient)
        self.assertEqual(entry.state, ReadyCheckEntryState.PENDING)
        self.assert_counts_agree(event, check)

    def test_staff_transfer_to_dropped_member_excuses_entry(self) -> None:
        event, check = self.roll_call()
        giver = self.seated(
            event, check, SignupStatus.APPROVED, ReadyCheckEntryState.PENDING
        )
        dropped = self.seated(
            event, check, SignupStatus.DROPPED, ReadyCheckEntryState.DROPPED
        )

        transfer_spot(self.row(giver), dropped.user, actor=self.staff_actor)

        self.assertEqual(self.row(dropped).status, SignupStatus.APPROVED)
        self.assertEqual(
            self.entry_state(check, dropped.user_id), ReadyCheckEntryState.EXCUSED
        )
        self.assert_counts_agree(event, check)
        self.assertEqual(
            confirm_ready(
                event,
                dropped.user,
                via=ReadyCheckConfirmVia.WEB,
                actor=member(dropped.user),
            ),
            ConfirmResult.CLOSED,
        )

    def test_recipient_own_confirmation_kept(self) -> None:
        event, check = self.roll_call()
        giver = self.seated(
            event, check, SignupStatus.APPROVED, ReadyCheckEntryState.PENDING
        )
        recipient_row = self.seated(
            event, check, SignupStatus.CONFIRMED, ReadyCheckEntryState.CONFIRMED
        )
        cancel_signup(self.row(recipient_row), actor=member(recipient_row.user))

        self.give(giver, recipient_row.user)

        self.assertEqual(self.row(recipient_row).status, SignupStatus.CONFIRMED)
        self.assert_counts_agree(event, check)

    def test_swap_only_one_side_confirmed(self) -> None:
        event, check = self.roll_call()
        giver = self.seated(
            event, check, SignupStatus.CONFIRMED, ReadyCheckEntryState.CONFIRMED
        )
        recipient = self.seated(
            event, check, SignupStatus.APPROVED, ReadyCheckEntryState.PENDING
        )
        giver_seq, recipient_seq = giver.line_seq, recipient.line_seq

        result = self.give(giver, recipient.user)

        self.assertEqual(result.mode, "swap")
        giver, recipient = self.row(giver), self.row(recipient)
        self.assertEqual(giver.status, SignupStatus.CONFIRMED)
        self.assertEqual(recipient.status, SignupStatus.APPROVED)
        self.assertEqual(giver.line_seq, recipient_seq)
        self.assertEqual(recipient.line_seq, giver_seq)
        self.assert_counts_agree(event, check)

    def test_staff_swap_statuses_follow_own_entries(self) -> None:
        event, check = self.roll_call()
        giver = self.seated(
            event, check, SignupStatus.APPROVED, ReadyCheckEntryState.PENDING
        )
        recipient = self.seated(
            event, check, SignupStatus.CONFIRMED, ReadyCheckEntryState.CONFIRMED
        )

        result = transfer_spot(self.row(giver), recipient.user, actor=self.staff_actor)

        self.assertEqual(result.mode, "swap")
        self.assertEqual(self.row(giver).status, SignupStatus.APPROVED)
        self.assertEqual(self.row(recipient).status, SignupStatus.CONFIRMED)
        self.assert_counts_agree(event, check)

    def test_cancelled_giver_entry_not_counted(self) -> None:
        event, check = self.roll_call()
        giver = self.seated(
            event, check, SignupStatus.APPROVED, ReadyCheckEntryState.PENDING
        )
        recipient = self.make_user()

        self.give(giver, recipient)

        active, droppable = _active_and_droppable(check)
        active_users = {e.user_id for e in active}
        self.assertNotIn(giver.user_id, active_users)
        self.assertIn(recipient.pk, active_users)
        self.assertNotIn(giver.user_id, {e.user_id for e in droppable})

    def test_rollcall_correlation_prefix(self) -> None:
        event, check = self.roll_call()
        giver = self.seated(
            event, check, SignupStatus.CONFIRMED, ReadyCheckEntryState.CONFIRMED
        )
        recipient = self.make_user()

        result = self.give(giver, recipient)

        self.assertTrue(result.correlation_id.startswith("xfer:"))
        transfer_ids = set(
            SignupLedgerEntry.objects.filter(
                event=event,
                action__in=(
                    SignupAction.TRANSFERRED_OUT,
                    SignupAction.TRANSFERRED_IN,
                ),
            ).values_list("correlation_id", flat=True)
        )
        self.assertEqual(transfer_ids, {result.correlation_id})
        asked = SignupLedgerEntry.objects.get(
            event=event, subject_user=recipient, action=SignupAction.READY_CHECK_ASKED
        )
        self.assertEqual(asked.correlation_id, f"rc{check.pk}:enrol")
        transfer_in = SignupLedgerEntry.objects.get(
            event=event, action=SignupAction.TRANSFERRED_IN
        )
        self.assertLess(transfer_in.pk, asked.pk)
