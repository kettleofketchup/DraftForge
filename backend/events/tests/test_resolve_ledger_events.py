import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from django.utils import timezone as tz
from structlog.testing import capture_logs

from events.constants import ActorRole, EventState, SignupAction, SignupMeans
from events.ledger import (
    LEDGER_STATE_DELETED,
    LEDGER_STATE_MOVED,
    LedgerEvent,
    RecordsWindow,
    event_snapshot,
    parse_snapshot_time,
    resolve_ledger_events,
)
from events.models import Event, EventRepeater, SignupLedgerEntry
from events.tests.base import EventTestCase
from org.models import Organization

T0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


class ResolveLedgerEventsTest(EventTestCase):
    def _entry(
        self,
        event: Event,
        *,
        snapshot: dict[str, Any] | None = None,
        organization: Organization | None = None,
        occurred_at: datetime | None = None,
    ) -> SignupLedgerEntry:
        return SignupLedgerEntry.objects.create(
            event_id=event.pk,
            organization=organization or self.org,
            event_snapshot=snapshot if snapshot is not None else event_snapshot(event),
            subject_user=self.user,
            subject_snapshot={"user_id": self.user.pk},
            actor_role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            action=SignupAction.SIGNED_UP,
            correlation_id=uuid.uuid4().hex,
            occurred_at=occurred_at or tz.now(),
        )

    def _event_at(self, when: datetime, **overrides: Any) -> Event:
        event = self.make_event(scheduled_at=when, **overrides)
        self._entry(event)
        return event

    def _delete(self, event: Event) -> int:
        pk = event.pk
        Event.objects.filter(pk=pk).delete()
        return pk

    def _repeater(self) -> EventRepeater:
        return EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency="weekly",
            day_of_week=1,
            time_of_day="20:00",
            starts_at="2026-01-01",
        )

    def test_live_event_metadata(self) -> None:
        repeater = self._repeater()
        event = self.make_event(
            scheduled_at=T0,
            ends_at=T0 + timedelta(hours=2),
            event_repeater=repeater,
            state=EventState.COMPLETED,
        )
        self._entry(event, snapshot={"id": event.pk, "name": "stale"})

        result = resolve_ledger_events(self.org.pk)

        self.assertEqual(
            result[event.pk],
            LedgerEvent(
                event_id=event.pk,
                name=event.name,
                scheduled_at=T0,
                ends_at=T0 + timedelta(hours=2),
                state=EventState.COMPLETED,
                series_id=repeater.pk,
                organization_id=self.org.pk,
            ),
        )
        self.assertEqual(result[event.pk].end, T0 + timedelta(hours=2))

    def test_deleted_event_uses_latest_snapshot(self) -> None:
        event = self.make_event(scheduled_at=T0)
        base = event_snapshot(event)
        later = tz.now()
        self._entry(
            event,
            snapshot={**base, "name": "Older", "series_id": 7},
            occurred_at=later - timedelta(hours=1),
        )
        self._entry(
            event,
            snapshot={**base, "name": "Newest", "series_id": 9},
            occurred_at=later,
        )
        self._entry(
            event,
            snapshot={**base, "name": "Oldest"},
            occurred_at=later - timedelta(hours=2),
        )
        pk = self._delete(event)

        resolved = resolve_ledger_events(self.org.pk)[pk]

        self.assertEqual(resolved.name, "Newest")
        self.assertEqual(resolved.state, LEDGER_STATE_DELETED)
        self.assertEqual(resolved.series_id, 9)
        self.assertEqual(resolved.scheduled_at, T0)
        self.assertIsNone(resolved.ends_at)
        self.assertEqual(resolved.end, T0)
        self.assertEqual(resolved.organization_id, self.org.pk)

    def test_latest_snapshot_ties_break_on_pk(self) -> None:
        event = self.make_event(scheduled_at=T0)
        at = tz.now()
        self._entry(event, snapshot={"name": "First"}, occurred_at=at)
        self._entry(event, snapshot={"name": "Second"}, occurred_at=at)
        pk = self._delete(event)

        self.assertEqual(resolve_ledger_events(self.org.pk)[pk].name, "Second")

    def test_moved_event_uses_old_org_snapshot(self) -> None:
        other = Organization.objects.create(name="Other Org", owner=self.admin)
        event = self.make_event(scheduled_at=T0, name="Original")
        self._entry(event)
        Event.objects.filter(pk=event.pk).update(
            organization=other, name="Renamed", scheduled_at=T0 + timedelta(days=30)
        )

        resolved = resolve_ledger_events(self.org.pk)[event.pk]

        self.assertEqual(resolved.state, LEDGER_STATE_MOVED)
        self.assertEqual(resolved.name, "Original")
        self.assertEqual(resolved.scheduled_at, T0)
        self.assertEqual(resolved.organization_id, self.org.pk)
        self.assertNotIn(event.pk, resolve_ledger_events(other.pk))

    def test_window_filters_live_in_sql(self) -> None:
        repeater = self._repeater()
        early = self._event_at(T0)
        middle = self._event_at(T0 + timedelta(days=1), event_repeater=repeater)
        late = self._event_at(T0 + timedelta(days=2))

        window = RecordsWindow(
            since=T0 + timedelta(hours=12), until=T0 + timedelta(days=2)
        )
        self.assertEqual(
            set(resolve_ledger_events(self.org.pk, window=window)), {middle.pk}
        )
        self.assertEqual(
            set(
                resolve_ledger_events(
                    self.org.pk, window=RecordsWindow(until=T0 + timedelta(days=2))
                )
            ),
            {early.pk, middle.pk},
        )
        self.assertEqual(
            set(
                resolve_ledger_events(
                    self.org.pk, window=RecordsWindow(series_id=repeater.pk)
                )
            ),
            {middle.pk},
        )
        self.assertEqual(
            set(
                resolve_ledger_events(
                    self.org.pk, window=RecordsWindow(event_id=late.pk)
                )
            ),
            {late.pk},
        )

    def test_window_applies_to_deleted_in_python(self) -> None:
        inside = self.make_event(scheduled_at=T0 + timedelta(days=1))
        self._entry(inside, snapshot={**event_snapshot(inside), "series_id": 5})
        outside = self.make_event(scheduled_at=T0 + timedelta(days=10))
        self._entry(outside)
        unscheduled = self.make_event(scheduled_at=T0)
        self._entry(
            unscheduled,
            snapshot={**event_snapshot(unscheduled), "scheduled_at": None},
        )
        inside_pk = self._delete(inside)
        outside_pk = self._delete(outside)
        unscheduled_pk = self._delete(unscheduled)

        window = RecordsWindow(since=T0, until=T0 + timedelta(days=2))
        self.assertEqual(
            set(resolve_ledger_events(self.org.pk, window=window)), {inside_pk}
        )
        self.assertEqual(
            set(resolve_ledger_events(self.org.pk, window=RecordsWindow(since=T0))),
            {inside_pk, outside_pk},
        )
        self.assertEqual(
            set(
                resolve_ledger_events(
                    self.org.pk, window=RecordsWindow(until=T0 + timedelta(days=20))
                )
            ),
            {inside_pk, outside_pk},
        )
        self.assertEqual(
            set(resolve_ledger_events(self.org.pk, window=RecordsWindow(series_id=5))),
            {inside_pk},
        )
        self.assertEqual(
            set(resolve_ledger_events(self.org.pk)),
            {inside_pk, outside_pk, unscheduled_pk},
        )
        self.assertEqual(
            set(
                resolve_ledger_events(
                    self.org.pk, window=RecordsWindow(event_id=outside_pk)
                )
            ),
            {outside_pk},
        )

    def test_event_ids_intersection(self) -> None:
        a = self._event_at(T0)
        b = self._event_at(T0)
        missing = 10_000_000

        self.assertEqual(
            set(resolve_ledger_events(self.org.pk, event_ids=[a.pk, missing])), {a.pk}
        )
        self.assertEqual(resolve_ledger_events(self.org.pk, event_ids=[]), {})
        self.assertEqual(
            set(
                resolve_ledger_events(
                    self.org.pk,
                    event_ids=[a.pk, b.pk],
                    window=RecordsWindow(event_id=b.pk),
                )
            ),
            {b.pk},
        )

    def test_snapshot_time_parsing(self) -> None:
        expected = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        self.assertEqual(parse_snapshot_time("2026-01-01T10:00:00+00:00"), expected)
        self.assertEqual(parse_snapshot_time("2026-01-01T10:00:00Z"), expected)
        self.assertEqual(parse_snapshot_time("2026-01-01T05:00:00-05:00"), expected)
        self.assertEqual(parse_snapshot_time("2026-01-01T05:00:00-05:00").tzinfo, UTC)
        self.assertIsNone(parse_snapshot_time(None))
        self.assertIsNone(parse_snapshot_time(""))

        for bad in ("2026-01-01T10:00:00", "garbage", 12345):
            with self.subTest(value=bad), capture_logs() as logs:
                self.assertIsNone(parse_snapshot_time(bad, event_id=4, field="ends_at"))
            unparsed = [
                e for e in logs if e["event"] == "signup_ledger_snapshot_unparsed"
            ]
            self.assertEqual(len(unparsed), 1)
            self.assertEqual(unparsed[0]["log_level"], "debug")
            self.assertEqual(unparsed[0]["system"], "events")
            self.assertEqual(unparsed[0]["subsystem"], "ledger")
            self.assertEqual(unparsed[0]["event_id"], 4)

    def test_deleted_event_with_bad_snapshot_times(self) -> None:
        event = self.make_event(scheduled_at=T0)
        self._entry(
            event,
            snapshot={
                "name": "Odd",
                "scheduled_at": "garbage",
                "ends_at": "2026-01-01T10:00:00",
            },
        )
        pk = self._delete(event)

        with capture_logs() as logs:
            resolved = resolve_ledger_events(self.org.pk)[pk]

        self.assertIsNone(resolved.scheduled_at)
        self.assertIsNone(resolved.ends_at)
        self.assertIsNone(resolved.end)
        self.assertEqual(
            len([e for e in logs if e["event"] == "signup_ledger_snapshot_unparsed"]),
            2,
        )

    def test_other_org_rows_ignored(self) -> None:
        other = Organization.objects.create(name="Other Org", owner=self.admin)
        mine = self._event_at(T0)
        theirs = self.make_event(organization=other, scheduled_at=T0)
        self._entry(theirs, organization=other)
        gone = self.make_event(organization=other, scheduled_at=T0)
        self._entry(gone, organization=other)
        self._delete(gone)

        self.assertEqual(set(resolve_ledger_events(self.org.pk)), {mine.pk})
        self.assertEqual(
            resolve_ledger_events(self.org.pk, event_ids=[theirs.pk, gone.pk]), {}
        )

    def test_org_without_rows(self) -> None:
        other = Organization.objects.create(name="Empty Org", owner=self.admin)
        with self.assertNumQueries(1):
            self.assertEqual(resolve_ledger_events(other.pk), {})

    def test_query_count_bounded(self) -> None:
        inside: set[int] = set()
        for i in range(40):
            when = T0 + timedelta(days=i)
            event = self._event_at(when)
            if i < 5:
                inside.add(event.pk)
        deleted: set[int] = set()
        for _ in range(5):
            event = self.make_event(scheduled_at=T0 + timedelta(days=1))
            self._entry(event)
            deleted.add(self._delete(event))

        window = RecordsWindow(since=T0, until=T0 + timedelta(days=5))
        with self.assertNumQueries(4):
            result = resolve_ledger_events(self.org.pk, window=window)

        self.assertEqual(set(result), inside | deleted)

    def test_chunking(self) -> None:
        deleted: set[int] = set()
        for i in range(5):
            event = self.make_event(scheduled_at=T0 + timedelta(days=i))
            self._entry(event)
            deleted.add(self._delete(event))
        live = {self._event_at(T0).pk, self._event_at(T0).pk, self._event_at(T0).pk}

        with patch("events.ledger.RESOLVE_CHUNK_SIZE", 2):
            result = resolve_ledger_events(self.org.pk)

        self.assertEqual(set(result), deleted | live)
        self.assertTrue(all(result[pk].state == LEDGER_STATE_DELETED for pk in deleted))
