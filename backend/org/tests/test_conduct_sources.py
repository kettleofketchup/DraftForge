from datetime import timedelta
from unittest import skipUnless

from django.utils import timezone as tz

from app.models import CustomUser
from events.completion import close_event
from events.constants import (
    ActorRole,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
)
from events.ledger import SignupActor, record_signup_change
from events.models import (
    Event,
    EventSignup,
    EventVoicePresence,
    ReadyCheck,
    ReadyCheckEntry,
)
from events.ready_check_constants import (
    ReadyCheckEntryState,
    ReadyCheckOutcome,
    ReadyCheckPhase,
)
from org.conduct.constants import Outcome, OutcomeSource
from org.conduct.sources import automatic_outcomes
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome
from org.tests.conduct_base import ConductTestCase

HAS_CULL = hasattr(SignupMeans, "CULL")


class AutomaticOutcomesTest(ConductTestCase):
    def setUp(self) -> None:
        self.unlock()
        self.event = self.make_event(
            state=EventState.IN_PROGRESS,
            scheduled_at=tz.now() - timedelta(minutes=30),
        )

    def _check(
        self,
        *,
        phase: str = ReadyCheckPhase.CLOSED,
        outcome: str = ReadyCheckOutcome.BINDING,
        closed_at_offset: int = 0,
    ) -> ReadyCheck:
        return ReadyCheck.objects.create(
            event=self.event,
            phase=phase,
            outcome=outcome,
            closed_at=tz.now() + timedelta(minutes=closed_at_offset),
        )

    def _entry(
        self, check: ReadyCheck, signup: EventSignup, state: str
    ) -> ReadyCheckEntry:
        return ReadyCheckEntry.objects.create(
            ready_check=check, signup=signup, user=signup.user, state=state
        )

    def _member(self, status: str = SignupStatus.APPROVED) -> EventSignup:
        return self.signup(self.event, self.make_user(), status)

    def _cull(self, signup: EventSignup) -> None:
        record_signup_change(
            event=self.event,
            subject=signup.user,
            actor=SignupActor(
                user=None, role=ActorRole.SYSTEM, means=getattr(SignupMeans, "CULL")
            ),
            action=SignupAction.REJECTED,
            signup=signup,
        )

    def _run(self, *signups: EventSignup) -> dict[int, tuple[Outcome, OutcomeSource]]:
        org_users: dict[int, OrgUser] = {
            s.user_id: self.org_user(s.user) for s in signups
        }
        return automatic_outcomes(self.event, org_users, list(signups))

    def _key(self, user: CustomUser) -> int:
        return self.org_user(user).pk

    def test_no_rows_returns_empty(self) -> None:
        signups = [self._member(), self._member(SignupStatus.CONFIRMED)]
        self.assertEqual(self._run(*signups), {})

    def test_latest_closed_binding_check_selected(self) -> None:
        stale = self._member()
        current = self._member()
        cancelled = self._check(phase=ReadyCheckPhase.CANCELLED, closed_at_offset=-60)
        self._entry(cancelled, stale, ReadyCheckEntryState.CONFIRMED)
        closed = self._check(closed_at_offset=0)
        self._entry(closed, current, ReadyCheckEntryState.CONFIRMED)

        result = self._run(stale, current)

        self.assertEqual(
            result,
            {self._key(current.user): (Outcome.ATTENDED, OutcomeSource.READY_CHECK)},
        )

    def test_open_escalated_held_checks_give_nothing(self) -> None:
        for phase in (
            ReadyCheckPhase.OPEN,
            ReadyCheckPhase.ESCALATED,
            ReadyCheckPhase.HELD,
        ):
            with self.subTest(phase=phase):
                ReadyCheck.objects.filter(event=self.event).delete()
                signup = self._member()
                check = self._check(phase=phase)
                self._entry(check, signup, ReadyCheckEntryState.CONFIRMED)
                self.assertEqual(self._run(signup), {})

    def test_blank_and_non_binding_outcomes_give_nothing(self) -> None:
        for outcome in ("", ReadyCheckOutcome.NON_BINDING):
            with self.subTest(outcome=outcome):
                ReadyCheck.objects.filter(event=self.event).delete()
                signup = self._member()
                check = self._check(outcome=outcome)
                self._entry(check, signup, ReadyCheckEntryState.CONFIRMED)
                self.assertEqual(self._run(signup), {})

    def test_staff_verified_and_resolved_count(self) -> None:
        for outcome in (
            ReadyCheckOutcome.STAFF_VERIFIED,
            ReadyCheckOutcome.STAFF_RESOLVED,
        ):
            with self.subTest(outcome=outcome):
                ReadyCheck.objects.filter(event=self.event).delete()
                signup = self._member()
                check = self._check(outcome=outcome)
                self._entry(check, signup, ReadyCheckEntryState.CONFIRMED)
                self.assertEqual(
                    self._run(signup),
                    {
                        self._key(signup.user): (
                            Outcome.ATTENDED,
                            OutcomeSource.READY_CHECK,
                        )
                    },
                )

    def test_confirmed_entry_attended(self) -> None:
        signup = self._member(SignupStatus.CONFIRMED)
        self._entry(self._check(), signup, ReadyCheckEntryState.CONFIRMED)

        self.assertEqual(
            self._run(signup),
            {self._key(signup.user): (Outcome.ATTENDED, OutcomeSource.READY_CHECK)},
        )

    def test_excused_and_pending_entries_nothing(self) -> None:
        check = self._check()
        excused = self._member()
        pending = self._member()
        self._entry(check, excused, ReadyCheckEntryState.EXCUSED)
        self._entry(check, pending, ReadyCheckEntryState.PENDING)

        self.assertEqual(self._run(excused, pending), {})

    def test_dropped_entry_with_reinstated_signup_nothing(self) -> None:
        signup = self._member()
        self._entry(self._check(), signup, ReadyCheckEntryState.DROPPED)

        self.assertEqual(self._run(signup), {})

    def test_dropped_signup_with_dropped_entry_ready_check_no_show(self) -> None:
        signup = self._member(SignupStatus.DROPPED)
        self._entry(self._check(), signup, ReadyCheckEntryState.DROPPED)

        self.assertEqual(
            self._run(signup),
            {self._key(signup.user): (Outcome.NO_SHOW, OutcomeSource.READY_CHECK)},
        )

    def test_dropped_signup_beats_voice(self) -> None:
        signup = self._member(SignupStatus.DROPPED)
        self._entry(self._check(), signup, ReadyCheckEntryState.DROPPED)
        EventVoicePresence.objects.create(
            event=self.event, user=signup.user, present=True
        )

        self.assertEqual(
            self._run(signup),
            {self._key(signup.user): (Outcome.NO_SHOW, OutcomeSource.READY_CHECK)},
        )

    def test_unattributed_dropped_signup_nothing(self) -> None:
        signup = self._member(SignupStatus.DROPPED)
        EventVoicePresence.objects.create(
            event=self.event, user=signup.user, present=True
        )

        self.assertEqual(self._run(signup), {})

    @skipUnless(HAS_CULL, "SignupMeans has no CULL member yet")
    def test_confirmed_then_culled_is_no_show(self) -> None:
        signup = self._member(SignupStatus.DROPPED)
        self._entry(self._check(), signup, ReadyCheckEntryState.CONFIRMED)
        self._cull(signup)

        self.assertEqual(
            self._run(signup),
            {self._key(signup.user): (Outcome.NO_SHOW, OutcomeSource.CULL)},
        )

    @skipUnless(HAS_CULL, "SignupMeans has no CULL member yet")
    def test_dropped_with_ledger_cull_attribution(self) -> None:
        signup = self._member(SignupStatus.DROPPED)
        self._cull(signup)

        self.assertEqual(
            self._run(signup),
            {self._key(signup.user): (Outcome.NO_SHOW, OutcomeSource.CULL)},
        )

    def test_voice_upgrades_only(self) -> None:
        present = self._member()
        joined = self._member()
        absent = self._member()
        EventVoicePresence.objects.create(
            event=self.event, user=present.user, present=True
        )
        EventVoicePresence.objects.create(
            event=self.event,
            user=joined.user,
            present=False,
            first_joined_at=tz.now(),
        )
        EventVoicePresence.objects.create(
            event=self.event, user=absent.user, present=False
        )

        self.assertEqual(
            self._run(present, joined, absent),
            {
                self._key(present.user): (Outcome.ATTENDED, OutcomeSource.VOICE),
                self._key(joined.user): (Outcome.ATTENDED, OutcomeSource.VOICE),
            },
        )


