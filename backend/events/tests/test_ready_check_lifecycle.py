from unittest import mock

from django.test import override_settings
from rest_framework.test import APIClient

from app.models import CustomUser
from events.completion import close_event
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
    SignupLedgerEntry,
)
from events.ready_check import (
    ConfirmResult,
    close_ready_check,
    confirm_ready,
    open_ready_check,
)
from events.ready_check_constants import (
    DROPPED_SIGNUP_MESSAGE,
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckOutcome,
    ReadyCheckPhase,
)
from events.services import (
    approve_signup,
    cancel_event,
    reinstate_signup,
    restart_event_tournament,
    staff_add_signup,
    unconfirm_signup,
)
from events.tests.base import EventTestCase

NOTIFY = "events.discord.dispatch.notify_signup_changed"
SERVICES_NOTIFY = "events.services.notify_signup_changed"
INTERNAL_TOKEN = "test-internal-token"


class LifecycleTestCase(EventTestCase):
    def setUp(self) -> None:
        patcher = mock.patch(SERVICES_NOTIFY)
        patcher.start()
        self.addCleanup(patcher.stop)
        dispatch = mock.patch(NOTIFY)
        dispatch.start()
        self.addCleanup(dispatch.stop)
        self.rc_event = self.make_event()
        self.helper = self.make_user()
        self.rc_event.helpers.add(self.helper)
        self.helper_actor = SignupActor(
            user=self.helper, role=ActorRole.STAFF, means=SignupMeans.WEB
        )
        self.admin_actor = SignupActor(
            user=self.admin, role=ActorRole.STAFF, means=SignupMeans.WEB
        )

    def _signup(self, status: str, *, user: CustomUser | None = None) -> EventSignup:
        return EventSignup.objects.create(
            event=self.rc_event, user=user or self.make_user(), status=status
        )

    def _open(self) -> ReadyCheck:
        with self.captureOnCommitCallbacks(execute=True):
            check = open_ready_check(self.rc_event, actor=self.admin_actor).check
        self.rc_event.refresh_from_db()
        return check

    def _set_phase(
        self, check: ReadyCheck, phase: str, outcome: str = ""
    ) -> ReadyCheck:
        ReadyCheck.objects.filter(pk=check.pk).update(phase=phase, outcome=outcome)
        check.refresh_from_db()
        return check

    def _rows(self, action: str) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                event=self.rc_event, action=action
            ).order_by("pk")
        )

    def _assert_staff_row(
        self, row: SignupLedgerEntry, user: CustomUser, check: ReadyCheck | None
    ) -> None:
        self.assertEqual(row.actor_user, user)
        self.assertEqual(row.actor_role, ActorRole.STAFF)
        self.assertEqual(row.means, SignupMeans.WEB)
        if check is not None:
            self.assertTrue(row.correlation_id.startswith(f"rc{check.pk}:"))


class LateEnrolmentTests(LifecycleTestCase):
    def _approve_rsvp(self, actor: SignupActor, user: CustomUser) -> None:
        check = self._open()
        rsvp = self._signup(SignupStatus.RSVP)
        approve_signup(rsvp, actor=actor)
        entry = check.entries.get(signup=rsvp)
        self.assertEqual(entry.state, ReadyCheckEntryState.PENDING)
        asked = SignupLedgerEntry.objects.get(
            action=SignupAction.READY_CHECK_ASKED, signup=rsvp
        )
        self._assert_staff_row(asked, user, check)

    def test_approve_during_open_check_enrols(self) -> None:
        self._approve_rsvp(self.admin_actor, self.admin)

    def test_approve_by_helper_attributes_helper(self) -> None:
        self._approve_rsvp(self.helper_actor, self.helper)

    def test_staff_add_during_open_check_enrols(self) -> None:
        check = self._open()
        user = self.make_user()
        signup = staff_add_signup(self.rc_event, user, actor=self.helper_actor)
        self.assertIn(signup.status, (SignupStatus.APPROVED, SignupStatus.CONFIRMED))
        entry = check.entries.get(signup=signup)
        self.assertEqual(entry.user, user)
        asked = SignupLedgerEntry.objects.get(
            action=SignupAction.READY_CHECK_ASKED, signup=signup
        )
        self._assert_staff_row(asked, self.helper, check)

    def test_staff_readd_after_cancel_relinks_entry(self) -> None:
        member = self._signup(SignupStatus.APPROVED)
        check = self._open()
        entry = check.entries.get(signup=member)
        member.status = SignupStatus.CANCELLED
        member.save(update_fields=["status"])
        readded = staff_add_signup(self.rc_event, member.user, actor=self.admin_actor)
        self.assertNotEqual(readded.pk, member.pk)
        entry.refresh_from_db()
        self.assertEqual(entry.signup_id, readded.pk)
        self.assertEqual(check.entries.filter(user=member.user).count(), 1)

    def test_approve_without_check_writes_no_entry(self) -> None:
        rsvp = self._signup(SignupStatus.RSVP)
        approve_signup(rsvp, actor=self.admin_actor)
        self.assertFalse(ReadyCheckEntry.objects.filter(signup=rsvp).exists())


