from datetime import datetime, timedelta
from unittest.mock import patch

from django.db import connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz

from app.models import CustomUser
from events.completion import CloseResult, close_event
from events.constants import ActorRole, EventState, SignupMeans, SignupStatus
from events.ledger import SignupActor
from events.models import Event, EventSignup, ReadyCheck, RollCallMode
from events.ready_check import close_ready_check, confirm_ready, open_ready_check
from events.ready_check_constants import (
    ReadyCheckConfirmVia,
    ReadyCheckOutcome,
    ReadyCheckPhase,
)
from events.reopen import reopen_event
from events.services import cancel_event
from org.conduct.adapter import CONDUCT
from org.conduct.attendance import event_attendance
from org.conduct.constants import Outcome, OutcomeSource
from org.conduct.finalize import finalize_event_outcomes
from org.conduct.gate import get_conduct_settings
from org.conduct.queries import member_scores
from org.conduct.services import set_outcomes
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import OrgLog
from org.models_conduct import AttendanceOutcome
from org.tests.conduct_base import ConductTestCase


class FinalizeAtCompletionTest(ConductTestCase):
    def setUp(self) -> None:
        self.unlock()
        self.starts_at = tz.now() - timedelta(minutes=30)

    def _event(self, **overrides: object) -> Event:
        fields: dict[str, object] = {
            "state": EventState.IN_PROGRESS,
            "scheduled_at": self.starts_at,
        }
        fields.update(overrides)
        return self.make_event(**fields)

    def _complete(self, event: Event, *, source: str = "admin") -> CloseResult:
        actor = self.admin if source == "admin" else None
        return close_event(
            event, new_state=EventState.COMPLETED, source=source, actor=actor
        )

    def _rows(self, event: Event) -> dict[int, AttendanceOutcome]:
        return {
            row.org_user.user_id: row
            for row in AttendanceOutcome.objects.nocache()
            .filter(event_id=event.pk)
            .select_related("org_user")
        }

    def _finalize_logs(self) -> list[OrgLog]:
        return list(
            OrgLog.objects.filter(organization=self.org, action="finalize_attendance")
        )

    def _late_cancel(
        self,
        user: CustomUser,
        event: Event,
        *,
        cancelled_at: datetime,
        outcome: str = Outcome.LATE_CANCEL,
    ) -> AttendanceOutcome:
        return self.outcome(
            user,
            event=event,
            outcome=outcome,
            source=OutcomeSource.LATE_CANCEL,
            finalized=False,
            cancelled_at=cancelled_at,
        )

    def test_defaults_to_attended(self) -> None:
        event = self._event()
        users = [self.make_user(), self.make_user()]
        for user in users:
            self.signup(event, user, SignupStatus.APPROVED)

        self.assertTrue(self._complete(event).closed)

        event = Event.objects.nocache().get(pk=event.pk)
        self.assertIsNotNone(event.conduct_finalized_at)
        rows = self._rows(event)
        self.assertEqual(set(rows), {user.pk for user in users})
        for row in rows.values():
            self.assertEqual(row.outcome, Outcome.ATTENDED)
            self.assertEqual(row.source, OutcomeSource.DEFAULT)
            self.assertEqual(row.finalized_at, event.conduct_finalized_at)
            self.assertEqual(row.signup_status_at_close, SignupStatus.APPROVED)
            self.assertIsNotNone(row.signup_id)
        logs = self._finalize_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].actor_id, self.admin.pk)
        self.assertEqual(
            logs[0].details,
            {
                "event_id": event.pk,
                "attended": 2,
                "no_show": 0,
                "late_cancel": 0,
                "excused": 0,
                "pending": 0,
            },
        )

    def test_staff_row_preserved(self) -> None:
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)
        staff_row = self.outcome(
            member,
            event=event,
            outcome=Outcome.NO_SHOW,
            source=OutcomeSource.STAFF,
            finalized=False,
            reason="never joined",
        )

        self._complete(event)

        staff_row.refresh_from_db()
        self.assertEqual(staff_row.outcome, Outcome.NO_SHOW)
        self.assertEqual(staff_row.source, OutcomeSource.STAFF)
        self.assertEqual(staff_row.reason, "never joined")
        self.assertIsNotNone(staff_row.finalized_at)
        self.assertEqual(staff_row.signup_status_at_close, SignupStatus.APPROVED)

    def test_resignup_clears_late_cancel(self) -> None:
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)
        row = self._late_cancel(
            member, event, cancelled_at=self.starts_at - timedelta(hours=1)
        )

        self._complete(event)

        row.refresh_from_db()
        self.assertEqual(row.outcome, Outcome.ATTENDED)
        self.assertEqual(row.source, OutcomeSource.DEFAULT)
        self.assertIsNone(row.cancelled_at)
        self.assertIsNotNone(row.finalized_at)

    def test_reschedule_later_deletes_late_cancel(self) -> None:
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.CANCELLED)
        row = self._late_cancel(
            member, event, cancelled_at=self.starts_at - timedelta(hours=5)
        )

        self._complete(event)

        self.assertFalse(AttendanceOutcome.objects.nocache().filter(pk=row.pk).exists())

    def test_reschedule_downgrades_post_start_no_show(self) -> None:
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.CANCELLED)
        row = self._late_cancel(
            member,
            event,
            cancelled_at=self.starts_at - timedelta(hours=1),
            outcome=Outcome.NO_SHOW,
        )

        self._complete(event)

        row.refresh_from_db()
        self.assertEqual(row.outcome, Outcome.LATE_CANCEL)
        self.assertEqual(row.source, OutcomeSource.LATE_CANCEL)
        self.assertIsNotNone(row.finalized_at)
        self.assertEqual(row.event_starts_at, self.starts_at)
        self.assertEqual(row.signup_status_at_close, SignupStatus.CANCELLED)

    def test_roll_call_unconfirmed_stay_pending(self) -> None:
        event = self._event(roll_call_enabled=True)
        confirmed = self.make_user()
        unconfirmed = self.make_user()
        self.signup(event, confirmed, SignupStatus.CONFIRMED)
        self.signup(event, unconfirmed, SignupStatus.APPROVED)

        self._complete(event)

        rows = self._rows(event)
        self.assertEqual(rows[confirmed.pk].outcome, Outcome.ATTENDED)
        self.assertIsNotNone(rows[confirmed.pk].finalized_at)
        pending = rows[unconfirmed.pk]
        self.assertEqual(pending.outcome, Outcome.PENDING)
        self.assertIsNone(pending.finalized_at)
        self.assertEqual(pending.signup_status_at_close, SignupStatus.APPROVED)
        self.assertEqual(self._finalize_logs()[0].details["pending"], 1)

    def test_roll_call_nobody_confirmed_defaults(self) -> None:
        event = self._event(roll_call_enabled=True)
        users = [self.make_user(), self.make_user()]
        for user in users:
            self.signup(event, user, SignupStatus.APPROVED)

        self._complete(event)

        rows = self._rows(event)
        self.assertEqual(len(rows), 2)
        for row in rows.values():
            self.assertEqual(row.outcome, Outcome.ATTENDED)

    def test_qualifying_ready_check_disables_roll_call_pending(self) -> None:
        event = self._event(roll_call_enabled=True)
        confirmed = self.make_user()
        unconfirmed = self.make_user()
        self.signup(event, confirmed, SignupStatus.CONFIRMED)
        self.signup(event, unconfirmed, SignupStatus.APPROVED)
        ReadyCheck.objects.create(
            event=event,
            phase=ReadyCheckPhase.CLOSED,
            outcome=ReadyCheckOutcome.BINDING,
            closed_at=tz.now(),
            settings_snapshot={"roll_call_enabled": True},
        )

        self._complete(event)

        self.assertEqual(self._rows(event)[unconfirmed.pk].outcome, Outcome.ATTENDED)

    def test_manual_approval_rsvps_get_rows(self) -> None:
        event = self._event(auto_approve=False)
        users = [self.make_user(), self.make_user()]
        for user in users:
            self.signup(event, user, SignupStatus.RSVP)

        self._complete(event)

        rows = self._rows(event)
        self.assertEqual(set(rows), {user.pk for user in users})
        for row in rows.values():
            self.assertEqual(row.outcome, Outcome.ATTENDED)
            self.assertEqual(row.signup_status_at_close, SignupStatus.RSVP)

    def test_waitlisted_tentative_rejected_get_no_rows(self) -> None:
        event = self._event()
        for status in (
            SignupStatus.WAITLISTED,
            SignupStatus.TENTATIVE,
            SignupStatus.REJECTED,
            SignupStatus.PENDING_APPROVAL,
            SignupStatus.CANCELLED,
            SignupStatus.RSVP,
        ):
            self.signup(event, self.make_user(), status)

        self._complete(event)

        self.assertEqual(self._rows(event), {})

    def test_idempotent(self) -> None:
        event = self._event()
        canceller = self.make_user()
        seeded = self.make_user()
        self.signup(event, canceller, SignupStatus.CANCELLED)
        self.signup(event, seeded, SignupStatus.APPROVED)
        self._late_cancel(
            canceller, event, cancelled_at=self.starts_at - timedelta(hours=1)
        )
        self.outcome(
            seeded,
            event=event,
            outcome=Outcome.ATTENDED,
            source=OutcomeSource.VOICE,
            finalized=False,
        )
        now = tz.now()

        with transaction.atomic():
            first = finalize_event_outcomes(event, now=now, actor=None)
        snapshot = list(
            AttendanceOutcome.objects.nocache()
            .filter(event=event)
            .order_by("pk")
            .values()
        )
        with transaction.atomic():
            second = finalize_event_outcomes(
                event, now=now + timedelta(minutes=5), actor=self.admin
            )

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(
            list(
                AttendanceOutcome.objects.nocache()
                .filter(event=event)
                .order_by("pk")
                .values()
            ),
            snapshot,
        )
        self.assertEqual(self._finalize_logs(), [])

    def test_locked_feature_stamps_only(self) -> None:
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=False, actor=None)
        event = self._event()
        staff_member = self.make_user()
        canceller = self.make_user()
        approved = self.make_user()
        self.signup(event, staff_member, SignupStatus.APPROVED)
        self.signup(event, canceller, SignupStatus.CANCELLED)
        self.signup(event, approved, SignupStatus.APPROVED)
        staff_row = self.outcome(
            staff_member,
            event=event,
            outcome=Outcome.EXCUSED,
            source=OutcomeSource.STAFF,
            finalized=False,
            reason="family emergency",
        )
        late_row = self._late_cancel(
            canceller, event, cancelled_at=self.starts_at - timedelta(hours=1)
        )

        self._complete(event)

        event = Event.objects.nocache().get(pk=event.pk)
        self.assertIsNotNone(event.conduct_finalized_at)
        rows = self._rows(event)
        self.assertEqual(set(rows), {staff_member.pk, canceller.pk})
        for row in (staff_row, late_row):
            row.refresh_from_db()
            self.assertEqual(row.finalized_at, event.conduct_finalized_at)

    def test_auto_close_finalizes(self) -> None:
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)

        self.assertTrue(self._complete(event, source="auto").closed)

        rows = self._rows(event)
        self.assertEqual(rows[member.pk].outcome, Outcome.ATTENDED)
        self.assertIsNotNone(rows[member.pk].finalized_at)
        self.assertEqual(self._finalize_logs(), [])

    def test_close_hook_exception_rolls_back(self) -> None:
        event = self._event()
        self.signup(event, self.make_user(), SignupStatus.APPROVED)

        with (
            patch(
                "org.conduct.adapter.finalize_event_outcomes",
                side_effect=RuntimeError("boom"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self._complete(event)

        event = Event.objects.nocache().get(pk=event.pk)
        self.assertEqual(event.state, EventState.IN_PROGRESS)
        self.assertIsNone(event.conduct_finalized_at)
        self.assertIsNone(event.contributions_awarded_at)
        self.assertEqual(self._rows(event), {})

    def test_close_hook_stamps_event_without_rereading(self) -> None:
        event = self._event()
        now = tz.now()

        with (
            transaction.atomic(),
            CaptureQueriesContext(connection) as ctx,
        ):
            CONDUCT.on_event_closed(
                event, cancelled=False, source="admin", actor=self.admin, now=now
            )

        self.assertEqual(event.conduct_finalized_at, now)
        self.assertFalse(
            [
                q["sql"]
                for q in ctx.captured_queries
                if q["sql"].startswith('SELECT "events_event"."conduct_finalized_at"')
            ]
        )

    def test_close_hook_keeps_earlier_stamp(self) -> None:
        event = self._event()
        earlier = tz.now() - timedelta(hours=1)
        Event.objects.filter(pk=event.pk).update(conduct_finalized_at=earlier)

        with transaction.atomic():
            CONDUCT.on_event_closed(
                event, cancelled=False, source="admin", actor=self.admin, now=tz.now()
            )

        self.assertEqual(event.conduct_finalized_at, earlier)

    def test_cancel_closes_do_not_finalize(self) -> None:
        event = self._event(state=EventState.ROLL_CALL)
        self.signup(event, self.make_user(), SignupStatus.APPROVED)

        close_event(
            event, new_state=EventState.CANCELLED, source="admin", actor=self.admin
        )

        self.assertEqual(self._rows(event), {})
        self.assertEqual(self._finalize_logs(), [])

    def test_cancel_reopen_complete_finalizes(self) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        approved = self.make_user()
        canceller = self.make_user()
        excused = self.make_user()
        self.signup(event, approved, SignupStatus.APPROVED)
        self.signup(event, canceller, SignupStatus.CANCELLED)
        self.signup(event, excused, SignupStatus.APPROVED)
        late_row = self._late_cancel(
            canceller, event, cancelled_at=self.starts_at - timedelta(hours=1)
        )
        staff_row = self.outcome(
            excused,
            event=event,
            outcome=Outcome.EXCUSED,
            source=OutcomeSource.STAFF,
            finalized=False,
            reason="internet outage",
        )

        cancel_event(event, actor=self.admin)
        late_row.refresh_from_db()
        self.assertIsNotNone(late_row.voided_at)
        self.assertIsNotNone(
            Event.objects.nocache().get(pk=event.pk).conduct_finalized_at
        )

        event = Event.objects.nocache().get(pk=event.pk)
        self.assertTrue(reopen_event(event, actor=self.admin).reopened)
        event = Event.objects.nocache().get(pk=event.pk)
        self.assertIsNone(event.conduct_finalized_at)
        event.transition_state(EventState.IN_PROGRESS)
        event = Event.objects.nocache().get(pk=event.pk)

        self.assertTrue(self._complete(event).closed)

        event = Event.objects.nocache().get(pk=event.pk)
        self.assertIsNotNone(event.conduct_finalized_at)
        for row in (late_row, staff_row):
            row.refresh_from_db()
            self.assertIsNone(row.voided_at)
            self.assertIsNotNone(row.finalized_at)
        self.assertEqual(late_row.outcome, Outcome.LATE_CANCEL)
        self.assertEqual(staff_row.outcome, Outcome.EXCUSED)
        rows = self._rows(event)
        self.assertEqual(rows[approved.pk].outcome, Outcome.ATTENDED)
        self.assertEqual(rows[approved.pk].source, OutcomeSource.DEFAULT)
        scores = member_scores(
            self.org.pk,
            [late_row.org_user_id],
            now=tz.now(),
            settings=get_conduct_settings(self.org),
        )
        self.assertEqual(scores[late_row.org_user_id].counted_events, 1)


class ReadyCheckConductTest(ConductTestCase):
    def setUp(self) -> None:
        self.unlock()
        self.helper = self.make_user()

    def _event(self, **overrides: object) -> Event:
        fields: dict[str, object] = {
            "scheduled_at": tz.now() - timedelta(minutes=30),
        }
        fields.update(overrides)
        event = self.make_event(**fields)
        event.helpers.add(self.helper)
        return event

    def _actor(self) -> SignupActor:
        return SignupActor(
            user=self.helper, role=ActorRole.STAFF, means=SignupMeans.WEB
        )

    def _members(self, event: Event, count: int) -> list[EventSignup]:
        return [
            self.signup(event, self.make_user(), SignupStatus.APPROVED)
            for _ in range(count)
        ]

    def _run_check(self, event: Event, confirm: list[EventSignup]) -> ReadyCheck:
        actor = self._actor()
        open_ready_check(event, actor=actor)
        for signup in confirm:
            confirm_ready(event, signup.user, via=ReadyCheckConfirmVia.WEB, actor=actor)
        result = close_ready_check(event, actor=actor)
        assert result.check is not None
        return result.check

    def _complete(self, event: Event) -> Event:
        event = Event.objects.nocache().get(pk=event.pk)
        event.transition_state(EventState.IN_PROGRESS)
        event = Event.objects.nocache().get(pk=event.pk)
        self.assertTrue(
            close_event(
                event,
                new_state=EventState.COMPLETED,
                source="admin",
                actor=self.admin,
            ).closed
        )
        return Event.objects.nocache().get(pk=event.pk)

    def _rows(self, event: Event) -> dict[int, AttendanceOutcome]:
        return {
            row.org_user.user_id: row
            for row in AttendanceOutcome.objects.nocache()
            .filter(event_id=event.pk)
            .select_related("org_user")
        }

    def test_staff_verified_check_keeps_unconfirmed_pending(self) -> None:
        event = self._event(roll_call_enabled=True)
        confirmed, unconfirmed = self._members(event, 2)

        check = self._run_check(event, [confirmed])
        self.assertEqual(check.outcome, ReadyCheckOutcome.STAFF_VERIFIED)
        event = self._complete(event)

        rows = self._rows(event)
        self.assertEqual(
            (rows[confirmed.user_id].outcome, rows[confirmed.user_id].source),
            (Outcome.ATTENDED, OutcomeSource.READY_CHECK),
        )
        pending = rows[unconfirmed.user_id]
        self.assertEqual(
            (pending.outcome, pending.source), (Outcome.PENDING, OutcomeSource.DEFAULT)
        )
        self.assertIsNone(pending.finalized_at)
        flags = {
            row["member"]["user_pk"]: row["flag"]
            for row in event_attendance(event, now=tz.now())["rows"]
        }
        self.assertEqual(flags[unconfirmed.user_id], "roll_call_unconfirmed")
        self.assertIsNone(flags[confirmed.user_id])

    def test_roll_call_off_check_does_not_change_sources(self) -> None:
        event = self._event(roll_call_enabled=False)
        confirmed, unconfirmed = self._members(event, 2)

        check = self._run_check(event, [confirmed])
        self.assertEqual(check.phase, ReadyCheckPhase.CLOSED)
        self.assertEqual(check.outcome, ReadyCheckOutcome.STAFF_VERIFIED)
        event = self._complete(event)

        rows = self._rows(event)
        self.assertEqual(set(rows), {confirmed.user_id, unconfirmed.user_id})
        for row in rows.values():
            self.assertEqual(
                (row.outcome, row.source), (Outcome.ATTENDED, OutcomeSource.DEFAULT)
            )
        for row in event_attendance(event, now=tz.now())["rows"]:
            self.assertIsNone(row["flag"])

    @override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
    def test_helper_closed_automatic_check_sets_no_show_and_staff_override_wins(
        self,
    ) -> None:
        event = self._event(
            roll_call_enabled=True, roll_call_mode=RollCallMode.AUTOMATIC
        )
        signups = self._members(event, 4)
        dropped = signups[3]

        check = self._run_check(event, signups[:3])
        self.assertEqual(check.outcome, ReadyCheckOutcome.BINDING)
        dropped.refresh_from_db()
        self.assertEqual(dropped.status, SignupStatus.DROPPED)
        event = self._complete(event)

        row = self._rows(event)[dropped.user_id]
        self.assertEqual(
            (row.outcome, row.source), (Outcome.NO_SHOW, OutcomeSource.READY_CHECK)
        )

        set_outcomes(
            event,
            actor=self.admin,
            changes=[(self.org_user(dropped.user), Outcome.EXCUSED)],
            reason="host misclicked the close",
        )

        row.refresh_from_db()
        self.assertEqual(
            (row.outcome, row.source), (Outcome.EXCUSED, OutcomeSource.STAFF)
        )
        self.assertEqual(row.set_by_id, self.admin.pk)
