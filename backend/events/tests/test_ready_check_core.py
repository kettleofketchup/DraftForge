import ast
from pathlib import Path

from django.db import transaction
from django.test import override_settings
from django.utils import timezone as tz

from app.models import CustomUser
from events import ready_check_core
from events.constants import (
    ActorRole,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
)
from events.ledger import SignupActor
from events.models import (
    Event,
    EventSignup,
    ReadyCheck,
    ReadyCheckEntry,
    RollCallMode,
    SignupLedgerEntry,
)
from events.ready_check_constants import (
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckOutcome,
    ReadyCheckPhase,
    ReadyCheckScope,
)
from events.ready_check_core import (
    cancel_ready_check,
    effective_mode,
    end_ready_check_on_completion,
    enrol_signup_if_live,
    live_ready_check,
    ready_check_population,
    ready_check_promotion_status,
)
from events.services import create_tournament_for_event
from events.tests.base import EventTestCase
from tournament.models import Tournament


class ReadyCheckCoreTestCase(EventTestCase):
    def setUp(self) -> None:
        self.rc_event = self.make_event(state=EventState.ROLL_CALL)
        self.helper = self.make_user()
        self.rc_event.helpers.add(self.helper)
        self.helper_actor = SignupActor(
            user=self.helper, role=ActorRole.STAFF, means=SignupMeans.WEB
        )

    def _signup(
        self, status: str, *, event: Event | None = None, user: CustomUser | None = None
    ) -> EventSignup:
        return EventSignup.objects.create(
            event=event or self.rc_event, user=user or self.make_user(), status=status
        )

    def _check(
        self,
        *,
        phase: str = ReadyCheckPhase.OPEN,
        scope: str = ReadyCheckScope.MAIN_ONLY,
        mode: str = RollCallMode.MANUAL,
        **extra: object,
    ) -> ReadyCheck:
        return ReadyCheck.objects.create(
            event=self.rc_event,
            phase=phase,
            settings_snapshot={"ready_check_scope": scope, "effective_mode": mode},
            **extra,
        )

    def _entry(
        self, check: ReadyCheck, signup: EventSignup, state: str
    ) -> ReadyCheckEntry:
        entry = ReadyCheckEntry.for_signup(check, signup)
        entry.state = state
        entry.save()
        return entry

    def _rows(self, action: str) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(event=self.rc_event, action=action)
        )


class EffectiveModeTests(ReadyCheckCoreTestCase):
    def test_manual_when_toggle_off(self) -> None:
        event = self.make_event(
            roll_call_enabled=False, roll_call_mode=RollCallMode.AUTOMATIC
        )
        with override_settings(READY_CHECK_AUTOMATIC_LIVE=True):
            self.assertEqual(effective_mode(event), RollCallMode.MANUAL)

    @override_settings(READY_CHECK_AUTOMATIC_LIVE=False)
    def test_manual_when_setting_false(self) -> None:
        event = self.make_event(
            roll_call_enabled=True, roll_call_mode=RollCallMode.AUTOMATIC
        )
        self.assertEqual(effective_mode(event), RollCallMode.MANUAL)

    @override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
    def test_automatic_only_with_toggle_mode_and_setting(self) -> None:
        event = self.make_event(
            roll_call_enabled=True, roll_call_mode=RollCallMode.AUTOMATIC
        )
        self.assertEqual(effective_mode(event), RollCallMode.AUTOMATIC)
        manual = self.make_event(
            roll_call_enabled=True, roll_call_mode=RollCallMode.MANUAL
        )
        self.assertEqual(effective_mode(manual), RollCallMode.MANUAL)


