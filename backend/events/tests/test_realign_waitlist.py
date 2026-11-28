from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.apps import apps
from django.db.models import Max
from django.utils import timezone as tz
from structlog.testing import capture_logs

from events.constants import EventState, SignupAction, SignupStatus
from events.line_backfill import realign_waitlist
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import cancel_signup
from events.tests.base import EventTestCase
from events.tests.test_signup_ledger_contract import LedgerContractMixin


class RealignWaitlistTests(LedgerContractMixin, EventTestCase):
    def _event(
        self, positions: list[int | None], **overrides: object
    ) -> tuple[Event, EventSignup, list[EventSignup]]:
        event = self.make_event(max_players=1, **overrides)
        seated = EventSignup.objects.create(
            event=event, user=self.make_user(), status=SignupStatus.APPROVED
        )
        waiting = [
            EventSignup.objects.create(
                event=event,
                user=self.make_user(),
                status=SignupStatus.WAITLISTED,
                waitlist_position=pos,
            )
            for pos in positions
        ]
        return event, seated, waiting

    def _line(self, event: Event) -> list[int]:
        return list(
            EventSignup.objects.nocache()
            .filter(event=event, status=SignupStatus.WAITLISTED)
            .in_line_order()
            .values_list("pk", flat=True)
        )

    def _seqs(self, event: Event) -> dict[int, int | None]:
        return dict(
            EventSignup.objects.nocache()
            .filter(event=event)
            .values_list("pk", "line_seq")
        )

    def _max_seq(self, event: Event) -> int:
        return (
            EventSignup.objects.nocache()
            .filter(event=event)
            .aggregate(top=Max("line_seq"))["top"]
        )

    def test_diverged_event_realigned_to_waitlist_order(self) -> None:
        event, seated, (w1, w2, w3) = self._event([3, 1, 2])
        top = self._max_seq(event)
        stamps = dict(
            EventSignup.objects.nocache()
            .filter(event=event)
            .values_list("pk", "signed_up_at")
        )
        ledger_before = SignupLedgerEntry.objects.filter(event=event).count()

        with capture_logs() as logs:
            realigned = realign_waitlist(apps)

        self.assertEqual(realigned, 1)
        self.assertEqual(self._line(event), [w2.pk, w3.pk, w1.pk])
        seqs = self._seqs(event)
        for row in (w1, w2, w3):
            self.assertGreater(seqs[row.pk], top)
        self.assertEqual(seqs[seated.pk], seated.line_seq)
        self.assertEqual(
            dict(
                EventSignup.objects.nocache()
                .filter(event=event)
                .values_list("pk", "signed_up_at")
            ),
            stamps,
        )
        self.assertEqual(
            SignupLedgerEntry.objects.filter(event=event).count(), ledger_before
        )
        entry = next(e for e in logs if e["event"] == "waitlist_line_realigned")
        self.assertEqual(entry["system"], "events")
        self.assertEqual(entry["subsystem"], "migration")
        self.assertEqual(entry["events"], 1)
        self.assertEqual(entry["rows"], 3)

    def test_aligned_event_untouched(self) -> None:
        event, _seated, _waiting = self._event([1, 2, 3])
        seqs = self._seqs(event)

        self.assertEqual(realign_waitlist(apps), 0)
        self.assertEqual(self._seqs(event), seqs)

    def test_single_waitlisted_row_skipped(self) -> None:
        event, _seated, _waiting = self._event([7])
        seqs = self._seqs(event)

        self.assertEqual(realign_waitlist(apps), 0)
        self.assertEqual(self._seqs(event), seqs)

    def test_second_run_is_noop(self) -> None:
        event, _seated, _waiting = self._event([2, 1])
        self.assertEqual(realign_waitlist(apps), 1)
        seqs = self._seqs(event)

        self.assertEqual(realign_waitlist(apps), 0)
        self.assertEqual(self._seqs(event), seqs)

    @patch("events.services.notify_signup_changed")
    def test_any_state_realigned(self, _notify: Any) -> None:
        event, seated, (w1, w2) = self._event([2, 1])
        Event.objects.filter(pk=event.pk).update(state=EventState.COMPLETED)

        self.assertEqual(realign_waitlist(apps), 1)

        Event.objects.filter(pk=event.pk).update(state=EventState.SIGNUPS_OPEN)
        cancel_signup(EventSignup.objects.get(pk=seated.pk), actor=self.staff_actor)

        promoted = SignupLedgerEntry.objects.get(
            event=event, action=SignupAction.PROMOTED
        )
        self.assertEqual(promoted.signup_id, w2.pk)
        self.assertEqual(
            EventSignup.objects.nocache().get(pk=w1.pk).status,
            SignupStatus.WAITLISTED,
        )

    def test_null_positions_sort_last(self) -> None:
        event, _seated, (w1, w2, w3, w4) = self._event([None, 2, 1, None])
        EventSignup.objects.filter(pk=w4.pk).update(
            created_at=tz.now() - timedelta(days=1)
        )

        self.assertEqual(realign_waitlist(apps), 1)
        self.assertEqual(self._line(event), [w3.pk, w2.pk, w4.pk, w1.pk])
