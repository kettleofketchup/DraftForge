from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import site
from django.db import connection, transaction
from django.http import HttpRequest
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import Tournament
from org.models import OrgLog, Organization
from discordbot.models import DiscordEvent
from events.completion import close_event
from events.constants import EventState, RepeatFrequency
from events.models import Event, EventRepeater
from events.reopen import reopen_event
from events.services import cancel_event, restart_event_tournament, teardown_event
from org.conduct.adapter import ConductTrack
from org.conduct.constants import Outcome, OutcomeSource
from org.conduct.lifecycle import (
    reopen_event_outcomes,
    teardown_event_outcomes,
    void_event_outcomes,
)
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome
from org.models_contributions import ContributionEntry
from org.tests.conduct_base import ConductTestCase

CANCEL_CLOSE_QUERIES = 5


class VoidOnCancelTest(ConductTestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.member = self.make_user()

    def _late_cancel_row(self, event: Event) -> AttendanceOutcome:
        return self.outcome(
            self.member,
            event=event,
            outcome=Outcome.LATE_CANCEL,
            source=OutcomeSource.LATE_CANCEL,
            finalized=False,
            cancelled_at=tz.now(),
        )

    def _void_logs(self) -> list[OrgLog]:
        return list(
            OrgLog.objects.filter(organization=self.org, action="void_attendance")
        )

    def test_staff_cancel_view_voids_rows(self) -> None:
        self.unlock()
        event = self.make_event(scheduled_at=tz.now() + timedelta(hours=1))
        row = self._late_cancel_row(event)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/events/{event.pk}/cancel/")
        self.assertEqual(resp.status_code, 200, resp.content)
        row.refresh_from_db()
        self.assertIsNotNone(row.voided_at)
        event = Event.objects.nocache().get(pk=event.pk)
        self.assertIsNotNone(event.conduct_finalized_at)
        logs = self._void_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].actor_id, self.admin.pk)
        self.assertEqual(logs[0].details, {"event_id": event.pk, "voided": 1})

    def test_auto_cancel_voids(self) -> None:
        self.unlock()
        event = self.make_event()
        row = self._late_cancel_row(event)
        result = close_event(event, new_state=EventState.CANCELLED, source="auto")
        self.assertTrue(result.closed)
        row.refresh_from_db()
        self.assertIsNotNone(row.voided_at)
        self.assertIsNotNone(
            Event.objects.nocache().get(pk=event.pk).conduct_finalized_at
        )
        self.assertEqual(self._void_logs(), [])

    def test_admin_close_cancel_logs_actor(self) -> None:
        event = self.make_event()
        self._late_cancel_row(event)
        close_event(
            event, new_state=EventState.CANCELLED, source="admin", actor=self.admin
        )
        logs = self._void_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].actor_id, self.admin.pk)

    def test_void_idempotent(self) -> None:
        event = self.make_event()
        row = self._late_cancel_row(event)
        with transaction.atomic():
            first = void_event_outcomes(event, now=tz.now(), actor=None)
        row.refresh_from_db()
        voided_at = row.voided_at
        with transaction.atomic():
            second = void_event_outcomes(
                event, now=tz.now() + timedelta(minutes=5), actor=self.admin
            )
        row.refresh_from_db()
        self.assertEqual(first, 1)
        self.assertIsNone(second)
        self.assertEqual(row.voided_at, voided_at)
        self.assertEqual(self._void_logs(), [])

    def test_void_runs_with_feature_locked(self) -> None:
        event = self.make_event()
        row = self._late_cancel_row(event)
        voided = void_event_outcomes(event, now=tz.now(), actor=None)
        row.refresh_from_db()
        self.assertEqual(voided, 1)
        self.assertIsNotNone(row.voided_at)

    def test_void_without_outcomes_claims(self) -> None:
        event = self.make_event()
        with transaction.atomic():
            self.assertEqual(void_event_outcomes(event, now=tz.now(), actor=None), 0)
        event.refresh_from_db()
        self.assertIsNotNone(event.conduct_finalized_at)

    @override_settings(CACHEOPS_ENABLED=False)
    def test_cancel_close_hook_skips_reread_when_locked(self) -> None:
        event = self.make_event()
        now = tz.now()
        with transaction.atomic(), self.assertNumQueries(CANCEL_CLOSE_QUERIES):
            ConductTrack().on_event_closed(
                event, cancelled=True, source="auto", actor=None, now=now
            )
        self.assertEqual(event.conduct_finalized_at, now)

    def test_void_leaves_other_events_rows(self) -> None:
        event = self.make_event()
        other = self.make_event()
        self._late_cancel_row(event)
        kept = self._late_cancel_row(other)
        void_event_outcomes(event, now=tz.now(), actor=None)
        kept.refresh_from_db()
        self.assertIsNone(kept.voided_at)

    def test_cancel_view_behaviour_unchanged(self) -> None:
        tournament = Tournament.objects.create(
            name="Cancel Tourney", date_played=tz.now(), state="future"
        )
        event = self.make_event(tournament=tournament)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/events/{event.pk}/cancel/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["state"], EventState.CANCELLED)
        self.assertFalse(Tournament.objects.filter(pk=tournament.pk).exists())
        event.refresh_from_db()
        self.assertIsNone(event.tournament_id)

    def test_cancel_view_refuses_bad_transition(self) -> None:
        event = self.make_event(state=EventState.COMPLETED)
        row = self._late_cancel_row(event)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/events/{event.pk}/cancel/")
        self.assertEqual(resp.status_code, 400, resp.content)
        row.refresh_from_db()
        self.assertIsNone(row.voided_at)

    def _discord_event(self, event: Event) -> DiscordEvent:
        return DiscordEvent.objects.create(
            event=event, guild_id="734185035623825559", scheduled_event_id="42"
        )

    @patch("events.tasks.delete_discord_scheduled_event.delay")
    def test_cancel_hook_exception_keeps_discord_event(self, delay) -> None:
        self.unlock()
        event = self.make_event()
        discord_event = self._discord_event(event)
        with (
            patch(
                "org.conduct.adapter.void_event_outcomes",
                side_effect=RuntimeError("boom"),
            ),
            self.captureOnCommitCallbacks(execute=True),
            self.assertRaises(RuntimeError),
        ):
            cancel_event(event, actor=self.admin)

        delay.assert_not_called()
        self.assertEqual(
            Event.objects.nocache().get(pk=event.pk).state, EventState.SIGNUPS_OPEN
        )
        discord_event.refresh_from_db()
        self.assertEqual(discord_event.scheduled_event_id, "42")

    @patch("events.tasks.delete_discord_scheduled_event.delay")
    def test_cancel_deletes_discord_event_on_commit(self, delay) -> None:
        event = self.make_event()
        discord_event = self._discord_event(event)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            cancel_event(event, actor=self.admin)
            delay.assert_not_called()
        for callback in callbacks:
            callback()

        delay.assert_called_once_with("734185035623825559", "42")
        discord_event.refresh_from_db()
        self.assertIsNone(discord_event.scheduled_event_id)

    def test_cancel_event_contribution_unchanged(self) -> None:
        self.unlock()
        event = self.make_event(host=self.member)

        cancel_event(event, actor=self.admin)

        self.assertFalse(ContributionEntry.objects.filter(event=event).exists())
        event = Event.objects.nocache().get(pk=event.pk)
        self.assertIsNone(event.contributions_awarded_at)
        self.assertIsNotNone(event.conduct_finalized_at)