class UnconfirmTests(LifecycleTestCase):
    def _confirmed_in_check(self) -> tuple[ReadyCheck, EventSignup]:
        signup = self._signup(SignupStatus.CONFIRMED)
        check = self._open()
        self.assertEqual(
            check.entries.get(signup=signup).state, ReadyCheckEntryState.CONFIRMED
        )
        return check, signup

    def _assert_reset(self, check: ReadyCheck, signup: EventSignup) -> None:
        entry = check.entries.get(signup=signup)
        self.assertEqual(entry.state, ReadyCheckEntryState.PENDING)
        self.assertEqual(entry.confirmed_via, "")
        self.assertIsNone(entry.confirmed_at)

    def test_open_check_resets_entry(self) -> None:
        check, signup = self._confirmed_in_check()
        unconfirm_signup(signup, actor=self.admin_actor)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)
        self._assert_reset(check, signup)
        rows = self._rows(SignupAction.UNCONFIRMED)
        self.assertEqual(len(rows), 1)
        self._assert_staff_row(rows[0], self.admin, check)

    def test_held_check_resets_entry(self) -> None:
        check, signup = self._confirmed_in_check()
        self._set_phase(check, ReadyCheckPhase.HELD)
        unconfirm_signup(signup, actor=self.admin_actor)
        self._assert_reset(check, signup)
        self.assertEqual(len(self._rows(SignupAction.UNCONFIRMED)), 1)

    def test_closed_check_resets_entry(self) -> None:
        check, signup = self._confirmed_in_check()
        self._set_phase(check, ReadyCheckPhase.CLOSED, ReadyCheckOutcome.STAFF_VERIFIED)
        unconfirm_signup(signup, actor=self.admin_actor)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)
        self._assert_reset(check, signup)
        self.assertEqual(len(self._rows(SignupAction.UNCONFIRMED)), 1)
        self.assertEqual(len(self._rows(SignupAction.UNCONFIRMED)), 1)

    def test_helper_actor_attributes_row(self) -> None:
        check, signup = self._confirmed_in_check()
        unconfirm_signup(signup, actor=self.helper_actor)
        self._assert_reset(check, signup)
        row = self._rows(SignupAction.UNCONFIRMED)[0]
        self._assert_staff_row(row, self.helper, check)
        self.assertEqual(row.subject_user, signup.user)
        self.assertTrue(row.on_behalf)

    def test_without_check_writes_row(self) -> None:
        signup = self._signup(SignupStatus.CONFIRMED)
        unconfirm_signup(signup, actor=self.admin_actor)
        rows = self._rows(SignupAction.UNCONFIRMED)
        self.assertEqual(len(rows), 1)
        self._assert_staff_row(rows[0], self.admin, None)