class PopulationTests(ReadyCheckCoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.by_status = {
            status: self._signup(status)
            for status in (
                SignupStatus.APPROVED,
                SignupStatus.CONFIRMED,
                SignupStatus.WAITLISTED,
                SignupStatus.TENTATIVE,
                SignupStatus.RSVP,
                SignupStatus.PENDING_APPROVAL,
                SignupStatus.CANCELLED,
                SignupStatus.DROPPED,
                SignupStatus.REJECTED,
            )
        }

    def _ids(self, scope: str) -> set[int]:
        return set(
            ready_check_population(self.rc_event, scope).values_list("pk", flat=True)
        )

    def test_main_only(self) -> None:
        self.assertEqual(
            self._ids(ReadyCheckScope.MAIN_ONLY),
            {
                self.by_status[SignupStatus.APPROVED].pk,
                self.by_status[SignupStatus.CONFIRMED].pk,
            },
        )

    def test_main_and_fill_adds_waitlisted(self) -> None:
        self.assertEqual(
            self._ids(ReadyCheckScope.MAIN_AND_FILL),
            {
                self.by_status[SignupStatus.APPROVED].pk,
                self.by_status[SignupStatus.CONFIRMED].pk,
                self.by_status[SignupStatus.WAITLISTED].pk,
            },
        )

    def test_other_event_signups_excluded(self) -> None:
        other = self.make_event()
        foreign = self._signup(SignupStatus.APPROVED, event=other)
        self.assertNotIn(foreign.pk, self._ids(ReadyCheckScope.MAIN_AND_FILL))


class LiveReadyCheckTests(ReadyCheckCoreTestCase):
    def test_none_without_check(self) -> None:
        self.assertIsNone(live_ready_check(self.rc_event))

    def test_ignores_cancelled_returns_closed(self) -> None:
        ReadyCheck.objects.create(event=self.rc_event, phase=ReadyCheckPhase.CANCELLED)
        self.assertIsNone(live_ready_check(self.rc_event))
        closed = self._check(phase=ReadyCheckPhase.CLOSED)
        self.assertEqual(live_ready_check(self.rc_event), closed)

    def test_lock_inside_atomic(self) -> None:
        check = self._check()
        with transaction.atomic():
            self.assertEqual(live_ready_check(self.rc_event, lock=True), check)


class CancelTests(ReadyCheckCoreTestCase):
    def test_cancel_with_helper_actor(self) -> None:
        check = self._check()
        pending = [self._signup(SignupStatus.APPROVED) for _ in range(2)]
        for signup in pending:
            self._entry(check, signup, ReadyCheckEntryState.PENDING)
        confirmed = self._signup(SignupStatus.CONFIRMED)
        self._entry(check, confirmed, ReadyCheckEntryState.CONFIRMED)

        with self.captureOnCommitCallbacks(execute=True):
            changed = cancel_ready_check(
                self.rc_event, actor=self.helper_actor, reason="reopened"
            )

        self.assertTrue(changed)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        self.assertIsNotNone(check.cancelled_at)
        withdrawn = self._rows(SignupAction.READY_CHECK_WITHDRAWN)
        self.assertEqual({row.signup_id for row in withdrawn}, {s.pk for s in pending})
        transitions = self._rows(SignupAction.READY_CHECK_TRANSITION)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].reason, "reopened")
        self.assertEqual(transitions[0].after["extra"]["step"], "cancel")
        rows = withdrawn + transitions
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row.actor_user_id, self.helper.pk)
            self.assertEqual(row.actor_role, ActorRole.STAFF)
            self.assertEqual(row.means, SignupMeans.WEB)
            self.assertNotEqual(row.actor_role, ActorRole.SYSTEM)
            self.assertEqual(row.correlation_id, f"rc{check.pk}:cancel")
        statuses = set(
            EventSignup.objects.nocache()
            .filter(pk__in=[s.pk for s in pending])
            .values_list("status", flat=True)
        )
        self.assertEqual(statuses, {SignupStatus.APPROVED})

    def test_second_cancel_is_noop(self) -> None:
        check = self._check()
        self._entry(check, self._signup(SignupStatus.APPROVED), "pending")
        self.assertTrue(
            cancel_ready_check(self.rc_event, actor=self.helper_actor, reason="x")
        )
        before = SignupLedgerEntry.objects.count()
        self.assertFalse(
            cancel_ready_check(self.rc_event, actor=self.helper_actor, reason="x")
        )
        self.assertEqual(SignupLedgerEntry.objects.count(), before)

    def test_closed_check_keeps_history_and_frees_constraint(self) -> None:
        closed_at = tz.now()
        check = self._check(
            phase=ReadyCheckPhase.CLOSED,
            outcome=ReadyCheckOutcome.BINDING,
            closed_at=closed_at,
        )
        self.assertTrue(
            cancel_ready_check(self.rc_event, actor=self.helper_actor, reason="x")
        )
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        self.assertEqual(check.outcome, ReadyCheckOutcome.BINDING)
        self.assertEqual(check.closed_at, closed_at)
        fresh = ReadyCheck.objects.create(event=self.rc_event)
        self.assertEqual(live_ready_check(self.rc_event), fresh)


