import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

from django.dispatch import Signal
from django.test import override_settings

from app.models import CustomUser, Team
from events import ready_check_signals
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
from events.ready_check import (
    CloseResult,
    ConfirmResult,
    OpenResult,
    cancel_ready_check,
    chase_unconfirmed,
    close_ready_check,
    confirm_ready,
    escalate_ready_check,
    open_ready_check,
    refused_confirm_message,
)
from events.ready_check_constants import (
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckLowCompletionAction,
    ReadyCheckOutcome,
    ReadyCheckPhase,
    ReadyCheckScope,
)
from events.services import (
    cancel_signup,
    create_tournament_for_event,
    demote_to_waitlist,
)
from events.tests.base import EventTestCase

NOTIFY = "events.discord.dispatch.notify_signup_changed"


class ReadyCheckServiceTestCase(EventTestCase):
    def setUp(self) -> None:
        self.rc_event = self.make_event()
        self.helper = self.make_user()
        self.rc_event.helpers.add(self.helper)
        self.staff_actor = SignupActor(
            user=self.helper, role=ActorRole.STAFF, means=SignupMeans.WEB
        )

    def _signup(
        self, status: str, *, event: Event | None = None, user: CustomUser | None = None
    ) -> EventSignup:
        return EventSignup.objects.create(
            event=event or self.rc_event, user=user or self.make_user(), status=status
        )

    def _rows(self, action: str, event: Event | None = None) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                event=event or self.rc_event, action=action
            ).order_by("pk")
        )

    def _open(self, event: Event | None = None) -> OpenResult:
        with self.captureOnCommitCallbacks(execute=True):
            return open_ready_check(event or self.rc_event, actor=self.staff_actor)

    @contextmanager
    def _listen(self, signal: Signal) -> Iterator[mock.Mock]:
        receiver = mock.Mock(return_value=None)
        signal.connect(receiver, weak=False)
        try:
            yield receiver
        finally:
            signal.disconnect(receiver)

    def _entry(self, check: ReadyCheck, signup: EventSignup) -> ReadyCheckEntry:
        return check.entries.get(signup=signup)