class ReinstateDroppedTests(LifecycleTestCase):
    def _dropped_in_check(self) -> tuple[ReadyCheck, EventSignup]:
        signup = self._signup(SignupStatus.APPROVED)
        check = self._open()
        EventSignup.objects.filter(pk=signup.pk).update(status=SignupStatus.DROPPED)
        check.entries.filter(signup=signup).update(state=ReadyCheckEntryState.DROPPED)
        signup.refresh_from_db()
        return check, signup

    def test_roll_call_staff_reinstates_to_approved_and_excuses_entry(self) -> None:
        check, signup = self._dropped_in_check()
        entries_before = check.entries.count()
        reinstate_signup(signup, for_staff_placement=True, actor=self.helper_actor)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)
        self.assertEqual(check.entries.count(), entries_before)
        self.assertEqual(
            check.entries.get(signup=signup).state, ReadyCheckEntryState.EXCUSED
        )
        rows = self._rows(SignupAction.REINSTATED)
        self.assertEqual(len(rows), 1)
        self._assert_staff_row(rows[0], self.helper, check)
        self.assertEqual(rows[0].before["status"], SignupStatus.DROPPED)
        self.assertEqual(rows[0].after["status"], SignupStatus.APPROVED)

    def test_roll_call_owner_refused(self) -> None:
        check, signup = self._dropped_in_check()
        owner = SignupActor(
            user=signup.user, role=ActorRole.MEMBER, means=SignupMeans.WEB
        )
        with self.assertRaisesMessage(ValueError, DROPPED_SIGNUP_MESSAGE):
            reinstate_signup(signup, for_staff_placement=False, actor=owner)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.DROPPED)
        self.assertEqual(
            check.entries.get(signup=signup).state, ReadyCheckEntryState.DROPPED
        )
        self.assertEqual(self._rows(SignupAction.REINSTATED), [])

    def test_signups_open_staff_gets_decided_status(self) -> None:
        signup = self._signup(SignupStatus.DROPPED)
        reinstate_signup(signup, for_staff_placement=True, actor=self.admin_actor)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)
        rows = self._rows(SignupAction.REINSTATED)
        self.assertEqual(len(rows), 1)
        self._assert_staff_row(rows[0], self.admin, None)

    def test_signups_open_owner_refused(self) -> None:
        signup = self._signup(SignupStatus.DROPPED)
        owner = SignupActor(
            user=signup.user, role=ActorRole.MEMBER, means=SignupMeans.WEB
        )
        with self.assertRaisesMessage(ValueError, DROPPED_SIGNUP_MESSAGE):
            reinstate_signup(signup, for_staff_placement=False, actor=owner)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.DROPPED)

    def test_cancelled_reinstate_writes_row(self) -> None:
        signup = self._signup(SignupStatus.CANCELLED)
        owner = SignupActor(
            user=signup.user, role=ActorRole.MEMBER, means=SignupMeans.WEB
        )
        reinstate_signup(signup, for_staff_placement=False, actor=owner)
        rows = self._rows(SignupAction.REINSTATED)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].actor_role, ActorRole.MEMBER)