class EnrolTests(ReadyCheckCoreTestCase):
    def _staff_actor(self) -> SignupActor:
        return SignupActor(user=self.admin, role=ActorRole.STAFF, means=SignupMeans.WEB)

    def test_enrols_approved_signup_on_open_check(self) -> None:
        check = self._check()
        signup = self._signup(SignupStatus.APPROVED)
        with transaction.atomic():
            entry = enrol_signup_if_live(signup, actor=self._staff_actor())
        assert entry is not None
        self.assertEqual(entry.ready_check_id, check.pk)
        self.assertEqual(entry.state, ReadyCheckEntryState.PENDING)
        self.assertEqual(entry.user_id, signup.user_id)
        asked = self._rows(SignupAction.READY_CHECK_ASKED)
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0].signup_id, signup.pk)
        self.assertEqual(asked[0].actor_user_id, self.admin.pk)
        self.assertEqual(asked[0].actor_role, ActorRole.STAFF)

    def test_closed_check_enrols_nobody(self) -> None:
        check = self._check(phase=ReadyCheckPhase.CLOSED)
        signup = self._signup(SignupStatus.APPROVED)
        with transaction.atomic():
            self.assertIsNone(enrol_signup_if_live(signup, actor=self._staff_actor()))
        self.assertFalse(check.entries.exists())

    def test_waitlisted_out_of_scope_under_main_only(self) -> None:
        check = self._check(scope=ReadyCheckScope.MAIN_ONLY)
        signup = self._signup(SignupStatus.WAITLISTED)
        with transaction.atomic():
            self.assertIsNone(enrol_signup_if_live(signup, actor=self._staff_actor()))
        self.assertFalse(check.entries.exists())

    def test_waitlisted_enrolled_under_main_and_fill(self) -> None:
        self._check(scope=ReadyCheckScope.MAIN_AND_FILL)
        signup = self._signup(SignupStatus.WAITLISTED)
        with transaction.atomic():
            entry = enrol_signup_if_live(signup, actor=self._staff_actor())
        assert entry is not None
        self.assertEqual(entry.state, ReadyCheckEntryState.PENDING)

    def test_late_enrolment_records_computed_waitlist_rank(self) -> None:
        self._check(scope=ReadyCheckScope.MAIN_AND_FILL)
        self._signup(SignupStatus.WAITLISTED)
        signup = self._signup(SignupStatus.WAITLISTED)
        EventSignup.objects.filter(pk=signup.pk).update(waitlist_position=40)
        signup = EventSignup.objects.nocache().get(pk=signup.pk)
        with transaction.atomic():
            enrol_signup_if_live(signup, actor=self._staff_actor())
        asked = self._rows(SignupAction.READY_CHECK_ASKED)
        self.assertEqual(asked[0].after["waitlist_position"], 2)

    def test_existing_confirmed_entry_confirms_approved_signup(self) -> None:
        create_tournament_for_event(self.rc_event)
        self.rc_event.refresh_from_db()
        check = self._check(scope=ReadyCheckScope.MAIN_AND_FILL)
        signup = self._signup(SignupStatus.WAITLISTED)
        entry = self._entry(check, signup, ReadyCheckEntryState.CONFIRMED)
        EventSignup.objects.filter(pk=signup.pk).update(status=SignupStatus.APPROVED)
        signup = EventSignup.objects.nocache().get(pk=signup.pk)

        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                result = enrol_signup_if_live(signup, actor=self._staff_actor())

        self.assertEqual(result, entry)
        signup = EventSignup.objects.nocache().get(pk=signup.pk)
        self.assertEqual(signup.status, SignupStatus.CONFIRMED)
        tournament = Tournament.objects.nocache().get(pk=self.rc_event.tournament_id)
        self.assertIn(
            signup.user_id, set(tournament.users.values_list("pk", flat=True))
        )
        self.assertFalse(self._rows(SignupAction.READY_CHECK_ASKED))
        confirmed_rows = self._rows(SignupAction.CONFIRMED)
        self.assertEqual(len(confirmed_rows), 1)
        self.assertEqual(confirmed_rows[0].correlation_id, f"rc{check.pk}:enrol")
        self.assertEqual(confirmed_rows[0].actor_user_id, self.admin.pk)

    def test_confirmed_signup_gets_confirmed_staff_entry(self) -> None:
        check = self._check(mode=RollCallMode.MANUAL)
        signup = self._signup(SignupStatus.CONFIRMED)
        with transaction.atomic():
            entry = enrol_signup_if_live(signup, actor=self._staff_actor())
        assert entry is not None
        entry.refresh_from_db()
        self.assertEqual(entry.ready_check_id, check.pk)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.STAFF)
        self.assertIsNotNone(entry.confirmed_at)
        asked = self._rows(SignupAction.READY_CHECK_ASKED)
        self.assertEqual([row.signup_id for row in asked], [signup.pk])

    def test_existing_dropped_entry_returned_unchanged(self) -> None:
        check = self._check()
        signup = self._signup(SignupStatus.APPROVED)
        entry = self._entry(check, signup, ReadyCheckEntryState.DROPPED)
        with transaction.atomic():
            result = enrol_signup_if_live(signup, actor=self._staff_actor())
        self.assertEqual(result, entry)
        entry.refresh_from_db()
        self.assertEqual(entry.state, ReadyCheckEntryState.DROPPED)
        signup = EventSignup.objects.nocache().get(pk=signup.pk)
        self.assertEqual(signup.status, SignupStatus.APPROVED)

    def test_no_check_returns_none(self) -> None:
        signup = self._signup(SignupStatus.APPROVED)
        with transaction.atomic():
            self.assertIsNone(enrol_signup_if_live(signup, actor=self._staff_actor()))