class OpenTests(ReadyCheckServiceTestCase):
    def test_manual_open_from_signups(self) -> None:
        confirmed = self._signup(SignupStatus.CONFIRMED)
        approved = self._signup(SignupStatus.APPROVED)
        with (
            mock.patch(NOTIFY) as notify,
            self._listen(ready_check_signals.ready_check_opened) as opened,
        ):
            result = self._open()
        self.rc_event.refresh_from_db()
        self.assertEqual(self.rc_event.state, EventState.ROLL_CALL)
        self.assertTrue(result.created)
        self.assertIsNotNone(result.roster)
        check = result.check
        self.assertEqual(check.phase, ReadyCheckPhase.OPEN)
        self.assertEqual(check.opened_by, self.helper)
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status, SignupStatus.CONFIRMED)
        c_entry = self._entry(check, confirmed)
        self.assertEqual(c_entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(c_entry.confirmed_via, ReadyCheckConfirmVia.STAFF)
        self.assertIsNotNone(c_entry.confirmed_at)
        self.assertEqual(
            self._entry(check, approved).state, ReadyCheckEntryState.PENDING
        )
        asked = self._rows(SignupAction.READY_CHECK_ASKED)
        self.assertEqual(len(asked), check.entries.count())
        self.assertTrue(all(r.correlation_id == f"rc{check.pk}:open" for r in asked))
        transitions = self._rows(SignupAction.READY_CHECK_TRANSITION)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].reason, "open")
        self.assertEqual(transitions[0].actor_user, self.helper)
        opened.assert_called_once()
        change = opened.call_args.kwargs["change"]
        self.assertEqual(change.user_ids, (approved.user_id,))
        self.assertEqual(change.actor_user_id, self.helper.pk)
        notify.assert_called_once()
        self.assertIn(confirmed.user, self.rc_event.tournament.users.all())
        self.assertNotIn(approved.user, self.rc_event.tournament.users.all())

    @override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
    def test_automatic_open_resets_confirmed(self) -> None:
        event = self.make_event(
            roll_call_enabled=True, roll_call_mode=RollCallMode.AUTOMATIC
        )
        confirmed = self._signup(SignupStatus.CONFIRMED, event=event)
        approved = self._signup(SignupStatus.APPROVED, event=event)
        check = self._open(event).check
        self.assertEqual(check.settings_snapshot["effective_mode"], "automatic")
        self.assertEqual(check.settings_snapshot["configured_mode"], "automatic")
        self.assertTrue(check.settings_snapshot["roll_call_enabled"])
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status, SignupStatus.APPROVED)
        self.assertEqual(
            set(check.entries.values_list("state", flat=True)),
            {ReadyCheckEntryState.PENDING},
        )
        self.assertEqual(check.entries.count(), 2)
        reset = self._rows(SignupAction.UNCONFIRMED, event)
        self.assertEqual(len(reset), 1)
        self.assertEqual(reset[0].signup, confirmed)
        self.assertEqual(reset[0].reason, "ready_check_reset")
        approved.refresh_from_db()
        self.assertEqual(approved.status, SignupStatus.APPROVED)

    @override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
    def test_toggle_off_snapshots_manual(self) -> None:
        event = self.make_event(
            roll_call_enabled=False, roll_call_mode=RollCallMode.AUTOMATIC
        )
        check = self._open(event).check
        self.assertEqual(check.settings_snapshot["effective_mode"], "manual")
        self.assertEqual(check.settings_snapshot["configured_mode"], "automatic")

    def test_main_and_fill_asks_waitlisted(self) -> None:
        event = self.make_event(ready_check_scope=ReadyCheckScope.MAIN_AND_FILL)
        waitlisted = self._signup(SignupStatus.WAITLISTED, event=event)
        tentative = self._signup(SignupStatus.TENTATIVE, event=event)
        rsvp = self._signup(SignupStatus.RSVP, event=event)
        check = self._open(event).check
        asked = set(check.entries.values_list("signup_id", flat=True))
        self.assertIn(waitlisted.pk, asked)
        self.assertNotIn(tentative.pk, asked)
        self.assertNotIn(rsvp.pk, asked)
        waitlisted.refresh_from_db()
        self.assertEqual(waitlisted.status, SignupStatus.WAITLISTED)

    def test_main_only_skips_waitlisted(self) -> None:
        waitlisted = self._signup(SignupStatus.WAITLISTED)
        tentative = self._signup(SignupStatus.TENTATIVE)
        check = self._open().check
        self.assertFalse(
            check.entries.filter(signup__in=[waitlisted, tentative]).exists()
        )

    def test_default_preset_snapshot(self) -> None:
        check = self._open().check
        self.assertEqual(check.settings_snapshot["ready_check_min_completion_pct"], 70)
        self.assertEqual(
            check.settings_snapshot["ready_check_low_completion_action"],
            "non_binding",
        )
        self.assertEqual(check.settings_snapshot["ready_check_scope"], "main_only")
        self.assertEqual(check.settings_snapshot["effective_mode"], "manual")

    def test_idempotent_on_roll_call(self) -> None:
        self._signup(SignupStatus.APPROVED)
        first = self._open()
        entries = ReadyCheckEntry.objects.count()
        rows = SignupLedgerEntry.objects.count()
        second = self._open()
        self.assertFalse(second.created)
        self.assertEqual(second.check.pk, first.check.pk)
        self.assertEqual(ReadyCheckEntry.objects.count(), entries)
        self.assertEqual(SignupLedgerEntry.objects.count(), rows)

    def test_refuses_upcoming(self) -> None:
        event = self.make_event(state=EventState.UPCOMING)
        with self.assertRaises(ValueError):
            open_ready_check(event, actor=self.staff_actor)
        self.assertFalse(ReadyCheck.objects.filter(event=event).exists())

    def test_refuses_in_progress(self) -> None:
        event = self.make_event(state=EventState.IN_PROGRESS)
        with self.assertRaisesMessage(ValueError, "The tournament is already running."):
            open_ready_check(event, actor=self.staff_actor)

    def test_refuses_when_teams_made(self) -> None:
        tournament = create_tournament_for_event(self.rc_event)
        Team.objects.create(
            tournament=tournament, name="Owls", captain=self.make_user()
        )
        with self.assertRaisesMessage(
            ValueError, "Teams are already made for this event."
        ):
            open_ready_check(self.rc_event, actor=self.staff_actor)
        self.rc_event.refresh_from_db()
        self.assertEqual(self.rc_event.state, EventState.SIGNUPS_OPEN)

    def test_refuses_when_tournament_started(self) -> None:
        tournament = create_tournament_for_event(self.rc_event)
        tournament.state = "in_progress"
        tournament.save(update_fields=["state"])
        with self.assertRaisesMessage(
            ValueError, "Teams are already made for this event."
        ):
            open_ready_check(self.rc_event, actor=self.staff_actor)

    def test_roll_call_without_check_opens_without_transition(self) -> None:
        event = self.make_event(state=EventState.ROLL_CALL)
        approved = self._signup(SignupStatus.APPROVED, event=event)
        with mock.patch(NOTIFY) as notify:
            result = self._open(event)
        self.assertTrue(result.created)
        self.assertTrue(result.check.entries.filter(signup=approved).exists())
        event.refresh_from_db()
        self.assertEqual(event.state, EventState.ROLL_CALL)
        notify.assert_called_once()
        self.assertEqual(len(self._rows(SignupAction.READY_CHECK_TRANSITION, event)), 1)

    def test_stale_check_cancelled_and_reopened(self) -> None:
        stale = ReadyCheck.objects.create(
            event=self.rc_event,
            settings_snapshot={
                "ready_check_scope": "main_only",
                "effective_mode": "manual",
            },
        )
        result = self._open()
        stale.refresh_from_db()
        self.assertEqual(stale.phase, ReadyCheckPhase.CANCELLED)
        self.assertTrue(result.created)
        self.assertNotEqual(result.check.pk, stale.pk)
        cancel_rows = [
            r
            for r in self._rows(SignupAction.READY_CHECK_TRANSITION)
            if r.after["extra"]["step"] == "cancel"
        ]
        self.assertEqual([r.reason for r in cancel_rows], ["stale_check"])

    def test_reopen_after_cancel_creates_new_check(self) -> None:
        first = self._open().check
        with self.captureOnCommitCallbacks(execute=True):
            cancel_ready_check(self.rc_event, actor=self.staff_actor, reason="test")
        second = self._open()
        self.assertTrue(second.created)
        self.assertNotEqual(second.check.pk, first.pk)


