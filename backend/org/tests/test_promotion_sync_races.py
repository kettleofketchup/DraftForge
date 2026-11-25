"""Import-versus-send races on a real, committing database.

Both an external contact import and a local record-send run their whole event
mutation under the event's lock (``with_event_mutations`` /
``with_event_mutation``): a PostgreSQL row lock on the event, or SQLite's
early write lock. So once an import that suppresses a recipient has
committed, no ordinary send to that recipient can commit; and a send that
committed first stays, next to the imported history, with its point voided
because the external contact holds it.

The module runs on whichever engine the test settings select. The default
suite is SQLite; ``just test::backend::pg-race`` runs it again against a
throwaway PostgreSQL container (``backend.settings_pgtest``). Only the
rescore races are PostgreSQL-only: on SQLite every write transaction is
already serialized, so there is nothing to race.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.db import OperationalError, connection, connections
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone

from app.models import CustomUser
from config.promotion_sync import PromotionSyncConfig
from events.constants import EventState
from events.models import Event
from league.models import League
from org.contributions import services as contribution_services
from org.contributions.kinds import ContributionKind
from org.contributions.services import set_point_value
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.integration import contacts, event_lock
from org.integration.contacts import import_contact_receipts
from org.integration.event_lock import with_event_mutation
from org.integration.receipts import format_timestamp
from org.models import ContributionEntry, Organization, OrgUser, PromoSend
from org.models_promotion_sync import ExternalPromotionReceipt
from org.promotion import services
from org.promotion.services import (
    ContactAlreadyRecorded,
    record_promo_send,
    undo_promo_send,
)
from tournament.models import Tournament

GUILD = "770000000000000002"
WAIT = 10.0
BLOCKED_PROBE = 0.5


def _binding(org: Organization, *events: Event) -> PromotionSyncConfig:
    raw = json.dumps(
        [
            {
                "org_id": str(org.pk),
                "guild_id": GUILD,
                "events": [
                    {"event_id": str(event.pk), "occasion_id": str(501 + i)}
                    for i, event in enumerate(events)
                ],
            }
        ]
    )
    return PromotionSyncConfig.from_env(environ={"PROMOTION_SYNC_BINDINGS": raw})


class _Worker(threading.Thread):
    """Runs ``target`` on its own DB connection and keeps its result or error."""

    def __init__(self, target: Callable[[], Any]) -> None:
        super().__init__(daemon=True)
        self._target_fn = target
        self.result: Any = None
        self.error: BaseException | None = None
        self.finished = threading.Event()

    def run(self) -> None:
        try:
            self.result = self._target_fn()
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            self.error = exc
        finally:
            connections.close_all()
            self.finished.set()


class EngineTests(TransactionTestCase):
    def test_pg_recipe_really_uses_postgresql(self) -> None:
        expected = "postgresql" if os.environ.get("DF_PGTEST_DSN") else "sqlite"
        self.assertEqual(connection.vendor, expected)


class _RaceBase(TransactionTestCase):
    def setUp(self) -> None:
        now = timezone.now()
        self.owner = CustomUser.objects.create_user(username="race_owner")
        self.org = Organization.objects.create(
            name="Race Org", owner=self.owner, discord_server_id=GUILD
        )
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=None)
        self.promoter = self._user("race_promoter")
        self.org.promoters.add(self.promoter)
        OrgUser.objects.create(user=self.promoter, organization=self.org)
        self.recipient = self._user("race_recipient")
        league = League.objects.create(
            name="Race League", organization=self.org, steam_league_id=88501
        )
        Tournament.objects.create(
            name="Race Past", date_played=now - timedelta(days=3), league=league
        ).users.add(self.recipient)
        self.event = Event.objects.create(
            organization=self.org,
            name="Race Night",
            scheduled_at=now + timedelta(days=3),
            created_by=self.owner,
            state=EventState.UPCOMING,
        )
        self.second_event = Event.objects.create(
            organization=self.org,
            name="Race Night 2",
            scheduled_at=now + timedelta(days=4),
            created_by=self.owner,
            state=EventState.UPCOMING,
        )
        settings = override_settings(
            PROMOTION_SYNC=_binding(self.org, self.event, self.second_event),
            DISCORD_BOT_TOKEN="test-bot-token",
        )
        settings.enable()
        self.addCleanup(settings.disable)
        fetch = patch(
            "org.promotion.recipients.get_discord_members_data", return_value=[]
        )
        fetch.start()
        self.addCleanup(fetch.stop)

    def _user(self, username: str) -> CustomUser:
        user = CustomUser.objects.create_user(username=username)
        user.discordId = str(885000000000000000 + user.pk)
        user.save()
        return user

    def entry(
        self,
        source_id: int = 9001,
        *,
        occasion: int = 501,
        promoter: str | None = None,
    ) -> dict[str, Any]:
        return {
            "source_contact_id": str(source_id),
            "target_discord_id": self.recipient.discordId,
            "promoter_discord_id": promoter,
            "recorded_at": "2026-11-01T10:00:00Z",
            "contact_date_ny": "2026-11-01",
            "contact_method": "DISCORD_DM",
            "contact_reason": "EVENT_INVITE",
            "occasion_id": str(occasion),
            "event_date": None,
            "forced": False,
        }

    def payload(self, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        entries = entries if entries is not None else [self.entry()]
        ids = [int(e["source_contact_id"]) for e in entries]
        return {
            "source": "contact_log",
            "guild_id": GUILD,
            "scan_started_at": format_timestamp(timezone.now()),
            "range": {"after": str(min(ids) - 1), "through": str(max(ids))},
            "skipped_ids": [],
            "entries": entries,
        }

    def send(self, event: Event | None = None) -> PromoSend:
        return record_promo_send(
            sender=self.promoter,
            event=Event.objects.nocache().get(pk=(event or self.event).pk),
            recipient=CustomUser.objects.nocache().get(pk=self.recipient.pk),
            template=None,
            text="Hi",
        )

    def paused(self, original: Callable[..., Any]) -> tuple[Callable, Any, Any]:
        """``original`` wrapped to report it ran, then wait for release."""
        inside = threading.Event()
        release = threading.Event()

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            inside.set()
            if not release.wait(WAIT):
                raise AssertionError("test never released the paused mutation")
            return result

        return wrapper, inside, release


class ImportFirstRaceTests(_RaceBase):
    def test_no_send_commits_after_a_committed_import(self) -> None:
        payload = self.payload()
        wrapper, inside, release = self.paused(contacts._apply_batch)
        with patch.object(contacts, "_apply_batch", wrapper):
            importer = _Worker(lambda: import_contact_receipts(self.org, payload))
            importer.start()
            self.assertTrue(inside.wait(WAIT), importer.error)
            sender = _Worker(self.send)
            sender.start()
            # The send must wait on the import's event lock.
            self.assertFalse(sender.finished.wait(BLOCKED_PROBE))
            release.set()
            importer.join(WAIT)
            sender.join(WAIT)
        self.assertIsNone(importer.error)
        self.assertEqual(importer.result["applied"], 1)
        self.assertIsInstance(sender.error, ContactAlreadyRecorded)
        self.assertFalse(PromoSend.objects.exists())
        self.assertFalse(ContributionEntry.objects.exists())

    def test_import_then_send_409(self) -> None:
        import_contact_receipts(self.org, self.payload())
        with self.assertRaises(ContactAlreadyRecorded):
            self.send()
        self.assertFalse(PromoSend.objects.exists())


class SendFirstRaceTests(_RaceBase):
    def test_send_then_import_voids(self) -> None:
        payload = self.payload()
        wrapper, inside, release = self.paused(services.enqueue_send)
        with patch.object(services, "enqueue_send", wrapper):
            sender = _Worker(self.send)
            sender.start()
            self.assertTrue(inside.wait(WAIT), sender.error)
            importer = _Worker(lambda: import_contact_receipts(self.org, payload))
            importer.start()
            self.assertFalse(importer.finished.wait(BLOCKED_PROBE))
            release.set()
            sender.join(WAIT)
            importer.join(WAIT)
        self.assertIsNone(sender.error)
        self.assertIsNone(importer.error)
        self.assertEqual(importer.result["applied"], 1)
        self.assertEqual(importer.result["voided_local"], 1)
        self.assertEqual(PromoSend.objects.count(), 1)
        self.assertEqual(ExternalPromotionReceipt.objects.count(), 1)
        # The send's entry and its void: the point is the external one.
        self.assertEqual(ContributionEntry.objects.count(), 2)
        self.assertEqual(
            sum(ContributionEntry.objects.values_list("points", flat=True)), 0
        )

    def test_concurrent_identical_imports_store_once(self) -> None:
        payload = self.payload()
        workers = [
            _Worker(lambda: import_contact_receipts(self.org, payload))
            for _ in range(3)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(WAIT)
        self.assertEqual([w.error for w in workers], [None, None, None])
        self.assertEqual(sorted(w.result["applied"] for w in workers), [0, 0, 1])
        self.assertEqual(ExternalPromotionReceipt.objects.count(), 1)


class UndoAndDuplicateRaceTests(_RaceBase):
    def test_undo_vs_import(self) -> None:
        send = self.send()
        payload = self.payload()
        wrapper, inside, release = self.paused(services.revoke_promo_entry)
        with patch.object(services, "revoke_promo_entry", wrapper):
            undo = _Worker(lambda: undo_promo_send(send, actor=None))
            undo.start()
            self.assertTrue(inside.wait(WAIT), undo.error)
            importer = _Worker(lambda: import_contact_receipts(self.org, payload))
            importer.start()
            # The import waits on the undo's event lock.
            self.assertFalse(importer.finished.wait(BLOCKED_PROBE))
            release.set()
            undo.join(WAIT)
            importer.join(WAIT)
        self.assertIsNone(undo.error)
        self.assertIsNone(importer.error)
        self.assertEqual(importer.result["voided_local"], 0)
        self.assertFalse(PromoSend.objects.exists())
        self.assertFalse(ContributionEntry.objects.exists())
        self.assertTrue(ExternalPromotionReceipt.objects.get().holds_point)

    def test_import_vs_undo_cascades_the_void(self) -> None:
        send = self.send()
        import_contact_receipts(self.org, self.payload())
        self.assertEqual(ContributionEntry.objects.count(), 2)
        undo_promo_send(send, actor=None)
        self.assertFalse(ContributionEntry.objects.exists())

    def test_concurrent_same_event_player_duplicate(self) -> None:
        payloads = [self.payload([self.entry(9001)]), self.payload([self.entry(9002)])]
        workers = [
            _Worker(lambda p=p: import_contact_receipts(self.org, p)) for p in payloads
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(WAIT)
        self.assertEqual([w.error for w in workers], [None, None])
        points = sorted(w.result["results"][0]["point"] for w in workers)
        self.assertEqual(points, ["duplicate", "uncredited"])
        self.assertEqual(
            ExternalPromotionReceipt.objects.filter(holds_point=True).count(), 1
        )

    def test_multi_event_lock_ordering_no_deadlock(self) -> None:
        forward = self.payload(
            [self.entry(9001, occasion=501), self.entry(9002, occasion=502)]
        )
        backward = self.payload(
            [self.entry(9003, occasion=502), self.entry(9004, occasion=501)]
        )
        workers = [
            _Worker(lambda: import_contact_receipts(self.org, forward)),
            _Worker(lambda: import_contact_receipts(self.org, backward)),
            _Worker(lambda: self.send(self.second_event)),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(WAIT)
        self.assertTrue(all(w.finished.is_set() for w in workers))
        self.assertEqual([w.error for w in workers[:2]], [None, None])
        if workers[2].error is not None:
            self.assertIsInstance(workers[2].error, ContactAlreadyRecorded)
        self.assertEqual(
            ExternalPromotionReceipt.objects.filter(holds_point=True).count(), 2
        )
        self.assertEqual(
            sum(ContributionEntry.objects.values_list("points", flat=True)), 0
        )

    def test_lock_set_change_409_retry(self) -> None:
        import_contact_receipts(self.org, self.payload())
        receipt = ExternalPromotionReceipt.objects.get()
        original = contacts.with_event_mutations

        def moved_first(*args: Any, **kwargs: Any) -> Any:
            # Another import moved the receipt after this one read it.
            with ExternalPromotionReceipt.source_update():
                ExternalPromotionReceipt.objects.filter(pk=receipt.pk).update(
                    event=self.second_event,
                    holds_point=False,
                    point_status="not_applicable",
                )
            return original(*args, **kwargs)

        payload = self.payload([self.entry(9001, promoter=self.promoter.discordId)])
        with patch.object(contacts, "with_event_mutations", moved_first):
            with self.assertRaises(contacts.IntegrationError) as raised:
                import_contact_receipts(self.org, payload)
        self.assertEqual(raised.exception.code, "import_conflict_retry")
        receipt.refresh_from_db()
        self.assertEqual(receipt.event_id, self.second_event.pk)
        result = import_contact_receipts(self.org, payload)
        self.assertEqual(result["results"][0]["status"], "updated")
        receipt.refresh_from_db()
        self.assertEqual(receipt.event_id, self.event.pk)
        self.assertTrue(receipt.holds_point)


class _PausedOrgLog:
    """Stands in for ``OrgLog`` in the contribution services and pauses
    after the rescore's first audit row, inside its transaction."""

    def __init__(self, real: Any, pause: Callable[[], None]) -> None:
        self._real = real
        self._pause = pause
        self.objects = self

    def create(self, **kwargs: Any) -> Any:
        row = self._real.objects.create(**kwargs)
        if kwargs.get("action") == "set_point_value":
            self._pause()
        return row