class ReopenCleanupTest(ConductTestCase):
    def _seed(self, event: Event) -> dict[str, AttendanceOutcome]:
        now = tz.now()
        sources = {
            OutcomeSource.DEFAULT: {},
            OutcomeSource.READY_CHECK: {"outcome": Outcome.NO_SHOW},
            OutcomeSource.VOICE: {},
            OutcomeSource.STAFF: {"outcome": Outcome.EXCUSED, "reason": "sick"},
            OutcomeSource.LATE_CANCEL: {
                "outcome": Outcome.LATE_CANCEL,
                "cancelled_at": now,
            },
        }
        return {
            source: self.outcome(
                self.make_user(),
                event=event,
                source=source,
                voided_at=now,
                **extra,
            )
            for source, extra in sources.items()
        }

    def _reopen_logs(self, event: Event) -> list[OrgLog]:
        return list(
            OrgLog.objects.filter(
                organization=self.org,
                action="reopen_event",
                details__event_id=event.pk,
            )
        )

    def test_reopen_deletes_automatic_keeps_staff_and_late_cancel(self) -> None:
        self.unlock()
        event = self.make_event(state=EventState.COMPLETED)
        Event.objects.filter(pk=event.pk).update(conduct_finalized_at=tz.now())
        rows = self._seed(event)
        other = self.outcome(self.make_user(), event=self.make_event())

        result = reopen_event(event, actor=self.admin)

        self.assertTrue(result.reopened)
        remaining = AttendanceOutcome.objects.nocache().filter(event=event)
        self.assertEqual(
            set(remaining.values_list("source", flat=True)),
            {OutcomeSource.STAFF, OutcomeSource.LATE_CANCEL},
        )
        for row in remaining:
            self.assertIsNone(row.finalized_at)
            self.assertIsNone(row.voided_at)
        self.assertEqual(
            AttendanceOutcome.objects.nocache()
            .get(pk=rows[OutcomeSource.STAFF].pk)
            .outcome,
            Outcome.EXCUSED,
        )
        self.assertIsNone(Event.objects.nocache().get(pk=event.pk).conduct_finalized_at)
        other.refresh_from_db()
        self.assertIsNotNone(other.finalized_at)
        logs = self._reopen_logs(event)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].details["attendance_reopened"], 5)

    def test_reopen_one_update(self) -> None:
        self.unlock()
        event = self.make_event(state=EventState.COMPLETED)
        Event.objects.filter(pk=event.pk).update(
            conduct_finalized_at=tz.now(), contributions_awarded_at=tz.now()
        )
        event.refresh_from_db()

        with CaptureQueriesContext(connection) as ctx:
            reopen_event(event, actor=self.admin)

        updates = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].startswith('UPDATE "events_event"')
        ]
        self.assertEqual(len(updates), 1)
        self.assertIn('"contributions_awarded_at" = NULL', updates[0])
        self.assertIn('"conduct_finalized_at" = NULL', updates[0])
        event = Event.objects.nocache().get(pk=event.pk)
        self.assertIsNone(event.conduct_finalized_at)
        self.assertIsNone(event.contributions_awarded_at)

    def test_reopen_runs_with_feature_locked(self) -> None:
        event = self.make_event(state=EventState.CANCELLED)
        Event.objects.filter(pk=event.pk).update(conduct_finalized_at=tz.now())
        self._seed(event)

        reopen_event(event, actor=self.admin)

        self.assertEqual(
            AttendanceOutcome.objects.nocache().filter(event=event).count(), 2
        )
        self.assertFalse(
            AttendanceOutcome.objects.nocache()
            .filter(event=event, voided_at__isnull=False)
            .exists()
        )
        self.assertIsNone(Event.objects.nocache().get(pk=event.pk).conduct_finalized_at)

    def test_reopen_event_outcomes_counts(self) -> None:
        event = self.make_event()
        self._seed(event)
        with transaction.atomic():
            deleted, kept = reopen_event_outcomes(event)
        self.assertEqual((deleted, kept), (3, 2))

    def test_skipped_reopen_leaves_rows(self) -> None:
        event = self.make_event(state=EventState.SIGNUPS_OPEN)
        rows = self._seed(event)
        result = reopen_event(event, actor=self.admin)
        self.assertFalse(result.reopened)
        self.assertEqual(
            AttendanceOutcome.objects.nocache().filter(event=event).count(),
            len(rows),
        )

    def test_restart_event_tournament_reaches_cleanup(self) -> None:
        tournament = Tournament.objects.create(
            name="Restart Tourney", date_played=tz.now(), state="past"
        )
        event = self.make_event(state=EventState.COMPLETED, tournament=tournament)
        Event.objects.filter(pk=event.pk).update(conduct_finalized_at=tz.now())
        self.outcome(self.make_user(), event=event, source=OutcomeSource.DEFAULT)

        restart_event_tournament(event, actor=self.admin, can_reopen=True)

        self.assertFalse(
            AttendanceOutcome.objects.nocache()
            .filter(event=event, source=OutcomeSource.DEFAULT)
            .exists()
        )
        self.assertIsNone(Event.objects.nocache().get(pk=event.pk).conduct_finalized_at)