class ConfirmTests(ReadyCheckServiceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.member = self.make_user()
        self.signup = self._signup(SignupStatus.APPROVED, user=self.member)
        self.member_actor = SignupActor(
            user=self.member, role=ActorRole.MEMBER, means=SignupMeans.WEB
        )

    def _confirm(
        self,
        user: CustomUser | None = None,
        *,
        via: str = ReadyCheckConfirmVia.WEB,
        actor: SignupActor | None = None,
        event: Event | None = None,
    ) -> ConfirmResult:
        with self.captureOnCommitCallbacks(execute=True):
            return confirm_ready(
                event or self.rc_event,
                user or self.member,
                via=via,
                actor=actor or self.member_actor,
            )

    def test_member_confirms_self(self) -> None:
        check = self._open().check
        before = check.last_progress_at
        with self._listen(ready_check_signals.ready_check_member_confirmed) as sig:
            result = self._confirm()
        self.assertEqual(result, ConfirmResult.CONFIRMED)
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, SignupStatus.CONFIRMED)
        entry = self._entry(check, self.signup)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.WEB)
        self.rc_event.refresh_from_db()
        self.assertIn(self.member, self.rc_event.tournament.users.all())
        rows = self._rows(SignupAction.CONFIRMED)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].actor_role, ActorRole.MEMBER)
        self.assertFalse(rows[0].on_behalf)
        self.assertEqual(rows[0].correlation_id, f"rc{check.pk}:confirm")
        check.refresh_from_db()
        self.assertGreater(check.last_progress_at, before)
        sig.assert_called_once()
        self.assertEqual(sig.call_args.kwargs["change"].user_ids, (self.member.pk,))

    def test_staff_confirms_on_behalf(self) -> None:
        check = self._open().check
        result = self._confirm(via=ReadyCheckConfirmVia.STAFF, actor=self.staff_actor)
        self.assertEqual(result, ConfirmResult.CONFIRMED)
        entry = self._entry(check, self.signup)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.STAFF)
        rows = self._rows(SignupAction.CONFIRMED)
        self.assertEqual(rows[0].actor_role, ActorRole.STAFF)
        self.assertTrue(rows[0].on_behalf)

    def test_second_confirm_is_already_confirmed(self) -> None:
        self._open()
        self._confirm()
        self.assertEqual(self._confirm(), ConfirmResult.ALREADY_CONFIRMED)
        self.assertEqual(len(self._rows(SignupAction.CONFIRMED)), 1)

    def test_fill_member_keeps_waitlisted(self) -> None:
        event = self.make_event(ready_check_scope=ReadyCheckScope.MAIN_AND_FILL)
        fill = self._signup(SignupStatus.WAITLISTED, event=event, user=self.member)
        check = self._open(event).check
        self.assertEqual(self._confirm(event=event), ConfirmResult.CONFIRMED)
        fill.refresh_from_db()
        self.assertEqual(fill.status, SignupStatus.WAITLISTED)
        self.assertEqual(self._entry(check, fill).state, ReadyCheckEntryState.CONFIRMED)

    def test_no_entry_is_not_in_check(self) -> None:
        self._open()
        self.assertEqual(self._confirm(self.make_user()), ConfirmResult.NOT_IN_CHECK)

    def test_no_check_is_not_in_check(self) -> None:
        event = self.make_event(state=EventState.ROLL_CALL)
        self.assertEqual(self._confirm(event=event), ConfirmResult.NOT_IN_CHECK)

    def test_cancelled_signup_is_not_in_check(self) -> None:
        check = self._open().check
        EventSignup.objects.filter(pk=self.signup.pk).update(
            status=SignupStatus.CANCELLED
        )
        self.assertEqual(self._confirm(), ConfirmResult.NOT_IN_CHECK)
        self.assertEqual(
            self._entry(check, self.signup).state, ReadyCheckEntryState.PENDING
        )

    def test_event_not_in_roll_call_is_closed(self) -> None:
        self._open()
        Event.objects.filter(pk=self.rc_event.pk).update(state=EventState.IN_PROGRESS)
        self.assertEqual(self._confirm(), ConfirmResult.CLOSED)

    def test_dropped_entry_is_closed(self) -> None:
        check = self._open().check
        ReadyCheckEntry.objects.filter(signup=self.signup).update(
            state=ReadyCheckEntryState.DROPPED
        )
        EventSignup.objects.filter(pk=self.signup.pk).update(
            status=SignupStatus.DROPPED
        )
        self.assertEqual(self._confirm(), ConfirmResult.CLOSED)
        self.assertEqual(
            self._entry(check, self.signup).state, ReadyCheckEntryState.DROPPED
        )

    def test_held_refuses_member_but_not_staff(self) -> None:
        check = self._open().check
        ReadyCheck.objects.filter(pk=check.pk).update(phase=ReadyCheckPhase.HELD)
        self.assertEqual(self._confirm(), ConfirmResult.CLOSED)
        self.assertEqual(
            self._entry(check, self.signup).state, ReadyCheckEntryState.PENDING
        )
        self.assertEqual(
            self._confirm(via=ReadyCheckConfirmVia.STAFF, actor=self.staff_actor),
            ConfirmResult.CONFIRMED,
        )
        self.assertEqual(
            self._entry(check, self.signup).state, ReadyCheckEntryState.CONFIRMED
        )

    def test_confirmed_entry_on_closed_check_is_already_confirmed(self) -> None:
        check = self._open().check
        self._confirm()
        ReadyCheck.objects.filter(pk=check.pk).update(phase=ReadyCheckPhase.CLOSED)
        self.assertEqual(self._confirm(), ConfirmResult.ALREADY_CONFIRMED)

    def test_pending_on_closed_check_is_closed(self) -> None:
        check = self._open().check
        ReadyCheck.objects.filter(pk=check.pk).update(phase=ReadyCheckPhase.CLOSED)
        self.assertEqual(
            self._confirm(via=ReadyCheckConfirmVia.STAFF, actor=self.staff_actor),
            ConfirmResult.CLOSED,
        )

    def test_repairs_confirmed_entry_with_approved_signup(self) -> None:
        check = self._open().check
        ReadyCheckEntry.objects.filter(signup=self.signup).update(
            state=ReadyCheckEntryState.CONFIRMED,
            confirmed_via=ReadyCheckConfirmVia.STAFF,
        )
        self.assertEqual(self._confirm(), ConfirmResult.ALREADY_CONFIRMED)
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, SignupStatus.CONFIRMED)
        self.rc_event.refresh_from_db()
        self.assertIn(self.member, self.rc_event.tournament.users.all())
        self.assertEqual(len(self._rows(SignupAction.CONFIRMED)), 1)
        self.assertTrue(check.entries.filter(signup=self.signup).exists())


