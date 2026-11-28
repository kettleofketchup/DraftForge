import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from structlog.testing import capture_logs

from events.constants import ActorRole, SignupAction, SignupMeans
from events.ledger import (
    SignupActor,
    SignupPurgeResult,
    event_snapshot,
    purge_expired,
    record_ready_check_transition,
)
from events.models import Event, EventSignup, ReadyCheck, SignupLedgerEntry
from events.tests.base import EventTestCase
from org.models import Organization, OrgSettings

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, step: float = 1.0) -> None:
        self.t = 0.0
        self.step = step

    def monotonic(self) -> float:
        value = self.t
        self.t += self.step
        return value


class PurgeExpiredTest(EventTestCase):
    def setUp(self) -> None:
        self.settings_row = OrgSettings.objects.create(
            organization=self.org, signup_record_retention_days=365
        )

    def _org(self, name: str, retention: int | None) -> Organization:
        org = Organization.objects.create(name=name, owner=self.admin)
        if retention is not None:
            OrgSettings.objects.create(
                organization=org, signup_record_retention_days=retention
            )
        return org

    def _entry(
        self,
        event: Event,
        *,
        snapshot: dict[str, Any] | None = None,
        organization_id: int | None | object = ...,
    ) -> SignupLedgerEntry:
        org_id = event.organization_id if organization_id is ... else organization_id
        return SignupLedgerEntry.objects.create(
            event_id=event.pk,
            organization_id=org_id,
            event_snapshot=snapshot if snapshot is not None else event_snapshot(event),
            subject_user=self.user,
            subject_snapshot={"user_id": self.user.pk},
            actor_role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            action=SignupAction.SIGNED_UP,
            correlation_id=uuid.uuid4().hex,
        )

    def _event(
        self,
        days_ago: float,
        *,
        rows: int = 1,
        organization: Organization | None = None,
        with_end: bool = True,
    ) -> Event:
        scheduled = NOW - timedelta(days=days_ago, hours=2)
        event = self.make_event(
            organization=organization or self.org,
            scheduled_at=scheduled,
            ends_at=NOW - timedelta(days=days_ago) if with_end else None,
        )
        for _ in range(rows):
            self._entry(event)
        return event

    def _remaining(self) -> Counter[int]:
        return Counter(SignupLedgerEntry.objects.values_list("event_id", flat=True))

    def test_null_retention_purges_nothing(self) -> None:
        self.settings_row.signup_record_retention_days = None
        self.settings_row.save()
        no_settings = self._org("No Settings Org", None)
        self._event(1000)
        self._event(1000, organization=no_settings)

        result = purge_expired(now=NOW)

        self.assertEqual(
            result,
            SignupPurgeResult(
                purged=0,
                organizations=0,
                events=0,
                skipped_unknown_end=0,
                per_org={},
                more=False,
            ),
        )
        self.assertEqual(SignupLedgerEntry.objects.count(), 2)

    def test_boundary_366_purged_364_kept(self) -> None:
        old = self._event(366, rows=2)
        recent = self._event(364)

        result = purge_expired(now=NOW)

        self.assertEqual(self._remaining(), Counter({recent.pk: 1}))
        self.assertNotIn(old.pk, self._remaining())
        self.assertEqual(result.purged, 2)
        self.assertEqual(result.events, 1)
        self.assertEqual(result.per_org, {self.org.pk: 2})
        self.assertFalse(result.more)

    def test_exact_cutoff_kept(self) -> None:
        event = self._event(365)

        purge_expired(now=NOW)

        self.assertEqual(self._remaining(), Counter({event.pk: 1}))

    def test_falls_back_to_scheduled_at(self) -> None:
        old = self._event(366, with_end=False)
        recent = self._event(364, with_end=False)

        purge_expired(now=NOW)

        self.assertEqual(self._remaining(), Counter({recent.pk: 1}))
        self.assertNotIn(old.pk, self._remaining())

    def test_deleted_event_decided_by_latest_snapshot(self) -> None:
        event = self.make_event(scheduled_at=NOW - timedelta(days=10))
        base = event_snapshot(event)
        self._entry(event, snapshot=base)
        expired = {
            **base,
            "scheduled_at": (NOW - timedelta(days=400)).isoformat(),
            "ends_at": (NOW - timedelta(days=400)).isoformat(),
        }
        self._entry(event, snapshot=expired)
        kept = self.make_event(scheduled_at=NOW - timedelta(days=400))
        kept_base = event_snapshot(kept)
        self._entry(kept, snapshot=kept_base)
        self._entry(
            kept,
            snapshot={
                **kept_base,
                "scheduled_at": (NOW - timedelta(days=5)).isoformat(),
                "ends_at": None,
            },
        )
        Event.objects.filter(pk__in=[event.pk, kept.pk]).delete()

        result = purge_expired(now=NOW)

        self.assertEqual(self._remaining(), Counter({kept.pk: 2}))
        self.assertEqual(result.purged, 2)

    def test_rescheduled_event_uses_live_end(self) -> None:
        stale = {"scheduled_at": (NOW - timedelta(days=400)).isoformat()}
        moved_later = self.make_event(scheduled_at=NOW - timedelta(days=10))
        for _ in range(2):
            self._entry(moved_later, snapshot={**event_snapshot(moved_later), **stale})
        recent = {"scheduled_at": (NOW - timedelta(days=5)).isoformat()}
        moved_earlier = self.make_event(scheduled_at=NOW - timedelta(days=400))
        for _ in range(3):
            self._entry(
                moved_earlier, snapshot={**event_snapshot(moved_earlier), **recent}
            )

        result = purge_expired(now=NOW)

        self.assertEqual(self._remaining(), Counter({moved_later.pk: 2}))
        self.assertEqual(result.purged, 3)
        self.assertEqual(result.events, 1)

    def test_moved_event_uses_old_org_snapshot(self) -> None:
        other = self._org("Other Org", 30)
        event = self._event(400, rows=2)
        Event.objects.filter(pk=event.pk).update(
            organization=other, scheduled_at=NOW, ends_at=NOW + timedelta(hours=2)
        )
        keep = self.make_event(scheduled_at=NOW - timedelta(days=10))
        self._entry(keep)
        Event.objects.filter(pk=keep.pk).update(
            organization=other, scheduled_at=NOW - timedelta(days=900)
        )

        result = purge_expired(now=NOW)

        self.assertEqual(self._remaining(), Counter({keep.pk: 1}))
        self.assertEqual(result.per_org, {self.org.pk: 2})

    def test_null_org_rows_untouched(self) -> None:
        event = self._event(1000)
        self._entry(event, organization_id=None)

        result = purge_expired(now=NOW)

        self.assertEqual(
            list(SignupLedgerEntry.objects.values_list("organization_id", flat=True)),
            [None],
        )
        self.assertEqual(result.purged, 1)

    def test_neighbour_org_other_retention(self) -> None:
        neighbour = self._org("Neighbour Org", 30)
        mine = self._event(60)
        theirs = self._event(60, rows=2, organization=neighbour)

        result = purge_expired(now=NOW)

        self.assertEqual(self._remaining(), Counter({mine.pk: 1}))
        self.assertNotIn(theirs.pk, self._remaining())
        self.assertEqual(result.per_org, {neighbour.pk: 2})
        self.assertEqual(result.organizations, 1)

    def test_unknown_end_kept_and_counted(self) -> None:
        event = self.make_event(scheduled_at=NOW - timedelta(days=900))
        self._entry(event, snapshot={"id": event.pk, "name": "No times"})
        Event.objects.filter(pk=event.pk).delete()

        result = purge_expired(now=NOW)

        self.assertEqual(self._remaining(), Counter({event.pk: 1}))
        self.assertEqual(result.skipped_unknown_end, 1)
        self.assertEqual(result.purged, 0)

    def test_eventsignup_untouched(self) -> None:
        event = self._event(400)
        EventSignup.objects.create(event=event, user=self.user)
        before = EventSignup.objects.count()

        purge_expired(now=NOW)

        self.assertEqual(EventSignup.objects.count(), before)
        self.assertFalse(SignupLedgerEntry.objects.filter(event_id=event.pk).exists())

    def test_ready_check_rows_purged_with_event(self) -> None:
        event = self._event(400)
        check = ReadyCheck.objects.create(event=event)
        entry = record_ready_check_transition(
            event=event, actor=SignupActor.system(), check=check, step="started"
        )
        self.assertEqual(entry.subject_snapshot, {})

        result = purge_expired(now=NOW)

        self.assertFalse(SignupLedgerEntry.objects.exists())
        self.assertEqual(result.purged, 2)

    def test_budget_returns_more_and_resumes(self) -> None:
        sizes = {self._event(400 + i, rows=i + 1).pk: i + 1 for i in range(3)}
        clock = FakeClock()

        with patch("events.ledger.time", clock), patch("events.models.time", clock):
            first = purge_expired(now=NOW, batch_size=1, time_budget_s=3.5)

        self.assertTrue(first.more)
        self.assertEqual(first.events, 2)
        for event_id, n in self._remaining().items():
            self.assertEqual(n, sizes[event_id])
        self.assertEqual(len(self._remaining()), 1)

        second = purge_expired(now=NOW, batch_size=1)
        self.assertFalse(second.more)
        self.assertEqual(second.events, 1)
        self.assertFalse(SignupLedgerEntry.objects.exists())

        third = purge_expired(now=NOW)
        self.assertEqual(third.purged, 0)
        self.assertFalse(third.more)

    def test_zero_budget_deletes_nothing(self) -> None:
        self._event(400)

        result = purge_expired(now=NOW, time_budget_s=0.0)

        self.assertTrue(result.more)
        self.assertEqual(result.purged, 0)
        self.assertEqual(SignupLedgerEntry.objects.count(), 1)

    def test_default_budget_read_at_call_time(self) -> None:
        self._event(400)

        with self.settings(SIGNUP_RECORDS_PURGE_BUDGET_S=0.0):
            result = purge_expired(now=NOW)

        self.assertTrue(result.more)

    def test_expired_ids_chunked(self) -> None:
        events = [self._event(400) for _ in range(5)]

        with patch("events.models.PURGE_CHUNK_SIZE", 2):
            result = purge_expired(now=NOW, batch_size=2)

        self.assertEqual(result.events, len(events))
        self.assertFalse(SignupLedgerEntry.objects.exists())

    def test_log_lines(self) -> None:
        other = self._org("Second Org", 90)
        self._event(400, rows=2)
        self._event(100, rows=3, organization=other)
        self._event(10, organization=other)

        with capture_logs() as logs:
            result = purge_expired(now=NOW)

        purged = [e for e in logs if e["event"] == "signup_records_purged"]
        completed = [e for e in logs if e["event"] == "signup_records_purge_completed"]
        self.assertEqual(
            {e["organization_id"]: (e["count"], e["retention_days"]) for e in purged},
            {self.org.pk: (2, 365), other.pk: (3, 90)},
        )
        self.assertEqual(len(purged), 2)
        self.assertEqual(len(completed), 1)
        line = completed[0]
        self.assertEqual(line["system"], "events")
        self.assertEqual(line["subsystem"], "ledger")
        self.assertEqual(line["purged"], 5)
        self.assertEqual(line["organizations"], 2)
        self.assertEqual(line["events"], 2)
        self.assertEqual(line["skipped_unknown_end"], 0)
        self.assertFalse(line["more"])
        self.assertEqual(result.purged, 5)

    def test_org_without_expired_rows_logs_no_purge_line(self) -> None:
        self._event(10)

        with capture_logs() as logs:
            purge_expired(now=NOW)

        self.assertEqual(
            [e["event"] for e in logs if e["event"].startswith("signup_records_")],
            ["signup_records_purge_completed"],
        )