class EventLifecycleTests(LifecycleTestCase):
    def _withdrawn_reason(self, check: ReadyCheck) -> str:
        transition = SignupLedgerEntry.objects.get(
            action=SignupAction.READY_CHECK_TRANSITION,
            correlation_id=f"rc{check.pk}:cancel",
        )
        return transition.reason

    def _open_with_pending(self) -> tuple[ReadyCheck, EventSignup]:
        pending = self._signup(SignupStatus.APPROVED)
        return self._open(), pending

    def test_cancel_event_cancels_check(self) -> None:
        check, _ = self._open_with_pending()
        cancel_event(self.rc_event, actor=self.helper)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        self.assertEqual(self._withdrawn_reason(check), "event_cancelled")
        row = SignupLedgerEntry.objects.get(
            action=SignupAction.READY_CHECK_TRANSITION,
            correlation_id=f"rc{check.pk}:cancel",
        )
        self._assert_staff_row(row, self.helper, check)

    def test_cancel_event_without_actor_is_system(self) -> None:
        check, _ = self._open_with_pending()
        cancel_event(self.rc_event, actor=None)
        row = SignupLedgerEntry.objects.get(
            action=SignupAction.READY_CHECK_TRANSITION,
            correlation_id=f"rc{check.pk}:cancel",
        )
        self.assertIsNone(row.actor_user)
        self.assertEqual(row.actor_role, ActorRole.SYSTEM)

    def test_restart_cancels_check(self) -> None:
        check, _ = self._open_with_pending()
        restart_event_tournament(self.rc_event, actor=self.admin)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        self.assertEqual(self._withdrawn_reason(check), "restarted")
        self.rc_event.refresh_from_db()
        self.assertEqual(self.rc_event.state, EventState.SIGNUPS_OPEN)

    def test_restart_after_completion_cancels_closed_check(self) -> None:
        check, _ = self._open_with_pending()
        self._set_phase(check, ReadyCheckPhase.CLOSED, ReadyCheckOutcome.STAFF_VERIFIED)
        close_event(
            self.rc_event,
            new_state=EventState.COMPLETED,
            source="admin",
            actor=self.admin,
        )
        restart_event_tournament(self.rc_event, actor=self.admin, can_reopen=True)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        self.assertEqual(check.outcome, ReadyCheckOutcome.STAFF_VERIFIED)

    def test_complete_endpoint_cancels_open_check(self) -> None:
        check, _ = self._open_with_pending()
        client = APIClient()
        client.force_authenticate(self.admin)
        resp = client.post(f"/api/events/{self.rc_event.pk}/complete/", format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        self.assertEqual(self._withdrawn_reason(check), "event_completed")
        row = SignupLedgerEntry.objects.get(
            action=SignupAction.READY_CHECK_TRANSITION,
            correlation_id=f"rc{check.pk}:cancel",
        )
        self._assert_staff_row(row, self.admin, check)

    @override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN)
    def test_auto_close_cancels_open_check(self) -> None:
        check, _ = self._open_with_pending()
        resp = APIClient().post(
            f"/api/internal/events/{self.rc_event.pk}/auto-close/",
            {},
            format="json",
            HTTP_X_INTERNAL_TOKEN=INTERNAL_TOKEN,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["state"], EventState.COMPLETED)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        self.assertEqual(self._withdrawn_reason(check), "event_completed")
        row = SignupLedgerEntry.objects.get(
            action=SignupAction.READY_CHECK_TRANSITION,
            correlation_id=f"rc{check.pk}:cancel",
        )
        self.assertEqual(row.actor_role, ActorRole.SYSTEM)

    def test_completion_keeps_closed_check(self) -> None:
        check, _ = self._open_with_pending()
        self._set_phase(check, ReadyCheckPhase.CLOSED, ReadyCheckOutcome.STAFF_VERIFIED)
        result = close_event(
            self.rc_event,
            new_state=EventState.COMPLETED,
            source="admin",
            actor=self.admin,
        )
        self.assertTrue(result.closed)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CLOSED)
        self.assertEqual(check.outcome, ReadyCheckOutcome.STAFF_VERIFIED)

    def test_nothing_changes_after_completion(self) -> None:
        check, pending = self._open_with_pending()
        close_event(
            self.rc_event,
            new_state=EventState.COMPLETED,
            source="admin",
            actor=self.admin,
        )
        rows_before = SignupLedgerEntry.objects.filter(event=self.rc_event).count()
        users_before = set(self.rc_event.tournament.users.values_list("pk", flat=True))
        member = SignupActor(
            user=pending.user, role=ActorRole.MEMBER, means=SignupMeans.WEB
        )
        self.assertEqual(
            confirm_ready(
                self.rc_event,
                pending.user,
                via=ReadyCheckConfirmVia.WEB,
                actor=member,
            ),
            ConfirmResult.CLOSED,
        )
        self.assertFalse(
            close_ready_check(self.rc_event, actor=self.admin_actor).changed
        )
        self.assertEqual(
            SignupLedgerEntry.objects.filter(event=self.rc_event).count(),
            rows_before,
        )
        self.assertEqual(
            set(self.rc_event.tournament.users.values_list("pk", flat=True)),
            users_before,
        )
        pending.refresh_from_db()
        self.assertEqual(pending.status, SignupStatus.APPROVED)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)

    def test_completion_from_in_progress_leaves_check(self) -> None:
        check, _ = self._open_with_pending()
        self._set_phase(check, ReadyCheckPhase.CLOSED, ReadyCheckOutcome.BINDING)
        Event.objects.nocache().filter(pk=self.rc_event.pk).update(
            state=EventState.IN_PROGRESS
        )
        close_event(
            self.rc_event,
            new_state=EventState.COMPLETED,
            source="admin",
            actor=self.admin,
        )
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CLOSED)