class RescoreRaceTests(_RaceBase):
    """Rescoring and an import both lock the organization row first. These
    only race on PostgreSQL: SQLite's IMMEDIATE transactions serialize the
    whole write transaction anyway."""

    def _paused_rescore(
        self, points: int, *, apply_to_past: bool
    ) -> tuple[_Worker, threading.Event, threading.Event]:
        inside = threading.Event()
        release = threading.Event()

        def pause() -> None:
            inside.set()
            if not release.wait(WAIT):
                raise AssertionError("test never released the paused rescore")

        def rescore() -> Any:
            return set_point_value(
                Organization.objects.nocache().get(pk=self.org.pk),
                ContributionKind.PROMO_MESSAGE.value,
                points,
                actor=None,
                apply_to_past=apply_to_past,
            )

        stub = _PausedOrgLog(contribution_services.OrgLog, pause)
        patcher = patch.object(contribution_services, "OrgLog", stub)
        patcher.start()
        self.addCleanup(patcher.stop)
        return _Worker(rescore), inside, release

    @skipUnlessDBFeature("has_select_for_update")
    def test_rescore_vs_void_nets_zero(self) -> None:
        send = self.send()
        rescorer, inside, release = self._paused_rescore(5, apply_to_past=True)
        rescorer.start()
        self.assertTrue(inside.wait(WAIT), rescorer.error)
        importer = _Worker(lambda: import_contact_receipts(self.org, self.payload()))
        importer.start()
        self.assertFalse(importer.finished.wait(BLOCKED_PROBE))
        release.set()
        rescorer.join(WAIT)
        importer.join(WAIT)
        self.assertIsNone(rescorer.error)
        self.assertIsNone(importer.error)
        entry = ContributionEntry.objects.get(promo_send=send)
        void = ContributionEntry.objects.get(reversal_of=entry)
        self.assertEqual((entry.points, void.points), (5, -5))

    @skipUnlessDBFeature("has_select_for_update")
    def test_rescore_vs_credit_sees_committed_value(self) -> None:
        rescorer, inside, release = self._paused_rescore(4, apply_to_past=False)
        rescorer.start()
        self.assertTrue(inside.wait(WAIT), rescorer.error)
        payload = self.payload([self.entry(promoter=self.promoter.discordId)])
        importer = _Worker(lambda: import_contact_receipts(self.org, payload))
        importer.start()
        # The import waits on the rescore's organization lock.
        self.assertFalse(importer.finished.wait(BLOCKED_PROBE))
        release.set()
        rescorer.join(WAIT)
        importer.join(WAIT)
        self.assertIsNone(rescorer.error)
        self.assertIsNone(importer.error)
        credit = ContributionEntry.objects.get(external_contact__isnull=False)
        self.assertEqual(credit.points, 4)


