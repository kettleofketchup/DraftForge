from collections.abc import Sequence
from typing import Any
from unittest.mock import patch

from events.constants import Commitment, SignupAction, SignupStatus
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import (
    _promote_from_waitlist,
    cancel_signup,
    demote_to_waitlist,
    reject_signup,
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
