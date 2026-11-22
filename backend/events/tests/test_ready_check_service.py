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
    ConfirmResult,
    OpenResult,
    cancel_ready_check,
    confirm_ready,
    open_ready_check,
    refused_confirm_message,
)
from events.ready_check_constants import (
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckPhase,
    ReadyCheckScope,
)
from events.services import create_tournament_for_event
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