class NoNetworkInsideLockTests(_RaceBase):
    """The import does no network I/O: on SQLite (IMMEDIATE transactions) a
    fetch inside its transaction would hold the database-wide write lock."""

    def test_import_never_reads_the_guild(self) -> None:
        with patch("org.promotion.recipients.get_discord_members_data") as fetch:
            result = import_contact_receipts(self.org, self.payload())
        self.assertEqual(result["applied"], 1)
        fetch.assert_not_called()


class EventMutationRetryTests(_RaceBase):
    def _flaky(self, failures: int, message: str = "database is locked"):
        calls = {"n": 0}

        def operation() -> str:
            calls["n"] += 1
            if calls["n"] <= failures:
                raise OperationalError(message)
            return "done"

        return operation, calls

    def test_sqlite_lock_errors_retry_whole_operation_up_to_three_times(
        self,
    ) -> None:
        if connection.vendor != "sqlite":
            operation, calls = self._flaky(1)
            with self.assertRaises(OperationalError):
                with_event_mutation(self.event.pk, operation)
            self.assertEqual(calls["n"], 1)
            return
        with patch.object(event_lock, "_backoff", lambda attempt: None):
            operation, calls = self._flaky(2)
            self.assertEqual(with_event_mutation(self.event.pk, operation), "done")
            self.assertEqual(calls["n"], 3)
            operation, calls = self._flaky(3)
            with self.assertRaises(OperationalError):
                with_event_mutation(self.event.pk, operation)
            self.assertEqual(calls["n"], 3)

    def test_other_errors_are_not_retried(self) -> None:
        with patch.object(event_lock, "_backoff", lambda attempt: None):
            operation, calls = self._flaky(1, "no such table: x")
            with self.assertRaises(OperationalError):
                with_event_mutation(self.event.pk, operation)
            self.assertEqual(calls["n"], 1)

    def test_rolled_back_attempt_leaves_no_writes(self) -> None:
        calls = {"n": 0}

        def operation() -> int:
            calls["n"] += 1
            PromoSend.objects.create(
                organization=self.org,
                event=self.event,
                recipient=self.recipient,
                sender=self.promoter,
                text=f"attempt {calls['n']}",
            )
            if calls["n"] == 1 and connection.vendor == "sqlite":
                raise OperationalError("database is locked")
            return PromoSend.objects.count()

        with patch.object(event_lock, "_backoff", lambda attempt: None):
            self.assertEqual(with_event_mutation(self.event.pk, operation), 1)
