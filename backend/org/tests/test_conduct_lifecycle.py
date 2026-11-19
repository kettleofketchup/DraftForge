from datetime import timedelta

from django.db import transaction
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import OrgLog, Tournament
from events.completion import close_event
from events.constants import EventState
from events.models import Event
from org.conduct.constants import Outcome, OutcomeSource
from org.conduct.lifecycle import void_event_outcomes
from org.models_conduct import AttendanceOutcome
from org.tests.conduct_base import ConductTestCase


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
        self.assertEqual(second, 0)
        self.assertEqual(row.voided_at, voided_at)
        self.assertEqual(self._void_logs(), [])

    def test_void_runs_with_feature_locked(self) -> None:
        event = self.make_event()
        row = self._late_cancel_row(event)
        voided = void_event_outcomes(event, now=tz.now(), actor=None)
        row.refresh_from_db()
        self.assertEqual(voided, 1)
        self.assertIsNotNone(row.voided_at)

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