class RefusedMessageTests(ReadyCheckServiceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.host = self.make_user()
        self.host.nickname = "Hosty"
        self.host.save()

    def test_names_host_nickname(self) -> None:
        event = self.make_event(name="Friday Inhouse", host=self.host)
        self.assertEqual(
            refused_confirm_message(event),
            "The ready check for Friday Inhouse has closed. "
            "Contact the host, Hosty, to be added back.",
        )

    def test_falls_back_to_username(self) -> None:
        host = self.make_user()
        host.nickname = ""
        host.save()
        event = self.make_event(name="Friday Inhouse", host=host)
        self.assertEqual(
            refused_confirm_message(event),
            "The ready check for Friday Inhouse has closed. "
            f"Contact the host, {host.username}, to be added back.",
        )

    def test_no_host(self) -> None:
        event = self.make_event(name="Friday Inhouse")
        self.assertEqual(
            refused_confirm_message(event),
            "The ready check for Friday Inhouse has closed. "
            "Contact the event staff to be added back.",
        )

    def test_held(self) -> None:
        event = self.make_event(name="Friday Inhouse", host=self.host)
        self.assertEqual(
            refused_confirm_message(event, held=True),
            "The ready check for Friday Inhouse is waiting on staff. "
            "Contact the host, Hosty, to be added back.",
        )


AUTO = RollCallMode.AUTOMATIC
MANUAL = RollCallMode.MANUAL
NON_BINDING = ReadyCheckLowCompletionAction.NON_BINDING
HOLD = ReadyCheckLowCompletionAction.HOLD_FOR_STAFF
DROP_ANYWAY = ReadyCheckLowCompletionAction.DROP_ANYWAY


@override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
class LifecycleTestCase(ReadyCheckServiceTestCase):
    def _member_actor(self, user: CustomUser) -> SignupActor:
        return SignupActor(user=user, role=ActorRole.MEMBER, means=SignupMeans.WEB)

    def _confirm_member(
        self, signup: EventSignup, *, actor: SignupActor | None = None
    ) -> ConfirmResult:
        via = ReadyCheckConfirmVia.STAFF if actor else ReadyCheckConfirmVia.WEB
        with self.captureOnCommitCallbacks(execute=True):
            return confirm_ready(
                signup.event,
                signup.user,
                via=via,
                actor=actor or self._member_actor(signup.user),
            )

    def _setup(
        self,
        mode: str,
        confirmed: int,
        total: int,
        action: str = NON_BINDING,
        min_pct: int = 70,
        **event_fields: object,
    ) -> tuple[Event, list[EventSignup]]:
        event = self.make_event(
            roll_call_enabled=True,
            roll_call_mode=mode,
            ready_check_low_completion_action=action,
            ready_check_min_completion_pct=min_pct,
            **event_fields,
        )
        event.helpers.add(self.helper)
        signups = [
            self._signup(SignupStatus.APPROVED, event=event) for _ in range(total)
        ]
        self._open(event)
        for signup in signups[:confirmed]:
            self.assertEqual(self._confirm_member(signup), ConfirmResult.CONFIRMED)
        return event, signups

    def _close(self, event: Event) -> CloseResult:
        with self.captureOnCommitCallbacks(execute=True):
            return close_ready_check(event, actor=self.staff_actor)

    def _escalate(self, event: Event) -> list[ReadyCheckEntry]:
        with self.captureOnCommitCallbacks(execute=True):
            return escalate_ready_check(event, actor=self.staff_actor)

    def _chase(self, event: Event) -> list[ReadyCheckEntry]:
        with self.captureOnCommitCallbacks(execute=True):
            return chase_unconfirmed(event, actor=self.staff_actor)

    def _dropped(self, event: Event) -> list[EventSignup]:
        return list(
            EventSignup.objects.nocache().filter(
                event=event, status=SignupStatus.DROPPED
            )
        )


class EscalateChaseTests(LifecycleTestCase):
    def test_escalate_and_chase_require_actor(self) -> None:
        for fn in (escalate_ready_check, chase_unconfirmed):
            with self.subTest(fn=fn.__name__):
                param = inspect.signature(fn).parameters["actor"]
                self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(param.default, inspect.Parameter.empty)

    def test_escalate_returns_pending_and_writes_rows(self) -> None:
        event, signups = self._setup(MANUAL, 1, 3)
        with self._listen(ready_check_signals.ready_check_escalated) as sig:
            entries = self._escalate(event)
        check = ReadyCheck.objects.get(event=event)
        self.assertEqual(check.phase, ReadyCheckPhase.ESCALATED)
        self.assertIsNotNone(check.escalated_at)
        self.assertEqual({e.signup_id for e in entries}, {signups[1].pk, signups[2].pk})
        nudged = self._rows(SignupAction.READY_CHECK_NUDGED, event)
        self.assertEqual(len(nudged), 2)
        self.assertTrue(all(r.reason == "escalated" for r in nudged))
        self.assertTrue(
            all(r.correlation_id == f"rc{check.pk}:escalate" for r in nudged)
        )
        steps = [
            r.after["extra"]["step"]
            for r in self._rows(SignupAction.READY_CHECK_TRANSITION, event)
        ]
        self.assertEqual(steps.count("escalate"), 1)
        sig.assert_called_once()

    def test_escalate_twice_is_noop(self) -> None:
        event, _ = self._setup(MANUAL, 0, 2)
        self._escalate(event)
        rows = SignupLedgerEntry.objects.count()
        self.assertEqual(self._escalate(event), [])
        self.assertEqual(SignupLedgerEntry.objects.count(), rows)

    def test_escalate_with_nobody_pending_writes_transition(self) -> None:
        event, _ = self._setup(MANUAL, 2, 2)
        self.assertEqual(self._escalate(event), [])
        self.assertEqual(
            ReadyCheck.objects.get(event=event).phase, ReadyCheckPhase.ESCALATED
        )
        steps = [
            r.after["extra"]["step"]
            for r in self._rows(SignupAction.READY_CHECK_TRANSITION, event)
        ]
        self.assertEqual(steps.count("escalate"), 1)
        self.assertEqual(self._rows(SignupAction.READY_CHECK_NUDGED, event), [])

    def test_escalate_outside_roll_call_is_noop(self) -> None:
        event, _ = self._setup(MANUAL, 0, 2)
        Event.objects.filter(pk=event.pk).update(state=EventState.IN_PROGRESS)
        self.assertEqual(self._escalate(event), [])
        self.assertEqual(
            ReadyCheck.objects.get(event=event).phase, ReadyCheckPhase.OPEN
        )

    def test_escalate_signal_fires_once_with_pending_users(self) -> None:
        event, signups = self._setup(MANUAL, 2, 4)
        with self._listen(ready_check_signals.ready_check_escalated) as sig:
            self._escalate(event)
            self._escalate(event)
        self.assertEqual(sig.call_count, 1)
        self.assertEqual(
            set(sig.call_args.kwargs["change"].user_ids),
            {signups[2].user_id, signups[3].user_id},
        )

    def test_chase_sets_chased_at_once(self) -> None:
        event, signups = self._setup(MANUAL, 1, 2)
        entries = self._chase(event)
        check = ReadyCheck.objects.get(event=event)
        self.assertIsNotNone(check.chased_at)
        self.assertEqual(check.phase, ReadyCheckPhase.OPEN)
        self.assertEqual([e.signup_id for e in entries], [signups[1].pk])
        nudged = self._rows(SignupAction.READY_CHECK_NUDGED, event)
        self.assertEqual([r.reason for r in nudged], ["chase"])
        self.assertEqual(nudged[0].correlation_id, f"rc{check.pk}:chase")
        chased_at = check.chased_at
        self.assertEqual(self._chase(event), [])
        check.refresh_from_db()
        self.assertEqual(check.chased_at, chased_at)
        self.assertEqual(len(self._rows(SignupAction.READY_CHECK_NUDGED, event)), 1)

    def test_chase_works_after_escalation(self) -> None:
        event, _ = self._setup(MANUAL, 0, 2)
        self._escalate(event)
        self.assertEqual(len(self._chase(event)), 2)

    def test_chase_refused_on_held_or_closed(self) -> None:
        for phase in (ReadyCheckPhase.HELD, ReadyCheckPhase.CLOSED):
            with self.subTest(phase=phase):
                event, _ = self._setup(MANUAL, 0, 2)
                ReadyCheck.objects.filter(event=event).update(phase=phase)
                self.assertEqual(self._chase(event), [])
                self.assertIsNone(ReadyCheck.objects.get(event=event).chased_at)

    def test_chase_signal_fires_once_with_exactly_pending_users(self) -> None:
        event, signups = self._setup(MANUAL, 2, 4)
        with self._listen(ready_check_signals.ready_check_chase_due) as sig:
            self._chase(event)
            self._chase(event)
        self.assertEqual(sig.call_count, 1)
        self.assertEqual(
            set(sig.call_args.kwargs["change"].user_ids),
            {signups[2].user_id, signups[3].user_id},
        )


class CloseTests(LifecycleTestCase):
    MATRIX: tuple[tuple[str, int, int, str, str, str, int], ...] = (
        (MANUAL, 7, 10, NON_BINDING, "closed", "staff_verified", 0),
        (MANUAL, 7, 10, HOLD, "closed", "staff_verified", 0),
        (MANUAL, 7, 10, DROP_ANYWAY, "closed", "staff_verified", 0),
        (MANUAL, 6, 10, NON_BINDING, "closed", "staff_verified", 0),
        (MANUAL, 6, 10, HOLD, "closed", "staff_verified", 0),
        (MANUAL, 6, 10, DROP_ANYWAY, "closed", "staff_verified", 0),
        (MANUAL, 0, 0, NON_BINDING, "closed", "staff_verified", 0),
        (MANUAL, 0, 0, HOLD, "closed", "staff_verified", 0),
        (MANUAL, 0, 0, DROP_ANYWAY, "closed", "staff_verified", 0),
        (AUTO, 7, 10, NON_BINDING, "closed", "binding", 3),
        (AUTO, 7, 10, HOLD, "closed", "binding", 3),
        (AUTO, 7, 10, DROP_ANYWAY, "closed", "binding", 3),
        (AUTO, 6, 10, NON_BINDING, "closed", "non_binding", 0),
        (AUTO, 6, 10, HOLD, "held", "", 0),
        (AUTO, 6, 10, DROP_ANYWAY, "closed", "binding", 4),
        (AUTO, 0, 0, NON_BINDING, "closed", "binding", 0),
        (AUTO, 0, 0, HOLD, "closed", "binding", 0),
        (AUTO, 0, 0, DROP_ANYWAY, "closed", "binding", 0),
    )

    def test_close_matrix(self) -> None:
        for mode, confirmed, total, action, phase, outcome, dropped in self.MATRIX:
            with self.subTest(mode=mode, turnout=f"{confirmed}/{total}", action=action):
                event, _ = self._setup(mode, confirmed, total, action)
                result = self._close(event)
                self.assertTrue(result.changed)
                assert result.check is not None
                self.assertEqual(result.check.phase, phase)
                self.assertEqual(result.check.outcome, outcome)
                self.assertEqual(len(result.dropped_user_ids), dropped)
                self.assertEqual(len(self._dropped(event)), dropped)
                if total == 0:
                    self.assertEqual(result.check.completion_pct, 100)

    def test_binding_close_keeps_confirmed_signup_with_pending_entry(self) -> None:
        event, signups = self._setup(AUTO, 7, 10)
        mismatched = signups[9]
        EventSignup.objects.filter(pk=mismatched.pk).update(
            status=SignupStatus.CONFIRMED
        )
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.BINDING)
        self.assertEqual(len(result.dropped_user_ids), 2)
        self.assertNotIn(mismatched.user_id, result.dropped_user_ids)
        mismatched.refresh_from_db()
        self.assertEqual(mismatched.status, SignupStatus.CONFIRMED)
        kept = self._rows(SignupAction.READY_CHECK_KEPT, event)
        self.assertEqual([r.signup_id for r in kept], [mismatched.pk])
        self.assertEqual(kept[0].reason, "signup_confirmed")
        self.assertEqual(kept[0].correlation_id, f"rc{result.check.pk}:close")

    def test_manual_below_min_hold_for_staff_closes_staff_verified(self) -> None:
        event, _ = self._setup(MANUAL, 6, 10, HOLD)
        check = self._close(event).check
        assert check is not None
        self.assertEqual(check.phase, ReadyCheckPhase.CLOSED)
        self.assertEqual(check.outcome, ReadyCheckOutcome.STAFF_VERIFIED)
        self.assertEqual(self._rows(SignupAction.READY_CHECK_HELD, event), [])

    def test_manual_below_min_drop_anyway_drops_nobody(self) -> None:
        event, signups = self._setup(MANUAL, 6, 10, DROP_ANYWAY)
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.STAFF_VERIFIED)
        self.assertEqual(self._dropped(event), [])
        pending = result.check.entries.filter(state=ReadyCheckEntryState.PENDING)
        self.assertEqual(pending.count(), 4)
        kept = self._rows(SignupAction.READY_CHECK_KEPT, event)
        self.assertEqual(len(kept), 4)
        self.assertTrue(all(r.reason == "staff_verified" for r in kept))
        for signup in signups[6:]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, SignupStatus.APPROVED)

    def test_manual_zero_members_closes_staff_verified(self) -> None:
        event, _ = self._setup(MANUAL, 0, 0)
        check = self._close(event).check
        assert check is not None
        self.assertEqual(check.outcome, ReadyCheckOutcome.STAFF_VERIFIED)
        self.assertEqual(check.completion_pct, 100)

    def test_automatic_above_min_hold_for_staff_is_binding_not_held(self) -> None:
        event, _ = self._setup(AUTO, 7, 10, HOLD)
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.phase, ReadyCheckPhase.CLOSED)
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.BINDING)
        self.assertEqual(result.check.completion_pct, 70)
        self.assertEqual(len(result.dropped_user_ids), 3)

    def test_automatic_above_min_drop_anyway_is_binding(self) -> None:
        event, _ = self._setup(AUTO, 8, 10, DROP_ANYWAY)
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.BINDING)
        self.assertEqual(len(result.dropped_user_ids), 2)

    def test_automatic_below_min_non_binding_keeps_everyone(self) -> None:
        event, _ = self._setup(AUTO, 6, 10, NON_BINDING)
        with self._listen(ready_check_signals.ready_check_went_non_binding) as sig:
            result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.NON_BINDING)
        self.assertEqual(result.check.completion_pct, 60)
        self.assertEqual(self._dropped(event), [])
        kept = self._rows(SignupAction.READY_CHECK_KEPT, event)
        self.assertEqual(len(kept), 4)
        self.assertTrue(all(r.reason == "non_binding" for r in kept))
        sig.assert_called_once()
        self.assertEqual(len(sig.call_args.kwargs["change"].user_ids), 4)

    def test_automatic_below_min_hold_for_staff_holds(self) -> None:
        event, _ = self._setup(AUTO, 6, 10, HOLD)
        with (
            self._listen(ready_check_signals.ready_check_held) as held_sig,
            self._listen(ready_check_signals.ready_check_closed) as closed_sig,
        ):
            result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.phase, ReadyCheckPhase.HELD)
        self.assertEqual(result.check.outcome, "")
        self.assertIsNone(result.check.closed_at)
        self.assertEqual(self._dropped(event), [])
        held = self._rows(SignupAction.READY_CHECK_HELD, event)
        self.assertEqual(len(held), 4)
        held_sig.assert_called_once()
        closed_sig.assert_not_called()
        steps = [
            r.after["extra"]["step"]
            for r in self._rows(SignupAction.READY_CHECK_TRANSITION, event)
        ]
        self.assertIn("hold", steps)
        self.assertNotIn("close", steps)

    def test_automatic_below_min_drop_anyway_drops_pending(self) -> None:
        event, _ = self._setup(AUTO, 6, 10, DROP_ANYWAY)
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.BINDING)
        self.assertEqual(len(self._dropped(event)), 4)

    def test_automatic_zero_members_is_binding(self) -> None:
        event, _ = self._setup(AUTO, 0, 0)
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.BINDING)
        self.assertEqual(result.check.completion_pct, 100)
        steps = [
            r.after["extra"]["step"]
            for r in self._rows(SignupAction.READY_CHECK_TRANSITION, event)
        ]
        self.assertEqual(steps, ["open", "close"])

    def test_default_preset_below_70_is_non_binding(self) -> None:
        event = self.make_event(roll_call_enabled=True, roll_call_mode=AUTO)
        signups = [self._signup(SignupStatus.APPROVED, event=event) for _ in range(10)]
        self._open(event)
        for signup in signups[:6]:
            self._confirm_member(signup)
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.NON_BINDING)
        self.assertEqual(self._dropped(event), [])

    def test_drop_effects(self) -> None:
        event, signups = self._setup(AUTO, 7, 10)
        with self._listen(ready_check_signals.ready_check_member_dropped) as sig:
            result = self._close(event)
        assert result.check is not None
        event.refresh_from_db()
        roster = set(event.tournament.users.values_list("pk", flat=True))
        for signup in signups[7:]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, SignupStatus.DROPPED)
            self.assertIsNone(signup.waitlist_position)
            entry = self._entry(result.check, signup)
            self.assertEqual(entry.state, ReadyCheckEntryState.DROPPED)
            self.assertIsNotNone(entry.dropped_at)
            self.assertNotIn(signup.user_id, roster)
        for signup in signups[:7]:
            self.assertIn(signup.user_id, roster)
        dropped_rows = self._rows(SignupAction.DROPPED, event)
        self.assertEqual(len(dropped_rows), 3)
        for row in dropped_rows:
            self.assertEqual(row.reason, "ready_check_unconfirmed")
            self.assertEqual(row.actor_user, self.helper)
            self.assertEqual(row.actor_role, ActorRole.STAFF)
            self.assertEqual(row.correlation_id, f"rc{result.check.pk}:close")
        sig.assert_called_once()
        self.assertEqual(
            set(sig.call_args.kwargs["change"].user_ids),
            {s.user_id for s in signups[7:]},
        )
        self.assertEqual(set(result.dropped_user_ids), {s.user_id for s in signups[7:]})

    def test_confirmed_signup_with_pending_entry_is_never_dropped(self) -> None:
        event, signups = self._setup(AUTO, 7, 10)
        odd = signups[9]
        EventSignup.objects.filter(pk=odd.pk).update(status=SignupStatus.CONFIRMED)
        result = self._close(event)
        odd.refresh_from_db()
        self.assertEqual(odd.status, SignupStatus.CONFIRMED)
        self.assertNotIn(odd.user_id, result.dropped_user_ids)
        self.assertEqual(len(result.dropped_user_ids), 2)

    def test_idempotent(self) -> None:
        event, _ = self._setup(AUTO, 7, 10)
        first = self._close(event)
        rows = SignupLedgerEntry.objects.count()
        second = self._close(event)
        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        assert second.check is not None
        self.assertEqual(second.check.pk, first.check.pk if first.check else None)
        self.assertEqual(second.dropped_user_ids, ())
        self.assertEqual(SignupLedgerEntry.objects.count(), rows)
        self.assertEqual(len(self._dropped(event)), 3)

    def test_close_on_held_check_returns_it_unchanged(self) -> None:
        event, _ = self._setup(AUTO, 6, 10, HOLD)
        self._close(event)
        again = self._close(event)
        self.assertFalse(again.changed)
        assert again.check is not None
        self.assertEqual(again.check.phase, ReadyCheckPhase.HELD)

    def test_decision_follows_snapshot_not_live_fields(self) -> None:
        event, _ = self._setup(AUTO, 7, 10)
        Event.objects.filter(pk=event.pk).update(
            roll_call_mode=MANUAL, ready_check_min_completion_pct=100
        )
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.BINDING)
        self.assertEqual(len(result.dropped_user_ids), 3)

    def test_deleted_signup_entry_is_neither_counted_nor_dropped(self) -> None:
        event, signups = self._setup(AUTO, 7, 10)
        gone = signups[9]
        check = ReadyCheck.objects.get(event=event)
        entry = self._entry(check, gone)
        EventSignup.objects.filter(pk=gone.pk).delete()
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.completion_pct, 77)
        self.assertEqual(len(result.dropped_user_ids), 2)
        self.assertNotIn(gone.user_id, result.dropped_user_ids)
        entry.refresh_from_db()
        self.assertIsNone(entry.signup_id)
        self.assertEqual(entry.state, ReadyCheckEntryState.PENDING)

    def test_member_demoted_to_waitlist_under_main_only_is_out_of_scope(self) -> None:
        event, signups = self._setup(AUTO, 7, 10)
        demoted = signups[9]
        with self.captureOnCommitCallbacks(execute=True):
            demote_to_waitlist(demoted)
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.completion_pct, 77)
        self.assertNotIn(demoted.user_id, result.dropped_user_ids)
        demoted.refresh_from_db()
        self.assertEqual(demoted.status, SignupStatus.WAITLISTED)

    def test_no_check_or_cancelled(self) -> None:
        event = self.make_event(state=EventState.ROLL_CALL)
        self.assertEqual(self._close(event), CloseResult(check=None, changed=False))
        event, _ = self._setup(AUTO, 1, 2)
        with self.captureOnCommitCallbacks(execute=True):
            cancel_ready_check(event, actor=self.staff_actor, reason="test")
        self.assertEqual(self._close(event), CloseResult(check=None, changed=False))

    def test_outside_roll_call_is_noop(self) -> None:
        event, _ = self._setup(AUTO, 1, 2)
        Event.objects.filter(pk=event.pk).update(state=EventState.IN_PROGRESS)
        result = self._close(event)
        self.assertFalse(result.changed)
        self.assertEqual(
            ReadyCheck.objects.get(event=event).phase, ReadyCheckPhase.OPEN
        )
        self.assertEqual(self._dropped(event), [])

    def test_closed_signal_carries_unconfirmed(self) -> None:
        event, signups = self._setup(MANUAL, 1, 3)
        with self._listen(ready_check_signals.ready_check_closed) as sig:
            self._close(event)
        sig.assert_called_once()
        self.assertEqual(
            set(sig.call_args.kwargs["change"].user_ids),
            {signups[1].user_id, signups[2].user_id},
        )


