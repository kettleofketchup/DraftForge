from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

from django.db.models.signals import post_delete
from django.utils import timezone as tz
from structlog.testing import capture_logs

from events.constants import Commitment, SignupAction, SignupStatus
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import (
    _promote_from_waitlist,
    cancel_signup,
    create_tentative_signup,
    decline_signup,
    demote_to_waitlist,
    process_rsvp,
    reject_signup,
    staff_add_signup,
)
from events.tests.base import EventTestCase
from events.tests.test_signup_ledger_contract import LedgerContractMixin
from org.standing.cache import StandingCache


@patch("events.services.notify_signup_changed")
class PromotionLineOrderTests(LedgerContractMixin, EventTestCase):
    def _full_event(
        self, *, seats: int = 1, waiting: int = 2
    ) -> tuple[Event, list[EventSignup], list[EventSignup]]:
        event = self.make_event(max_players=seats)
        seated = [
            EventSignup.objects.create(
                event=event, user=self.make_user(), status=SignupStatus.APPROVED
            )
            for _ in range(seats)
        ]
        waitlisted = [
            EventSignup.objects.create(
                event=event,
                user=self.make_user(),
                status=SignupStatus.WAITLISTED,
                waitlist_position=pos,
            )
            for pos in range(1, waiting + 1)
        ]
        return event, seated, waitlisted

    def _status(self, signup: EventSignup) -> str:
        return EventSignup.objects.nocache().get(pk=signup.pk).status

    def _promoted(self, event: Event) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                event=event, action=SignupAction.PROMOTED
            ).order_by("pk")
        )

    def _waiting_line(self, event: Event) -> list[int]:
        return list(
            EventSignup.objects.nocache()
            .filter(event=event, status=SignupStatus.WAITLISTED)
            .in_line_order()
            .values_list("pk", flat=True)
        )

    def test_promotion_ignores_stored_waitlist_position(self, _notify: Any) -> None:
        event, seated, (w1, w2) = self._full_event()
        EventSignup.objects.filter(pk=w1.pk).update(waitlist_position=99)
        EventSignup.objects.filter(pk=w2.pk).update(waitlist_position=1)

        cancel_signup(seated[0], actor=self.staff_actor)

        self.assertNotEqual(self._status(w1), SignupStatus.WAITLISTED)
        self.assertEqual(self._status(w2), SignupStatus.WAITLISTED)

    def test_promotion_ignores_commitment(self, _notify: Any) -> None:
        event, seated, (w1, w2) = self._full_event()
        EventSignup.objects.filter(pk=w1.pk).update(
            commitment=Commitment.MAYBE, waitlist_position=2
        )
        EventSignup.objects.filter(pk=w2.pk).update(waitlist_position=1)

        cancel_signup(seated[0], actor=self.staff_actor)

        self.assertNotEqual(self._status(w1), SignupStatus.WAITLISTED)
        self.assertEqual(self._status(w2), SignupStatus.WAITLISTED)

    def test_promotion_follows_line_seq_not_insert_order(self, _notify: Any) -> None:
        event, seated, (w1, w2) = self._full_event()
        EventSignup.objects.filter(pk=w1.pk).update(line_seq=50)

        cancel_signup(seated[0], actor=self.staff_actor)

        self.assertEqual(self._status(w1), SignupStatus.WAITLISTED)
        self.assertNotEqual(self._status(w2), SignupStatus.WAITLISTED)

    def test_promoted_before_rank_is_rank_at_that_moment(self, _notify: Any) -> None:
        event, seated, (w1, w2, _w3) = self._full_event(seats=2, waiting=3)

        cancel_signup(seated[0], actor=self.staff_actor)
        cancel_signup(seated[1], actor=self.staff_actor)

        promoted = self._promoted(event)
        self.assertEqual([e.signup_id for e in promoted], [w1.pk, w2.pk])
        self.assertEqual([e.before["waitlist_position"] for e in promoted], [1, 1])
        self.assertEqual([e.after["waitlist_position"] for e in promoted], [None, None])

    def test_batch_promotion_ranks_each_row_at_its_turn(self, _notify: Any) -> None:
        event, _seated, (w1, w2, _w3) = self._full_event(seats=1, waiting=3)
        Event.objects.filter(pk=event.pk).update(max_players=3)

        _promote_from_waitlist(event, cause=None)

        promoted = self._promoted(event)
        self.assertEqual([e.signup_id for e in promoted], [w1.pk, w2.pk])
        self.assertEqual([e.before["waitlist_position"] for e in promoted], [1, 1])

    def test_deferred_row_keeps_its_rank_ahead(self, _notify: Any) -> None:
        event, _seated, (w1, w2, w3) = self._full_event(seats=1, waiting=3)
        Event.objects.filter(pk=event.pk).update(max_players=3)

        def defer_first(
            _event: Event, candidates: Sequence[EventSignup], *, cache: StandingCache
        ) -> list[EventSignup]:
            ordered = list(candidates)
            return [*ordered[1:], ordered[0]]

        with patch("events.services.standing.promotion_order", defer_first):
            _promote_from_waitlist(event, cause=None)

        promoted = self._promoted(event)
        self.assertEqual([e.signup_id for e in promoted], [w2.pk, w3.pk])
        self.assertEqual([e.before["waitlist_position"] for e in promoted], [2, 2])
        self.assertEqual(self._status(w1), SignupStatus.WAITLISTED)

    def test_demote_restamps_to_back(self, _notify: Any) -> None:
        event, (seat,), (w1,) = self._full_event(waiting=1)
        before_seq = seat.line_seq

        demote_to_waitlist(seat, actor=self.staff_actor)

        seat.refresh_from_db()
        w1.refresh_from_db()
        self.assertGreater(seat.line_seq, w1.line_seq)
        self.assertGreater(seat.line_seq, before_seq)
        self.assertEqual(seat.waitlist_position, 2)
        self.assertEqual(self._waiting_line(event), [w1.pk, seat.pk])

        _promote_from_waitlist(event, cause=None)

        self.assertNotEqual(self._status(w1), SignupStatus.WAITLISTED)
        self.assertEqual(self._status(seat), SignupStatus.WAITLISTED)

    def test_two_demotes_keep_fifo(self, _notify: Any) -> None:
        event, (a, b), (w1,) = self._full_event(seats=2, waiting=1)

        demote_to_waitlist(b, actor=self.staff_actor)
        demote_to_waitlist(a, actor=self.staff_actor)

        self.assertEqual(self._waiting_line(event), [w1.pk, b.pk, a.pk])
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual((b.waitlist_position, a.waitlist_position), (2, 3))

        _promote_from_waitlist(event, cause=None)

        self.assertNotEqual(self._status(w1), SignupStatus.WAITLISTED)
        self.assertNotEqual(self._status(b), SignupStatus.WAITLISTED)
        self.assertEqual(self._status(a), SignupStatus.WAITLISTED)

    def test_demote_ledger_records_computed_rank(self, _notify: Any) -> None:
        event, (seat,), (w1,) = self._full_event(waiting=1)
        EventSignup.objects.filter(pk=w1.pk).update(waitlist_position=7)

        demote_to_waitlist(seat, actor=self.staff_actor)

        entry = SignupLedgerEntry.objects.get(event=event, action=SignupAction.DEMOTED)
        self.assertIsNone(entry.before["waitlist_position"])
        self.assertEqual(entry.after["waitlist_position"], 2)
        self.assertEqual(entry.after["line_seq"], seat.line_seq)
        seat.refresh_from_db()
        self.assertEqual(seat.waitlist_position, 8)

    def test_withdraw_and_reject_clear_stored_position(self, _notify: Any) -> None:
        _event, _seated, (w1, w2) = self._full_event()

        cancel_signup(w1, actor=self.staff_actor)
        reject_signup(w2, actor=self.staff_actor)

        for signup in (w1, w2):
            signup.refresh_from_db()
            self.assertIsNone(signup.waitlist_position)

    def test_withdraw_and_reject_record_rank_before(self, _notify: Any) -> None:
        event, _seated, (w1, w2) = self._full_event()
        EventSignup.objects.filter(pk=w2.pk).update(waitlist_position=9)

        reject_signup(w2, actor=self.staff_actor)
        cancel_signup(w1, actor=self.staff_actor)

        rejected = SignupLedgerEntry.objects.get(
            event=event, action=SignupAction.REJECTED
        )
        withdrew = SignupLedgerEntry.objects.get(
            event=event, action=SignupAction.WITHDREW
        )
        self.assertEqual(rejected.before["waitlist_position"], 2)
        self.assertIsNone(rejected.after["waitlist_position"])
        self.assertEqual(withdrew.before["waitlist_position"], 1)
        self.assertIsNone(withdrew.after["waitlist_position"])