class SourcesAtFinalizeTest(ConductTestCase):
    def setUp(self) -> None:
        self.unlock()
        self.event = self.make_event(
            state=EventState.IN_PROGRESS,
            scheduled_at=tz.now() - timedelta(minutes=30),
        )

    def _complete(self) -> None:
        close_event(
            self.event,
            new_state=EventState.COMPLETED,
            source="admin",
            actor=self.admin,
        )

    def _row(self, user: CustomUser) -> AttendanceOutcome:
        return (
            AttendanceOutcome.objects.nocache()
            .select_related("org_user")
            .get(event_id=self.event.pk, org_user__user=user)
        )

    def test_unattributed_drop_stays_pending_and_flagged(self) -> None:
        user = self.make_user()
        self.signup(self.event, user, SignupStatus.DROPPED)

        self._complete()

        row = self._row(user)
        self.assertEqual(row.outcome, Outcome.PENDING)
        self.assertEqual(row.source, OutcomeSource.DEFAULT)
        self.assertIsNone(row.finalized_at)
        self.assertEqual(row.signup_status_at_close, SignupStatus.DROPPED)

    def test_ready_check_drop_finalized_as_no_show(self) -> None:
        user = self.make_user()
        signup = self.signup(self.event, user, SignupStatus.DROPPED)
        check = ReadyCheck.objects.create(
            event=self.event,
            phase=ReadyCheckPhase.CLOSED,
            outcome=ReadyCheckOutcome.BINDING,
            closed_at=tz.now(),
        )
        ReadyCheckEntry.objects.create(
            ready_check=check,
            signup=signup,
            user=user,
            state=ReadyCheckEntryState.DROPPED,
        )

        self._complete()

        row = self._row(user)
        self.assertEqual(row.outcome, Outcome.NO_SHOW)
        self.assertEqual(row.source, OutcomeSource.READY_CHECK)
        self.assertIsNotNone(row.finalized_at)

    def test_staff_rows_never_touched(self) -> None:
        user = self.make_user()
        signup = self.signup(self.event, user, SignupStatus.DROPPED)
        check = ReadyCheck.objects.create(
            event=self.event,
            phase=ReadyCheckPhase.CLOSED,
            outcome=ReadyCheckOutcome.BINDING,
            closed_at=tz.now(),
        )
        ReadyCheckEntry.objects.create(
            ready_check=check,
            signup=signup,
            user=user,
            state=ReadyCheckEntryState.DROPPED,
        )
        self.outcome(
            user,
            event=self.event,
            outcome=Outcome.EXCUSED,
            source=OutcomeSource.STAFF,
            finalized=False,
            set_by=self.admin,
            reason="Had a power cut",
        )

        self._complete()

        row = self._row(user)
        self.assertEqual(row.outcome, Outcome.EXCUSED)
        self.assertEqual(row.source, OutcomeSource.STAFF)
        self.assertEqual(
            Event.objects.nocache().get(pk=self.event.pk).state, EventState.COMPLETED
        )
