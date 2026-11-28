import itertools
import uuid
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from structlog.testing import capture_logs

from events.constants import ActorRole, SignupAction, SignupMeans
from events.models import Event, LedgerPurgeOutcome, SignupLedgerEntry
from events.tests.base import EventTestCase


class LedgerPurgeTest(EventTestCase):
    def setUp(self) -> None:
        self.a = self.make_event()
        self.b = self.make_event()
        self.c = self.make_event()
        self.sizes = {self.a.pk: 3, self.b.pk: 1, self.c.pk: 5}
        for event in (self.a, self.b, self.c):
            for _ in range(self.sizes[event.pk]):
                self._entry(event)

    def _entry(self, event: Event) -> SignupLedgerEntry:
        return SignupLedgerEntry.objects.create(
            event=event,
            organization=self.org,
            event_snapshot={"id": event.pk},
            subject_user=self.user,
            subject_snapshot={"user_id": self.user.pk},
            actor_role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            action=SignupAction.SIGNED_UP,
            correlation_id=uuid.uuid4().hex,
        )

    def _counts(self) -> Counter[int]:
        return Counter(SignupLedgerEntry.objects.values_list("event_id", flat=True))

    def _assert_events_whole(self) -> None:
        for event_id, n in self._counts().items():
            self.assertEqual(n, self.sizes[event_id], event_id)

    def _qs(self) -> Any:
        return SignupLedgerEntry.objects.filter(organization_id=self.org.pk)

    def _purged_logs(self, logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [e for e in logs if e["event"] == "signup_records_purged"]

    def test_purge_groups_whole_events_into_batches(self) -> None:
        outcome = self._qs().purge(batch_size=4)
        self.assertEqual(
            outcome, LedgerPurgeOutcome(count=9, events=3, batches=2, complete=True)
        )
        self.assertFalse(SignupLedgerEntry.objects.exists())

    def test_event_never_split(self) -> None:
        real_atomic = transaction.atomic
        snapshots: list[Counter[int]] = []

        @contextmanager
        def spy(*args: Any, **kwargs: Any) -> Iterator[None]:
            with real_atomic(*args, **kwargs):
                yield
            if kwargs.get("savepoint", True) and not args:
                snapshots.append(self._counts())

        with patch("events.models.transaction.atomic", side_effect=spy):
            self._qs().purge(batch_size=4)

        self.assertEqual(len(snapshots), 2)
        before: Counter[int] = Counter(self.sizes)
        deleted_sets: list[set[int]] = []
        for snap in snapshots:
            for event_id, n in snap.items():
                self.assertEqual(n, self.sizes[event_id])
            deleted_sets.append(set(before) - set(snap))
            before = snap
        self.assertEqual(deleted_sets, [{self.a.pk, self.b.pk}, {self.c.pk}])

    def test_deadline_stops_between_batches(self) -> None:
        clock = itertools.chain([0.0], itertools.repeat(100.0))
        with patch("events.models.time.monotonic", side_effect=clock):
            outcome = self._qs().purge(batch_size=3, deadline=50.0)
        self.assertEqual(
            outcome, LedgerPurgeOutcome(count=3, events=1, batches=1, complete=False)
        )
        self._assert_events_whole()
        self.assertEqual(set(self._counts()), {self.b.pk, self.c.pk})

        rest = self._qs().purge()
        self.assertTrue(rest.complete)
        self.assertEqual(rest.count, 6)
        self.assertFalse(self._qs().exists())

    def test_deadline_already_passed(self) -> None:
        with patch("events.models.time.monotonic", return_value=100.0):
            outcome = self._qs().purge(deadline=50.0)
        self.assertEqual(
            outcome, LedgerPurgeOutcome(count=0, events=0, batches=0, complete=False)
        )
        self.assertEqual(SignupLedgerEntry.objects.count(), 9)

    def test_min_batches_run_past_deadline(self) -> None:
        with patch("events.models.time.monotonic", return_value=100.0):
            outcome = self._qs().purge(batch_size=3, deadline=50.0, min_batches=1)
        self.assertEqual(
            outcome, LedgerPurgeOutcome(count=3, events=1, batches=1, complete=False)
        )
        self._assert_events_whole()

    def test_empty_queryset(self) -> None:
        with capture_logs() as logs:
            outcome = SignupLedgerEntry.objects.filter(pk=-1).purge()
        self.assertEqual(
            outcome, LedgerPurgeOutcome(count=0, events=0, batches=0, complete=True)
        )
        self.assertEqual(len(self._purged_logs(logs)), 1, logs)
        self.assertEqual(SignupLedgerEntry.objects.count(), 9)

    def test_logs_once_per_call(self) -> None:
        with capture_logs() as logs:
            self._qs().purge(
                organization_id=self.org.pk,
                batch_size=4,
                extra_log={"retention_days": 365},
            )
        purged = self._purged_logs(logs)
        self.assertEqual(len(purged), 1, logs)
        line = purged[0]
        self.assertEqual(line["system"], "events")
        self.assertEqual(line["subsystem"], "ledger")
        self.assertEqual(line["log_level"], "info")
        self.assertEqual(line["organization_id"], self.org.pk)
        self.assertEqual(line["count"], 9)
        self.assertEqual(line["events"], 3)
        self.assertEqual(line["batches"], 2)
        self.assertIs(line["complete"], True)
        self.assertEqual(line["retention_days"], 365)

    def test_only_purges_queryset_rows(self) -> None:
        self._qs().filter(event_id=self.b.pk).purge()
        self.assertEqual(self._counts(), Counter({self.a.pk: 3, self.c.pk: 5}))

    def test_large_in_list_chunked(self) -> None:
        extra = [self.make_event() for _ in range(2)]
        for event in extra:
            self.sizes[event.pk] = 1
            self._entry(event)
        with (
            patch("events.models.PURGE_CHUNK_SIZE", 2),
            CaptureQueriesContext(connection) as ctx,
        ):
            outcome = self._qs().purge()
        self.assertEqual(outcome.count, 11)
        self.assertEqual(outcome.events, 5)
        self.assertEqual(outcome.batches, 1)
        self.assertFalse(SignupLedgerEntry.objects.exists())
        deletes = [
            q["sql"] for q in ctx.captured_queries if q["sql"].startswith("DELETE")
        ]
        self.assertEqual(len(deletes), 3, deletes)