class TeardownOnDeleteTest(ConductTestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def _void_logs(self) -> list[OrgLog]:
        return list(
            OrgLog.objects.filter(organization=self.org, action="void_attendance")
        )

    def test_delete_view_voids_finalized_and_deletes_unfinalized(self) -> None:
        self.unlock()
        event = self.make_event(state=EventState.COMPLETED)
        event_pk = event.pk
        finalized = self.outcome(self.make_user(), event=event, outcome=Outcome.NO_SHOW)
        pending = self.outcome(
            self.make_user(),
            event=event,
            outcome=Outcome.LATE_CANCEL,
            source=OutcomeSource.LATE_CANCEL,
            finalized=False,
            cancelled_at=tz.now(),
        )
        other = self.outcome(self.make_user(), event=self.make_event())
        self.client.force_authenticate(self.admin)

        resp = self.client.delete(f"/api/events/{event_pk}/")

        self.assertEqual(resp.status_code, 204, resp.content)
        self.assertFalse(Event.objects.nocache().filter(pk=event_pk).exists())
        finalized.refresh_from_db()
        self.assertIsNone(finalized.event_id)
        self.assertIsNotNone(finalized.voided_at)
        self.assertFalse(
            AttendanceOutcome.objects.nocache()
            .counted()
            .filter(pk=finalized.pk)
            .exists()
        )
        self.assertFalse(
            AttendanceOutcome.objects.nocache().filter(pk=pending.pk).exists()
        )
        other.refresh_from_db()
        self.assertIsNone(other.voided_at)
        logs = self._void_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].actor_id, self.admin.pk)
        self.assertEqual(
            logs[0].details, {"event_id": event_pk, "deleted": 1, "voided": 1}
        )

    def _admin_request(self) -> HttpRequest:
        request = RequestFactory().post("/admin/")
        request.user = self.admin
        return request

    def test_admin_delete_voids_finalized_rows(self) -> None:
        event = self.make_event(state=EventState.COMPLETED)
        finalized = self.outcome(self.make_user(), event=event, outcome=Outcome.NO_SHOW)
        model_admin = site._registry[Event]

        model_admin.delete_model(self._admin_request(), event)

        finalized.refresh_from_db()
        self.assertIsNone(finalized.event_id)
        self.assertIsNotNone(finalized.voided_at)

    def test_admin_bulk_delete_voids_finalized_rows(self) -> None:
        events = [self.make_event(state=EventState.COMPLETED) for _ in range(2)]
        rows = [self.outcome(self.make_user(), event=event) for event in events]
        model_admin = site._registry[Event]

        model_admin.delete_queryset(
            self._admin_request(),
            Event.objects.filter(pk__in=[event.pk for event in events]),
        )

        for row in rows:
            row.refresh_from_db()
            self.assertIsNotNone(row.voided_at)
        self.assertFalse(
            Event.objects.nocache().filter(pk__in=[e.pk for e in events]).exists()
        )

    def test_admin_bulk_delete_two_orgs_one_locked(self) -> None:
        self.unlock()
        other_org = Organization.objects.create(name="Locked Org", owner=self.admin)
        final_member, pending_member = (
            OrgUser.objects.create(user=self.make_user(), organization=other_org)
            for _ in range(2)
        )
        unlocked_event = self.make_event(state=EventState.COMPLETED)
        locked_event = self.make_event(
            organization=other_org, state=EventState.COMPLETED
        )
        unlocked_final = self.outcome(self.make_user(), event=unlocked_event)
        unlocked_pending = self.outcome(
            self.make_user(), event=unlocked_event, finalized=False
        )
        now = tz.now()
        locked_final = AttendanceOutcome.objects.create(
            organization=other_org,
            org_user=final_member,
            event=locked_event,
            event_name=locked_event.name,
            event_starts_at=locked_event.scheduled_at,
            outcome=Outcome.ATTENDED,
            source=OutcomeSource.DEFAULT,
            finalized_at=now,
        )
        locked_pending = AttendanceOutcome.objects.create(
            organization=other_org,
            org_user=pending_member,
            event=locked_event,
            event_name=locked_event.name,
            event_starts_at=locked_event.scheduled_at,
            outcome=Outcome.LATE_CANCEL,
            source=OutcomeSource.LATE_CANCEL,
            cancelled_at=now,
        )

        site._registry[Event].delete_queryset(
            self._admin_request(),
            Event.objects.filter(pk__in=[unlocked_event.pk, locked_event.pk]),
        )

        for row in (unlocked_final, locked_final):
            row.refresh_from_db()
            self.assertIsNone(row.event_id)
            self.assertIsNotNone(row.voided_at)
        self.assertFalse(
            AttendanceOutcome.objects.nocache()
            .filter(pk__in=[unlocked_pending.pk, locked_pending.pk])
            .exists()
        )
        self.assertFalse(
            Event.objects.nocache()
            .filter(pk__in=[unlocked_event.pk, locked_event.pk])
            .exists()
        )

    def test_admin_conduct_finalized_at_read_only(self) -> None:
        self.assertIn("conduct_finalized_at", site._registry[Event].readonly_fields)

    def test_already_voided_row_keeps_voided_at(self) -> None:
        event = self.make_event()
        earlier = tz.now() - timedelta(days=2)
        row = self.outcome(self.make_user(), event=event, voided_at=earlier)

        teardown_event(event, actor=self.admin)

        row.refresh_from_db()
        self.assertEqual(row.voided_at, earlier)
        self.assertEqual(self._void_logs(), [])

    def test_series_realign_teardown_no_orglog(self) -> None:
        event = self.make_event()
        row = self.outcome(self.make_user(), event=event)

        teardown_event(event)

        row.refresh_from_db()
        self.assertIsNotNone(row.voided_at)
        self.assertEqual(self._void_logs(), [])

    def test_teardown_runs_with_feature_locked(self) -> None:
        event = self.make_event()
        pending = self.outcome(self.make_user(), event=event, finalized=False)
        with transaction.atomic():
            deleted, voided = teardown_event_outcomes(event, actor=None, now=tz.now())
        self.assertEqual((deleted, voided), (1, 0))
        self.assertFalse(
            AttendanceOutcome.objects.nocache().filter(pk=pending.pk).exists()
        )

    def test_series_delete_logs_actor(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day="18:00",
            starts_at=tz.now().date(),
            created_by=self.admin,
        )
        event = self.make_event(event_repeater=repeater, state=EventState.UPCOMING)
        self.outcome(self.make_user(), event=event, finalized=False)
        self.client.force_authenticate(self.admin)

        resp = self.client.delete(f"/api/events/repeaters/{repeater.pk}/")

        self.assertEqual(resp.status_code, 204, resp.content)
        logs = self._void_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].actor_id, self.admin.pk)