class PromotionTests(LifecycleTestCase):
    def test_drops_promote_waitlist_with_fill_confirmation(self) -> None:
        event = self.make_event(
            roll_call_enabled=True,
            roll_call_mode=AUTO,
            ready_check_scope=ReadyCheckScope.MAIN_AND_FILL,
            max_players=10,
        )
        main = [self._signup(SignupStatus.APPROVED, event=event) for _ in range(10)]
        fill = EventSignup.objects.create(
            event=event,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        check = self._open(event).check
        for signup in main[:7]:
            self._confirm_member(signup)
        self._confirm_member(fill)
        late = EventSignup.objects.create(
            event=event,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=2,
        )
        result = self._close(event)
        self.assertEqual(len(result.dropped_user_ids), 3)
        self.assertEqual(set(result.promoted_signup_ids), {fill.pk, late.pk})
        fill.refresh_from_db()
        late.refresh_from_db()
        self.assertEqual(fill.status, SignupStatus.CONFIRMED)
        self.assertEqual(late.status, SignupStatus.APPROVED)
        event.refresh_from_db()
        roster = set(event.tournament.users.values_list("pk", flat=True))
        self.assertIn(fill.user_id, roster)
        self.assertNotIn(late.user_id, roster)
        late_entry = self._entry(check, late)
        self.assertEqual(late_entry.state, ReadyCheckEntryState.PENDING)
        promoted = self._rows(SignupAction.PROMOTED, event)
        self.assertEqual({r.signup_id for r in promoted}, {fill.pk, late.pk})
        self.assertTrue(all(r.actor_user == self.helper for r in promoted))
        asked = [
            r
            for r in self._rows(SignupAction.READY_CHECK_ASKED, event)
            if r.signup_id == late.pk
        ]
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0].actor_user, self.helper)
        self.assertEqual(asked[0].actor_role, ActorRole.STAFF)
        self.assertEqual(asked[0].correlation_id, f"rc{check.pk}:enrol")

    def test_unconfirmed_fill_member_present_at_open_is_dropped(self) -> None:
        event = self.make_event(
            roll_call_enabled=True,
            roll_call_mode=AUTO,
            ready_check_scope=ReadyCheckScope.MAIN_AND_FILL,
            max_players=10,
        )
        main = [self._signup(SignupStatus.APPROVED, event=event) for _ in range(10)]
        fill = EventSignup.objects.create(
            event=event,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        check = self._open(event).check
        for signup in main[:8]:
            self._confirm_member(signup)
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.BINDING)
        self.assertIn(fill.user_id, result.dropped_user_ids)
        self.assertEqual(result.promoted_signup_ids, ())
        fill.refresh_from_db()
        self.assertEqual(fill.status, SignupStatus.DROPPED)
        self.assertIsNone(fill.waitlist_position)
        self.assertEqual(self._entry(check, fill).state, ReadyCheckEntryState.DROPPED)

    def test_unlimited_capacity_promotes_nobody(self) -> None:
        event, _ = self._setup(AUTO, 7, 10)
        waiting = EventSignup.objects.create(
            event=event,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        result = self._close(event)
        self.assertEqual(len(result.dropped_user_ids), 3)
        self.assertEqual(result.promoted_signup_ids, ())
        waiting.refresh_from_db()
        self.assertEqual(waiting.status, SignupStatus.WAITLISTED)

    def _cancel_to_promote(
        self, mode: str, **event_fields: object
    ) -> tuple[Event, EventSignup]:
        event, main = self._setup(mode, 0, 2, max_players=2, **event_fields)
        waiting = EventSignup.objects.create(
            event=event,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        with self.captureOnCommitCallbacks(execute=True):
            cancel_signup(main[0], actor=self._member_actor(main[0].user))
        waiting.refresh_from_db()
        return event, waiting

    def test_auto_confirm_promotee_in_automatic_mode_is_asked(self) -> None:
        event, waiting = self._cancel_to_promote(AUTO, auto_confirm=True)
        self.assertEqual(waiting.status, SignupStatus.APPROVED)
        entry = self._entry(ReadyCheck.objects.get(event=event), waiting)
        self.assertEqual(entry.state, ReadyCheckEntryState.PENDING)

    def test_auto_confirm_promotee_in_manual_mode_stays_confirmed(self) -> None:
        event, waiting = self._cancel_to_promote(MANUAL, auto_confirm=True)
        self.assertEqual(waiting.status, SignupStatus.CONFIRMED)
        entry = self._entry(ReadyCheck.objects.get(event=event), waiting)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.STAFF)

    def test_manual_approval_promotee_is_rsvp_without_entry(self) -> None:
        event, main = self._setup(AUTO, 0, 2, max_players=2)
        Event.objects.filter(pk=event.pk).update(auto_approve=False)
        waiting = EventSignup.objects.create(
            event=event,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        with self.captureOnCommitCallbacks(execute=True):
            cancel_signup(main[0], actor=self._member_actor(main[0].user))
        waiting.refresh_from_db()
        self.assertEqual(waiting.status, SignupStatus.RSVP)
        self.assertFalse(ReadyCheckEntry.objects.filter(signup=waiting).exists())

    def test_confirmed_fill_promotee_via_cancel_is_confirmed(self) -> None:
        event = self.make_event(
            roll_call_enabled=True,
            roll_call_mode=AUTO,
            ready_check_scope=ReadyCheckScope.MAIN_AND_FILL,
            max_players=2,
        )
        main = [self._signup(SignupStatus.APPROVED, event=event) for _ in range(2)]
        fill = EventSignup.objects.create(
            event=event,
            user=self.make_user(),
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        self._open(event)
        self._confirm_member(fill)
        with self.captureOnCommitCallbacks(execute=True):
            cancel_signup(main[0], actor=self._member_actor(main[0].user))
        fill.refresh_from_db()
        self.assertEqual(fill.status, SignupStatus.CONFIRMED)
        event.refresh_from_db()
        self.assertIn(fill.user, event.tournament.users.all())


class LedgerActorTests(LifecycleTestCase):
    def test_every_ready_check_row_has_actor_means_reason(self) -> None:
        event = self.make_event(
            roll_call_enabled=True,
            roll_call_mode=AUTO,
            ready_check_min_completion_pct=50,
            ready_check_low_completion_action=DROP_ANYWAY,
        )
        signups = [self._signup(SignupStatus.APPROVED, event=event) for _ in range(4)]
        check = self._open(event).check
        self._confirm_member(signups[0])
        self._confirm_member(signups[1], actor=self.staff_actor)
        self._escalate(event)
        self._chase(event)
        result = self._close(event)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.BINDING)
        self.assertEqual(len(result.dropped_user_ids), 2)
        rows = list(
            SignupLedgerEntry.objects.filter(
                correlation_id__startswith=f"rc{check.pk}:"
            )
        )
        actions = {r.action for r in rows}
        for expected in (
            SignupAction.READY_CHECK_ASKED,
            SignupAction.CONFIRMED,
            SignupAction.READY_CHECK_NUDGED,
            SignupAction.DROPPED,
            SignupAction.READY_CHECK_TRANSITION,
        ):
            self.assertIn(expected, actions)
        member = signups[0].user
        for row in rows:
            with self.subTest(action=row.action, reason=row.reason):
                self.assertTrue(row.reason)
                self.assertNotEqual(row.actor_role, ActorRole.SYSTEM)
                self.assertNotEqual(row.means, SignupMeans.SYSTEM)
                self.assertEqual(row.means, SignupMeans.WEB)
                if row.action == SignupAction.CONFIRMED and row.subject_user == member:
                    self.assertEqual(row.actor_user, member)
                    self.assertEqual(row.actor_role, ActorRole.MEMBER)
                else:
                    self.assertEqual(row.actor_user, self.helper)
                    self.assertEqual(row.actor_role, ActorRole.STAFF)
