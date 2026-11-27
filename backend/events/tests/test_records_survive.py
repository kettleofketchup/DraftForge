from typing import Any
from unittest.mock import Mock, patch

from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

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
from events.services import (
    SignupRecordsConflict,
    cancel_event,
    create_tournament_for_event,
    teardown_event,
)
from events.tests.base import EventTestCase
from tournament.models import Tournament


class CancellationAPITest(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        for target in (
            "events.services.notify_signup_changed",
            "events.discord.dispatch.notify_signup_changed",
        ):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _event_with_signup(self, **overrides: Any) -> Event:
        event = self.make_event(**overrides)
        EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.APPROVED
        )
        return event

    def _assert_cancelled(self, event: Event, reason: str, data: Any = None) -> None:
        response = self.client.post(
            f"/api/events/{event.pk}/cancel/", data, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["id"], event.pk)
        self.assertEqual(response.data["state"], EventState.CANCELLED)
        self.assertTrue(response.data["user_can_manage"])
        self.assertEqual(response.data["signup_count"], 1)
        event.refresh_from_db()
        self.assertEqual(event.state, EventState.CANCELLED)
        entry = SignupLedgerEntry.objects.get(
            event=event, action=SignupAction.EVENT_CANCELLED
        )
        self.assertEqual(entry.reason, reason)
        self.assertEqual(entry.actor_user_id, self.admin.pk)

    def test_empty_legacy_request(self) -> None:
        for payload in (None, {}, {"reason": ""}):
            with self.subTest(payload=payload):
                self._assert_cancelled(self._event_with_signup(), "", payload)

    def test_reason_round_trips(self) -> None:
        for reason in ("  Schedule changed\n  ", "x" * 2000):
            with self.subTest(length=len(reason)):
                self._assert_cancelled(
                    self._event_with_signup(), reason, {"reason": reason}
                )

    def test_invalid_reason_has_no_effects(self) -> None:
        for reason in (None, 42, 1.5, True, [], {}, "x" * 2001):
            with self.subTest(reason=reason):
                event = self._event_with_signup()
                original_event = Event.objects.filter(pk=event.pk).values().get()
                original_signups = list(
                    EventSignup.objects.filter(event=event).values()
                )
                original_entries = list(
                    SignupLedgerEntry.objects.filter(event=event).values()
                )
                response = self.client.post(
                    f"/api/events/{event.pk}/cancel/",
                    {"reason": reason},
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("reason", response.data)
                self.assertEqual(
                    Event.objects.nocache().filter(pk=event.pk).values().get(),
                    original_event,
                )
                self.assertEqual(
                    list(EventSignup.objects.nocache().filter(event=event).values()),
                    original_signups,
                )
                self.assertEqual(
                    list(SignupLedgerEntry.objects.filter(event=event).values()),
                    original_entries,
                )

    def test_cancel_permission_and_state_matrix(self) -> None:
        org_staff = self.make_user()
        self.org.staff.add(org_staff)
        host = self.make_user()
        helper = self.make_user()
        member = self.make_user()
        for actor, permitted in (
            (self.admin, True),
            (org_staff, True),
            (self.league_staff, True),
            (member, False),
            (host, False),
            (helper, False),
            (None, False),
        ):
            for state in EventState:
                with self.subTest(actor=actor, state=state):
                    event = self._event_with_signup(
                        state=state, tournament_league=self.league, host=host
                    )
                    event.helpers.add(helper)
                    self.client.force_authenticate(actor)
                    response = self.client.post(
                        f"/api/events/{event.pk}/cancel/",
                        {"reason": "Schedule changed"},
                        format="json",
                    )
                    cancellable = state in {
                        EventState.UPCOMING,
                        EventState.SIGNUPS_OPEN,
                        EventState.ROLL_CALL,
                    }
                    expected = (
                        200 if permitted and cancellable else 400 if permitted else 403
                    )
                    self.assertEqual(response.status_code, expected, response.content)
                    event.refresh_from_db()
                    entries = SignupLedgerEntry.objects.filter(
                        event=event, action=SignupAction.EVENT_CANCELLED
                    )
                    if expected == 200:
                        self.assertEqual(event.state, EventState.CANCELLED)
                        self.assertEqual(entries.get().actor_user_id, actor.pk)
                        self.assertEqual(entries.get().reason, "Schedule changed")
                    else:
                        self.assertEqual(event.state, state)
                        self.assertFalse(entries.exists())
                        if expected == 400:
                            self.assertIn("error", response.data)


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


class RecordDeletionAPITest(EventTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        patcher = patch("events.services.notify_signup_changed")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _recorded_event(self) -> Event:
        event = self.make_event()
        signup = EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.CANCELLED
        )
        for link in (signup, None):
            record_signup_change(
                event=event,
                subject=self.user,
                actor=SignupActor.system(),
                action=SignupAction.SIGNED_UP,
                signup=link,
            )
        deleted_signup = EventSignup.objects.create(
            event=event, user=self.make_user(), status=SignupStatus.CANCELLED
        )
        record_signup_change(
            event=event,
            subject=deleted_signup.user,
            actor=SignupActor.system(),
            action=SignupAction.SIGNED_UP,
            signup=deleted_signup,
        )
        deleted_signup.delete()
        return event

    def _snapshot(self, event_id: int) -> list[dict[str, Any]]:
        return list(
            SignupLedgerEntry.objects.filter(event_id=event_id).order_by("pk").values()
        )

    def test_ordinary_delete_conflict_has_exact_integer_ledger_count(self) -> None:
        for query in ("", "?confirm=false", "?confirm=True", "?confirm=1", "?confirm="):
            with self.subTest(query=query):
                event = self._recorded_event()
                original_rows = self._snapshot(event.pk)
                with patch("events.services.standing.on_event_deleted") as deleted:
                    response = self.client.delete(f"/api/events/{event.pk}/{query}")
                self.assertEqual(response.status_code, 409, response.content)
                self.assertEqual(
                    response.json(), {"error": "has_signup_records", "count": 3}
                )
                self.assertIs(type(response.json()["count"]), int)
                deleted.assert_not_called()
                self.assertTrue(Event.objects.nocache().filter(pk=event.pk).exists())
                self.assertEqual(self._snapshot(event.pk), original_rows)
                self.assertEqual(EventSignup.objects.filter(event=event).count(), 1)

    def test_delete_permission_and_confirmation_matrix(self) -> None:
        staff = self.make_user()
        self.org.staff.add(staff)
        org_admin = self.make_user()
        self.org.admins.add(org_admin)
        site_staff = self.make_user()
        site_staff.is_staff = True
        site_staff.save(update_fields=["is_staff"])
        superuser = self.make_user()
        superuser.is_superuser = True
        superuser.save(update_fields=["is_superuser"])
        outsider = self.make_user()
        for actor, can_delete, can_confirm in (
            (None, False, False),
            (self.user, False, False),
            (outsider, False, False),
            (self.league_staff, False, False),
            (staff, True, False),
            (self.admin, True, True),
            (org_admin, True, True),
            (site_staff, True, True),
            (superuser, True, True),
        ):
            for has_records in (False, True):
                for confirm in (False, True):
                    with self.subTest(
                        actor=actor, records=has_records, confirm=confirm
                    ):
                        event = (
                            self._recorded_event() if has_records else self.make_event()
                        )
                        event.tournament_league = self.league
                        event.save(update_fields=["tournament_league"])
                        event_id = event.pk
                        originals = self._snapshot(event_id)
                        self.client.force_authenticate(actor)
                        query = "?confirm=true" if confirm else ""
                        response = self.client.delete(f"/api/events/{event_id}/{query}")
                        expected = (
                            403
                            if not can_delete or (confirm and not can_confirm)
                            else 409
                            if has_records and not confirm
                            else 204
                        )
                        self.assertEqual(
                            response.status_code, expected, response.content
                        )
                        self.assertEqual(
                            Event.objects.nocache().filter(pk=event_id).exists(),
                            expected != 204,
                        )
                        self.assertEqual(self._snapshot(event_id), originals)
                        if expected == 403:
                            self.assertNotIn(b'"count"', response.content)

    def test_role_revocation_blocks_confirmed_request(self) -> None:
        actor = self.make_user()
        self.org.admins.add(actor)
        self.org.staff.add(actor)
        self.client.force_authenticate(actor)
        event = self._recorded_event()
        response = self.client.delete(f"/api/events/{event.pk}/")
        self.assertEqual(response.status_code, 409, response.content)
        self.org.admins.remove(actor)
        response = self.client.delete(f"/api/events/{event.pk}/?confirm=true")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertTrue(Event.objects.nocache().filter(pk=event.pk).exists())

    def test_confirmed_delete_preserves_exact_snapshots_and_cascades_signups(
        self,
    ) -> None:
        event = self._recorded_event()
        event_id = event.pk
        before = self._snapshot(event_id)
        response = self.client.delete(f"/api/events/{event_id}/?confirm=true")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Event.objects.nocache().filter(pk=event_id).exists())
        self.assertFalse(
            EventSignup.objects.nocache().filter(event_id=event_id).exists()
        )
        self.assertEqual(self._snapshot(event_id), before)

    def test_service_default_conflict_precedes_cleanup(self) -> None:
        event = self._recorded_event()
        event_id = event.pk
        before = self._snapshot(event_id)
        with patch("events.services.standing.on_event_deleted") as deleted:
            with self.assertRaises(SignupRecordsConflict) as raised:
                teardown_event(event, actor=self.admin)
        self.assertEqual(type(raised.exception).__name__, "SignupRecordsConflict")
        self.assertEqual(raised.exception.count, 3)
        deleted.assert_not_called()
        self.assertTrue(Event.objects.nocache().filter(pk=event_id).exists())
        self.assertEqual(self._snapshot(event_id), before)

    def test_service_override_requires_an_authorized_actor(self) -> None:
        staff = self.make_user()
        self.org.staff.add(staff)
        for actor in (None, staff):
            with self.subTest(actor=actor):
                event = self._recorded_event()
                with self.assertRaises(PermissionError):
                    teardown_event(event, actor=actor, confirm_signup_records=True)
                self.assertTrue(Event.objects.nocache().filter(pk=event.pk).exists())
        event = self._recorded_event()
        event_id = event.pk
        before = self._snapshot(event_id)
        teardown_event(event, actor=self.admin, confirm_signup_records=True)
        self.assertFalse(Event.objects.nocache().filter(pk=event_id).exists())
        self.assertEqual(self._snapshot(event_id), before)

    def test_empty_event_service_teardown_keeps_ordinary_access(self) -> None:
        event = self.make_event()
        event_id = event.pk
        teardown_event(event)
        self.assertFalse(Event.objects.nocache().filter(pk=event_id).exists())