@patch("events.services.notify_signup_changed")
class ResignUpTests(LedgerContractMixin, EventTestCase):
    def _age(self, signup: EventSignup) -> datetime:
        past = tz.now() - timedelta(days=3)
        EventSignup._base_manager.filter(pk=signup.pk).update(
            first_signed_up_at=past, signed_up_at=past
        )
        return past

    def _row(self, signup: EventSignup) -> EventSignup:
        return EventSignup.objects.nocache().get(pk=signup.pk)

    def _subject_entries(self, event: Event) -> list[SignupLedgerEntry]:
        return [e for e in self.ledger(event) if e.subject_user_id == self.subject.pk]

    def _assert_in_place(
        self,
        event: Event,
        old: EventSignup,
        past: datetime,
        later: EventSignup,
        *,
        restamped: bool,
        action: SignupAction,
    ) -> EventSignup:
        self.assertEqual(
            EventSignup.objects.filter(event=event, user=self.subject).count(), 1
        )
        row = self._row(old)
        self.assertEqual(row.first_signed_up_at, past)
        self.assertEqual(row.first_commitment, old.first_commitment)
        self.assertEqual(row.first_rsvp_class, old.first_rsvp_class)
        if restamped:
            self.assertGreater(row.line_seq, later.line_seq)
            self.assertGreater(row.signed_up_at, past)
        else:
            self.assertEqual(row.line_seq, old.line_seq)
            self.assertEqual(row.signed_up_at, past)
        entries = self._subject_entries(event)
        self.assertEqual(entries[-1].action, action)
        self.assertEqual({e.signup_id for e in entries}, {old.pk})
        return row

    def test_rsvp_cancel_rsvp_keeps_row(self, _notify: Any) -> None:
        for forfeits in (True, False):
            with self.subTest(line_withdraw_forfeits=forfeits):
                event = self.make_event(line_withdraw_forfeits=forfeits)
                old = process_rsvp(event, self.subject, actor=self.member_actor)
                later = process_rsvp(event, self.make_user(), actor=self.staff_actor)
                past = self._age(old)
                cancel_signup(old, actor=self.member_actor)

                with capture_logs() as logs:
                    new = process_rsvp(event, self.subject, actor=self.member_actor)

                self.assertEqual(new.pk, old.pk)
                row = self._assert_in_place(
                    event,
                    old,
                    past,
                    later,
                    restamped=forfeits,
                    action=SignupAction.RESIGNED_UP,
                )
                self.assertEqual(row.status, SignupStatus.APPROVED)
                self.assertTrue(row.self_made)
                events = [log["event"] for log in logs]
                self.assertIn("signup_resigned_up_in_place", events)
                self.assertNotIn("signup_cancelled_deleted", events)

    def test_reject_then_rsvp_keeps_row(self, _notify: Any) -> None:
        for forfeits in (True, False):
            with self.subTest(line_withdraw_forfeits=forfeits):
                event = self.make_event(line_withdraw_forfeits=forfeits)
                old = process_rsvp(event, self.subject, actor=self.member_actor)
                later = process_rsvp(event, self.make_user(), actor=self.staff_actor)
                past = self._age(old)
                reject_signup(old, actor=self.staff_actor)

                new = process_rsvp(event, self.subject, actor=self.member_actor)

                self.assertEqual(new.pk, old.pk)
                self._assert_in_place(
                    event,
                    old,
                    past,
                    later,
                    restamped=forfeits,
                    action=SignupAction.RESIGNED_UP,
                )

    def test_bare_decline_then_rsvp(self, _notify: Any) -> None:
        event = self.make_event(line_withdraw_forfeits=False)
        declined = decline_signup(event, self.subject, actor=self.member_actor)
        self.assertIsNone(declined.first_signed_up_at)
        later = process_rsvp(event, self.make_user(), actor=self.staff_actor)

        new = process_rsvp(event, self.subject, actor=self.member_actor)

        self.assertEqual(new.pk, declined.pk)
        row = self._row(declined)
        self.assertIsNotNone(row.first_signed_up_at)
        self.assertEqual(row.first_commitment, Commitment.MAIN)
        self.assertGreater(row.line_seq, later.line_seq)
        entries = self._subject_entries(event)
        self.assertEqual(entries[-1].action, SignupAction.SIGNED_UP)
        self.assertEqual({e.signup_id for e in entries}, {declined.pk})

    def test_maybe_to_main_keeps_row(self, _notify: Any) -> None:
        for restamps in (True, False):
            with self.subTest(line_switch_restamps=restamps):
                event = self.make_event(line_switch_restamps=restamps)
                old = create_tentative_signup(
                    event, self.subject, actor=self.member_actor
                )
                later = process_rsvp(event, self.make_user(), actor=self.staff_actor)
                past = self._age(old)

                with capture_logs() as logs:
                    new = process_rsvp(event, self.subject, actor=self.member_actor)

                self.assertEqual(new.pk, old.pk)
                row = self._assert_in_place(
                    event,
                    old,
                    past,
                    later,
                    restamped=restamps,
                    action=SignupAction.SWITCHED_COMMITMENT,
                )
                self.assertEqual(row.commitment, Commitment.MAIN)
                self.assertEqual(row.first_commitment, Commitment.MAYBE)
                events = [log["event"] for log in logs]
                self.assertIn("signup_switched_to_main_in_place", events)
                self.assertNotIn("signup_tentative_upgraded", events)

    def test_forfeits_off_full_event_returns_to_old_place(self, _notify: Any) -> None:
        event = self.make_event(max_players=1, line_withdraw_forfeits=False)
        a = process_rsvp(event, self.subject, actor=self.member_actor)
        cancel_signup(a, actor=self.member_actor)
        b = process_rsvp(event, self.make_user(), actor=self.staff_actor)
        c = process_rsvp(event, self.make_user(), actor=self.staff_actor)
        self.assertEqual(c.status, SignupStatus.WAITLISTED)

        back = process_rsvp(event, self.subject, actor=self.member_actor)

        self.assertEqual(back.pk, a.pk)
        self.assertEqual(back.status, SignupStatus.WAITLISTED)
        self.assertEqual(self._row(a).line_seq, a.line_seq)

        cancel_signup(b, actor=self.staff_actor)

        self.assertEqual(self._row(a).status, SignupStatus.APPROVED)
        self.assertEqual(self._row(c).status, SignupStatus.WAITLISTED)

    def test_waitlisted_entry_writes_stored_position(self, _notify: Any) -> None:
        event = self.make_event(max_players=1)
        EventSignup.objects.create(
            event=event, user=self.make_user(), status=SignupStatus.APPROVED
        )
        EventSignup.objects.create(
            event=event,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=5,
        )
        old = EventSignup.objects.create(
            event=event, user=self.subject, status=SignupStatus.CANCELLED
        )

        process_rsvp(event, self.subject, actor=self.member_actor)

        row = self._row(old)
        self.assertEqual(row.status, SignupStatus.WAITLISTED)
        self.assertEqual(row.waitlist_position, 6)
        entry = self._subject_entries(event)[-1]
        self.assertIsNone(entry.before["waitlist_position"])
        self.assertEqual(entry.after["waitlist_position"], 2)


