from typing import Any
from unittest.mock import Mock, patch

from django.db import transaction
from django.utils import timezone

from discordbot.models import DiscordEvent
from events.constants import (
    ActorRole,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
)
from events.ledger import SignupActor, record_signup_change
from events.models import Event, EventSignup, EventTeam, ReadyCheck, SignupLedgerEntry
from events.ready_check import open_ready_check
from events.ready_check_constants import ReadyCheckPhase
from events.reopen import reopen_event
from events.services import cancel_event, create_tournament_for_event
from events.tests.base import EventTestCase
from tournament.models import Tournament


class CancellationRecordsTest(EventTestCase):
    def setUp(self) -> None:
        for target in (
            "events.services.notify_signup_changed",
            "events.discord.dispatch.notify_signup_changed",
        ):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _signup(self, event: Event, status: str = SignupStatus.APPROVED) -> EventSignup:
        return EventSignup.objects.create(
            event=event, user=self.make_user(), status=status
        )

    def _entries(self, event: Event) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                event_id=event.pk, action=SignupAction.EVENT_CANCELLED
            ).order_by("pk")
        )

    def test_every_signup_status_and_line_fields_survive(self) -> None:
        event = self.make_event()
        originals: dict[int, dict[str, Any]] = {}
        for status in SignupStatus:
            signup = self._signup(event, status)
            originals[signup.pk] = (
                EventSignup.objects.filter(pk=signup.pk).values().get()
            )
        result = cancel_event(event, actor=self.admin)
        self.assertEqual(result.state, EventState.CANCELLED)
        self.assertEqual(EventSignup.objects.filter(event=event).count(), 9)
        for pk, original in originals.items():
            with self.subTest(status=original["status"]):
                fetched = EventSignup.objects.nocache().get(pk=pk)
                self.assertEqual((fetched.pk, fetched.status), (pk, original["status"]))
                self.assertEqual(
                    EventSignup.objects.nocache().filter(pk=pk).values().get(), original
                )
                entries = SignupLedgerEntry.objects.filter(
                    signup_id=pk, action=SignupAction.EVENT_CANCELLED
                )
                self.assertEqual(
                    entries.count(),
                    0
                    if original["status"] in {"cancelled", "rejected", "dropped"}
                    else 1,
                )
                if entries.exists():
                    row = entries.get()
                    self.assertEqual(row.before["status"], original["status"])
                    self.assertEqual(row.before, row.after)
                    self.assertEqual(row.reason, "")
        self.assertEqual(SignupLedgerEntry.objects.filter(event=event).count(), 6)

    def test_staff_and_system_cancel_snapshots_and_reason(self) -> None:
        for actor, role, means in (
            (self.admin, ActorRole.STAFF, SignupMeans.WEB),
            (None, ActorRole.SYSTEM, SignupMeans.SYSTEM),
        ):
            with self.subTest(role=role):
                event = self.make_event()
                signup = self._signup(event)
                cancel_event(event, actor=actor, reason="Schedule changed")
                row = self._entries(event)[0]
                self.assertEqual(row.actor_user, actor)
                self.assertEqual((row.actor_role, row.means), (role, means))
                self.assertEqual(row.reason, "Schedule changed")
                self.assertEqual(row.subject_user_id, signup.user_id)
                self.assertEqual(row.subject_snapshot["user_id"], signup.user_id)
                self.assertEqual(row.signup_id, signup.pk)
                self.assertEqual(row.event_snapshot["id"], event.pk)
                self.assertEqual(row.event_snapshot["state"], "cancelled")
                self.assertEqual(row.before["status"], "approved")
                self.assertEqual(row.after["status"], "approved")

    def test_tournament_cleanup_preserves_actual_event_team_placement(self) -> None:
        event = self.make_event(tournament_league=self.league)
        tournament = create_tournament_for_event(event)
        team = EventTeam.objects.create(
            event=event, name="Record team", captain=self.admin
        )
        signup = self._signup(event)
        signup.event_team = team
        signup.save(update_fields=["event_team"])
        result = cancel_event(event, actor=self.admin)
        row = self._entries(event)[0]
        self.assertIsNone(result.tournament_id)
        self.assertFalse(Tournament.objects.filter(pk=tournament.pk).exists())
        self.assertEqual(row.before["event_team_id"], team.pk)
        self.assertEqual(row.after["event_team_id"], team.pk)
        self.assertIsNone(row.event_snapshot["tournament_id"])

    def test_ready_check_history_is_retained_alongside_cancellation(self) -> None:
        event = self.make_event()
        signup = self._signup(event)
        check = open_ready_check(event, actor=SignupActor.system()).check
        before_ids = set(
            SignupLedgerEntry.objects.filter(event=event).values_list("pk", flat=True)
        )
        cancel_event(event, actor=self.admin, reason="New date")
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        self.assertTrue(
            before_ids.issubset(
                set(
                    SignupLedgerEntry.objects.filter(event=event).values_list(
                        "pk", flat=True
                    )
                )
            )
        )
        self.assertEqual(len(self._entries(event)), 1)
        self.assertEqual(self._entries(event)[0].signup_id, signup.pk)
        self.assertTrue(
            SignupLedgerEntry.objects.filter(
                event=event,
                action=SignupAction.READY_CHECK_WITHDRAWN,
                reason="event_cancelled",
            ).exists()
        )
        self.assertTrue(
            SignupLedgerEntry.objects.filter(
                event=event,
                action=SignupAction.READY_CHECK_TRANSITION,
                reason="event_cancelled",
            ).exists()
        )
        self.assertFalse(
            SignupLedgerEntry.objects.filter(
                event=event, action__in=[SignupAction.WITHDREW, SignupAction.PROMOTED]
            ).exists()
        )

    def test_repeat_cancel_has_no_new_entries(self) -> None:
        event = self.make_event()
        self._signup(event)
        result = cancel_event(event, actor=self.admin)
        count = SignupLedgerEntry.objects.filter(event=event).count()
        self.assertEqual(count, 1)
        for candidate in (event, result):
            with self.assertRaises(ValueError):
                cancel_event(candidate, actor=self.admin)
        self.assertEqual(SignupLedgerEntry.objects.filter(event=event).count(), count)

    def test_reopen_then_cancel_records_another_cycle(self) -> None:
        event = self.make_event()
        signup = self._signup(event)
        closed = cancel_event(event, actor=self.admin)
        self.assertTrue(reopen_event(closed, actor=self.admin).reopened)
        cancel_event(closed, actor=self.admin)
        self.assertEqual(len(self._entries(event)), 2)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)

    def _rollback_fixture(self) -> tuple[Event, Tournament, ReadyCheck, DiscordEvent]:
        event = self.make_event(tournament_league=self.league)
        self._signup(event)
        self._signup(event)
        check = open_ready_check(event, actor=SignupActor.system()).check
        tournament = create_tournament_for_event(event)
        discord = DiscordEvent.objects.create(
            event=event, guild_id="101", scheduled_event_id="202"
        )
        return event, tournament, check, discord

    def test_cancel_failure_rolls_back_all_changes(self) -> None:
        for failure in ("ledger", "standing"):
            with self.subTest(failure=failure):
                event, tournament, check, discord = self._rollback_fixture()
                tournament_id = tournament.pk
                original_state = Event.objects.nocache().get(pk=event.pk).state
                original_rows = list(EventSignup.objects.filter(event=event).values())
                original_ids = set(
                    SignupLedgerEntry.objects.filter(event=event).values_list(
                        "pk", flat=True
                    )
                )
                calls = 0

                def fail_second_append(**kwargs: Any) -> SignupLedgerEntry:
                    nonlocal calls
                    if kwargs["action"] == SignupAction.EVENT_CANCELLED:
                        calls += 1
                        if calls == 2:
                            raise RuntimeError("ledger failure")
                    return record_signup_change(**kwargs)

                target = (
                    "events.services.record_signup_change"
                    if failure == "ledger"
                    else "events.services.standing.on_event_closed"
                )
                effect = (
                    fail_second_append
                    if failure == "ledger"
                    else RuntimeError("standing failure")
                )
                with (
                    patch(target, side_effect=effect),
                    patch(
                        "events.services.delete_discord_scheduled_event"
                    ) as delete_task,
                ):
                    with self.captureOnCommitCallbacks(execute=True):
                        with self.assertRaises(RuntimeError):
                            cancel_event(event, actor=self.admin)
                    delete_task.delay.assert_not_called()
                fetched = Event.objects.nocache().get(pk=event.pk)
                self.assertEqual(
                    (fetched.state, fetched.tournament_id),
                    (original_state, tournament_id),
                )
                self.assertTrue(Tournament.objects.filter(pk=tournament_id).exists())
                self.assertEqual(
                    list(EventSignup.objects.nocache().filter(event=event).values()),
                    original_rows,
                )
                self.assertEqual(
                    set(
                        SignupLedgerEntry.objects.filter(event=event).values_list(
                            "pk", flat=True
                        )
                    ),
                    original_ids,
                )
                check.refresh_from_db()
                self.assertEqual(check.phase, ReadyCheckPhase.OPEN)
                discord.refresh_from_db()
                self.assertEqual(discord.scheduled_event_id, "202")

    @patch("events.services.delete_discord_scheduled_event")
    def test_discord_cleanup_waits_for_outer_commit(self, delete_task: Mock) -> None:
        event = self.make_event()
        self._signup(event)
        discord = DiscordEvent.objects.create(
            event=event, guild_id="101", scheduled_event_id="202"
        )
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                cancel_event(event, actor=self.admin)
                discord.refresh_from_db()
                self.assertIsNone(discord.scheduled_event_id)
                delete_task.delay.assert_not_called()
        delete_task.delay.assert_called_once_with("101", "202")
        self.assertEqual(len(self._entries(event)), 1)

    @patch("events.services.delete_discord_scheduled_event")
    def test_outer_rollback_discards_discord_cleanup(self, delete_task: Mock) -> None:
        event = self.make_event()
        signup = self._signup(event)
        discord = DiscordEvent.objects.create(
            event=event, guild_id="101", scheduled_event_id="202"
        )
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    cancel_event(event, actor=self.admin)
                    self.assertEqual(len(self._entries(event)), 1)
                    raise RuntimeError("outer failure")
        delete_task.delay.assert_not_called()
        event.refresh_from_db()
        discord.refresh_from_db()
        signup.refresh_from_db()
        self.assertEqual(event.state, EventState.SIGNUPS_OPEN)
        self.assertEqual(discord.scheduled_event_id, "202")
        self.assertEqual(signup.status, SignupStatus.APPROVED)
        self.assertEqual(self._entries(event), [])

    def test_authoritative_invalid_state_rejects_before_cleanup(self) -> None:
        for state in (
            EventState.IN_PROGRESS,
            EventState.COMPLETED,
            EventState.CANCELLED,
        ):
            with self.subTest(state=state):
                event, tournament, check, discord = self._rollback_fixture()
                Event.objects.filter(pk=event.pk).update(state=state)
                now = timezone.now()
                with patch("events.services.cancel_ready_check") as cancel_check:
                    with self.assertRaises(ValueError):
                        cancel_event(event, actor=self.admin)
                    cancel_check.assert_not_called()
                self.assertTrue(Tournament.objects.filter(pk=tournament.pk).exists())
                self.assertFalse(
                    SignupLedgerEntry.objects.filter(
                        event=event,
                        action=SignupAction.EVENT_CANCELLED,
                        occurred_at__gte=now,
                    ).exists()
                )
