from datetime import timedelta

from django.utils import timezone as tz

from org.models import OrgLog, Organization
from events.completion import close_event
from events.constants import EventState, SignupStatus
from events.models import Event
from org.conduct.constants import Outcome, OutcomeSource
from org.conduct.services import SetResult, set_outcomes
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome
from org.tests.conduct_base import ConductTestCase

REASON = "checked the lobby"


class SetOutcomesTest(ConductTestCase):
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

    def _finalized_event(self) -> Event:
        return self._event(
            state=EventState.COMPLETED,
            conduct_finalized_at=tz.now() - timedelta(minutes=5),
        )

    def _set_logs(self) -> list[OrgLog]:
        return list(
            OrgLog.objects.filter(organization=self.org, action="set_attendance")
        )

    def test_marks_no_show_with_reason_and_orglog(self) -> None:
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)
        org_user = self.org_user(member)

        result = set_outcomes(
            event,
            actor=self.admin,
            changes=[(org_user, Outcome.NO_SHOW)],
            reason=f"  {REASON}  ",
        )

        self.assertEqual(result, SetResult(changed=1, unchanged=0))
        row = AttendanceOutcome.objects.nocache().get(event=event, org_user=org_user)
        self.assertEqual(row.outcome, Outcome.NO_SHOW)
        self.assertEqual(row.source, OutcomeSource.STAFF)
        self.assertEqual(row.set_by_id, self.admin.pk)
        self.assertEqual(row.reason, REASON)
        self.assertTrue(row.committed)
        self.assertIsNotNone(row.signup_id)
        self.assertIsNone(row.finalized_at)
        logs = self._set_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].actor_id, self.admin.pk)
        details = logs[0].details
        self.assertEqual(details["outcome_pk"], row.pk)
        self.assertEqual(details["event_id"], event.pk)
        self.assertEqual(details["org_user_id"], org_user.pk)
        self.assertEqual(details["old"], {"outcome": "pending", "source": "default"})
        self.assertEqual(details["new"]["outcome"], "no_show")
        self.assertEqual(details["new"]["source"], "staff")
        self.assertEqual(details["reason"], REASON)

    def test_after_finalize_edit_counts_immediately(self) -> None:
        event = self._finalized_event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)
        row = self.outcome(member, event=event)
        finalized_at = row.finalized_at

        set_outcomes(
            event,
            actor=self.admin,
            changes=[(self.org_user(member), Outcome.NO_SHOW)],
            reason=REASON,
        )

        row.refresh_from_db()
        self.assertEqual(row.outcome, Outcome.NO_SHOW)
        self.assertEqual(row.source, OutcomeSource.STAFF)
        self.assertEqual(row.finalized_at, finalized_at)
        self.assertTrue(
            AttendanceOutcome.objects.nocache().counted().filter(pk=row.pk).exists()
        )

    def test_resolves_pending_roll_call_row(self) -> None:
        event = self._finalized_event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)
        row = self.outcome(
            member, event=event, outcome=Outcome.PENDING, finalized=False
        )
        before = tz.now()

        set_outcomes(
            event,
            actor=self.admin,
            changes=[(self.org_user(member), Outcome.ATTENDED)],
            reason=REASON,
        )

        row.refresh_from_db()
        self.assertEqual(row.outcome, Outcome.ATTENDED)
        self.assertIsNotNone(row.finalized_at)
        self.assertGreaterEqual(row.finalized_at, before)

    def test_unchanged_rows_skipped(self) -> None:
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)
        self.outcome(
            member,
            event=event,
            outcome=Outcome.NO_SHOW,
            source=OutcomeSource.STAFF,
            finalized=False,
            reason="earlier",
        )

        result = set_outcomes(
            event,
            actor=self.admin,
            changes=[(self.org_user(member), Outcome.NO_SHOW)],
            reason=REASON,
        )

        self.assertEqual(result, SetResult(changed=0, unchanged=1))
        self.assertEqual(self._set_logs(), [])

    def _assert_refused(
        self, event: Event, changes: list[tuple[OrgUser, str]], reason: str = REASON
    ) -> str:
        with self.assertRaises(ValueError) as ctx:
            set_outcomes(event, actor=self.admin, changes=changes, reason=reason)
        self.assertEqual(AttendanceOutcome.objects.nocache().count(), 0)
        self.assertEqual(self._set_logs(), [])
        return str(ctx.exception)

    def _member_change(
        self, event: Event, outcome: str = Outcome.NO_SHOW
    ) -> list[tuple[OrgUser, str]]:
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)
        return [(self.org_user(member), outcome)]

    def test_rejects_locked_feature(self) -> None:
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=False, actor=None)
        event = self._event()
        message = self._assert_refused(event, self._member_change(event))
        self.assertEqual(message, "Conduct is not enabled for this organization.")

    def test_rejects_short_reason(self) -> None:
        event = self._event()
        self._assert_refused(event, self._member_change(event), reason="  ab  ")

    def test_rejects_long_reason(self) -> None:
        event = self._event()
        self._assert_refused(event, self._member_change(event), reason="x" * 501)

    def test_rejects_pending_outcome(self) -> None:
        event = self._event()
        self._assert_refused(event, self._member_change(event, Outcome.PENDING))

    def test_rejects_unknown_outcome(self) -> None:
        event = self._event()
        self._assert_refused(event, self._member_change(event, "vanished"))

    def test_rejects_cancelled_event(self) -> None:
        event = self._event(state=EventState.CANCELLED, conduct_finalized_at=tz.now())
        message = self._assert_refused(event, self._member_change(event))
        self.assertEqual(
            message,
            "This event was cancelled. Reopen and complete it to record attendance.",
        )

    def test_rejects_untracked_completed_event(self) -> None:
        event = self._event(state=EventState.COMPLETED)
        message = self._assert_refused(event, self._member_change(event))
        self.assertEqual(message, "Attendance was not tracked for this event.")

    def test_rejects_signups_open_event(self) -> None:
        event = self._event(
            state=EventState.SIGNUPS_OPEN, scheduled_at=tz.now() + timedelta(days=1)
        )
        message = self._assert_refused(event, self._member_change(event))
        self.assertEqual(
            message, "Attendance can only be recorded from roll call onwards."
        )

    def test_rejects_duplicate_and_cross_org_and_empty(self) -> None:
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)
        org_user = self.org_user(member)
        self._assert_refused(
            event, [(org_user, Outcome.NO_SHOW), (org_user, Outcome.ATTENDED)]
        )

        other_org = Organization.objects.create(name="Other Org", owner=self.admin)
        outsider = self.make_user()
        self.signup(event, outsider, SignupStatus.APPROVED)
        foreign, _ = OrgUser.objects.get_or_create(
            user=outsider, organization=other_org
        )
        self._assert_refused(
            event, [(org_user, Outcome.NO_SHOW), (foreign, Outcome.NO_SHOW)]
        )

        self._assert_refused(event, [])

    def test_walkin_attended_not_committed(self) -> None:
        event = self._event()
        walkin = self.make_user()

        set_outcomes(
            event,
            actor=self.admin,
            changes=[(self.org_user(walkin), Outcome.ATTENDED)],
            reason=REASON,
        )

        row = AttendanceOutcome.objects.nocache().get(
            event=event, org_user=self.org_user(walkin)
        )
        self.assertFalse(row.committed)
        self.assertIsNone(row.signup_id)
        self.assertEqual(row.outcome, Outcome.ATTENDED)
        row.finalized_at = tz.now()
        row.save(update_fields=["finalized_at"])
        self.assertFalse(
            AttendanceOutcome.objects.nocache().counted().filter(pk=row.pk).exists()
        )

    def test_walkin_no_show_refused(self) -> None:
        event = self._event()
        walkin = self.make_user()
        self.signup(event, walkin, SignupStatus.WAITLISTED)
        self._assert_refused(event, [(self.org_user(walkin), Outcome.NO_SHOW)])

    def test_dropped_signup_is_expected(self) -> None:
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.DROPPED)

        set_outcomes(
            event,
            actor=self.admin,
            changes=[(self.org_user(member), Outcome.NO_SHOW)],
            reason=REASON,
        )

        row = AttendanceOutcome.objects.nocache().get(event=event)
        self.assertTrue(row.committed)
        self.assertEqual(row.outcome, Outcome.NO_SHOW)

    def test_stale_event_instance_after_finalize(self) -> None:
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)
        Event.objects.nocache().filter(pk=event.pk).update(
            state=EventState.COMPLETED, conduct_finalized_at=tz.now()
        )
        self.assertEqual(event.state, EventState.IN_PROGRESS)

        set_outcomes(
            event,
            actor=self.admin,
            changes=[(self.org_user(member), Outcome.NO_SHOW)],
            reason=REASON,
        )

        row = AttendanceOutcome.objects.nocache().get(event=event)
        self.assertIsNotNone(row.finalized_at)

    def test_lock_close_unlock_edit_counts(self) -> None:
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=False, actor=None)
        event = self._event()
        member = self.make_user()
        self.signup(event, member, SignupStatus.APPROVED)
        close_event(
            event, new_state=EventState.COMPLETED, source="admin", actor=self.admin
        )
        self.assertFalse(AttendanceOutcome.objects.nocache().exists())

        self.unlock()
        set_outcomes(
            event,
            actor=self.admin,
            changes=[(self.org_user(member), Outcome.NO_SHOW)],
            reason=REASON,
        )

        row = AttendanceOutcome.objects.nocache().get(event=event)
        self.assertTrue(
            AttendanceOutcome.objects.nocache().counted().filter(pk=row.pk).exists()
        )