class PromotionStatusTests(ReadyCheckCoreTestCase):
    def test_no_live_check_returns_decided(self) -> None:
        signup = self._signup(SignupStatus.WAITLISTED)
        self.assertEqual(
            ready_check_promotion_status(self.rc_event, SignupStatus.CONFIRMED, signup),
            SignupStatus.CONFIRMED,
        )

    def test_confirmed_entry_promotes_to_confirmed(self) -> None:
        check = self._check(scope=ReadyCheckScope.MAIN_AND_FILL)
        signup = self._signup(SignupStatus.WAITLISTED)
        self._entry(check, signup, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(
            ready_check_promotion_status(self.rc_event, SignupStatus.APPROVED, signup),
            SignupStatus.CONFIRMED,
        )

    @override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
    def test_auto_confirm_downgraded_in_automatic_mode(self) -> None:
        self._check(mode=RollCallMode.AUTOMATIC)
        signup = self._signup(SignupStatus.WAITLISTED)
        self.assertEqual(
            ready_check_promotion_status(self.rc_event, SignupStatus.CONFIRMED, signup),
            SignupStatus.APPROVED,
        )

    def test_auto_confirm_kept_in_manual_mode(self) -> None:
        self._check(mode=RollCallMode.MANUAL)
        signup = self._signup(SignupStatus.WAITLISTED)
        self.assertEqual(
            ready_check_promotion_status(self.rc_event, SignupStatus.CONFIRMED, signup),
            SignupStatus.CONFIRMED,
        )

    @override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
    def test_event_not_in_roll_call_keeps_decided(self) -> None:
        self._check(phase=ReadyCheckPhase.CLOSED, mode=RollCallMode.AUTOMATIC)
        signup = self._signup(SignupStatus.WAITLISTED)
        Event.objects.filter(pk=self.rc_event.pk).update(state=EventState.IN_PROGRESS)
        self.rc_event.refresh_from_db()
        self.assertEqual(
            ready_check_promotion_status(self.rc_event, SignupStatus.CONFIRMED, signup),
            SignupStatus.CONFIRMED,
        )

    def test_other_decisions_unchanged(self) -> None:
        self._check()
        signup = self._signup(SignupStatus.WAITLISTED)
        for decided in (
            SignupStatus.APPROVED,
            SignupStatus.RSVP,
            SignupStatus.PENDING_APPROVAL,
        ):
            self.assertEqual(
                ready_check_promotion_status(self.rc_event, decided, signup), decided
            )


class CompletionTests(ReadyCheckCoreTestCase):
    def test_open_check_cancelled_with_event_completed(self) -> None:
        check = self._check()
        self._entry(check, self._signup(SignupStatus.APPROVED), "pending")
        with transaction.atomic():
            self.assertTrue(
                end_ready_check_on_completion(self.rc_event, actor=SignupActor.system())
            )
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        transition = self._rows(SignupAction.READY_CHECK_TRANSITION)
        self.assertEqual([row.reason for row in transition], ["event_completed"])
        withdrawn = self._rows(SignupAction.READY_CHECK_WITHDRAWN)
        self.assertEqual([row.reason for row in withdrawn], ["event_completed"])

    def test_closed_check_untouched(self) -> None:
        check = self._check(
            phase=ReadyCheckPhase.CLOSED, outcome=ReadyCheckOutcome.BINDING
        )
        with transaction.atomic():
            self.assertFalse(
                end_ready_check_on_completion(self.rc_event, actor=SignupActor.system())
            )
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CLOSED)
        self.assertFalse(SignupLedgerEntry.objects.filter(event=self.rc_event).exists())

    def test_no_check_returns_false(self) -> None:
        self.assertFalse(
            end_ready_check_on_completion(self.rc_event, actor=SignupActor.system())
        )


class CoreImportTests(EventTestCase):
    def test_core_imports_no_services(self) -> None:
        tree = ast.parse(Path(ready_check_core.__file__).read_text())
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
                modules.update(f"{node.module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        for forbidden in ("events.services", "events.ready_check"):
            self.assertNotIn(forbidden, modules)