@patch("events.services.notify_signup_changed")
class StaffAddTests(LedgerContractMixin, EventTestCase):
    def test_staff_add_over_cancelled_always_restamps(self, _notify: Any) -> None:
        event = self.make_event(
            line_withdraw_forfeits=False, line_switch_restamps=False
        )
        for status in (
            SignupStatus.CANCELLED,
            SignupStatus.REJECTED,
            SignupStatus.TENTATIVE,
        ):
            with self.subTest(status=status):
                user = self.make_user()
                old = EventSignup.objects.create(
                    event=event, user=user, status=SignupStatus.RSVP
                )
                later = EventSignup.objects.create(
                    event=event, user=self.make_user(), status=SignupStatus.RSVP
                )
                EventSignup.objects.filter(pk=old.pk).update(status=status)

                new = staff_add_signup(event, user, actor=self.staff_actor)

                self.assertEqual(new.pk, old.pk)
                row = EventSignup.objects.nocache().get(pk=old.pk)
                self.assertGreater(row.line_seq, later.line_seq)
                self.assertFalse(row.self_made)
                self.assertEqual(row.first_signed_up_at, old.first_signed_up_at)
                entry = [e for e in self.ledger(event) if e.subject_user_id == user.pk][
                    -1
                ]
                self.assertEqual(entry.action, SignupAction.STAFF_ADDED)
                self.assertEqual(entry.signup_id, old.pk)

    def test_staff_add_over_bare_decline_starts_first_fields(
        self, _notify: Any
    ) -> None:
        event = self.make_event(line_withdraw_forfeits=False)
        declined = decline_signup(event, self.subject, actor=self.member_actor)

        staff_add_signup(event, self.subject, actor=self.staff_actor)

        row = EventSignup.objects.nocache().get(pk=declined.pk)
        self.assertEqual(row.first_signed_up_at, row.signed_up_at)
        self.assertEqual(row.first_commitment, Commitment.MAIN)


@patch("events.services.notify_signup_changed")
class NoDeleteTests(LedgerContractMixin, EventTestCase):
    def test_services_never_delete(self, _notify: Any) -> None:
        deleted: list[int] = []

        def receiver(sender: type, instance: EventSignup, **_kwargs: Any) -> None:
            deleted.append(instance.pk)

        post_delete.connect(receiver, sender=EventSignup)
        self.addCleanup(post_delete.disconnect, receiver, sender=EventSignup)
        event = self.make_event()

        signup = process_rsvp(event, self.subject, actor=self.member_actor)
        cancel_signup(signup, actor=self.member_actor)
        process_rsvp(event, self.subject, actor=self.member_actor)

        staffed = process_rsvp(event, self.make_user(), actor=self.staff_actor)
        cancel_signup(staffed, actor=self.staff_actor)
        staff_add_signup(event, staffed.user, actor=self.staff_actor)

        maybe = create_tentative_signup(event, self.make_user(), actor=self.staff_actor)
        process_rsvp(event, maybe.user, actor=self.staff_actor)

        self.assertEqual(deleted, [])
