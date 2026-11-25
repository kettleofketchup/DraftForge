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
throwaway PostgreSQL container (``backend.settings_pgtest``). Nothing here
is skipped on either engine.
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
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from app.models import CustomUser
from config.promotion_sync import PromotionSyncConfig
from events.constants import EventState
from events.models import Event
from league.models import League
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.integration import contacts, event_lock
from org.integration.contacts import import_contact_receipts
from org.integration.event_lock import with_event_mutation
from org.integration.receipts import format_timestamp
from org.models import ContributionEntry, Organization, OrgUser, PromoSend
from org.models_promotion_sync import ExternalPromotionReceipt
from org.promotion import services
from org.promotion.services import ContactAlreadyRecorded, record_promo_send
from tournament.models import Tournament

GUILD = "770000000000000002"
WAIT = 10.0
BLOCKED_PROBE = 0.5


def _binding(org: Organization, event: Event) -> PromotionSyncConfig:
    raw = json.dumps(
        [
            {
                "org_id": str(org.pk),
                "guild_id": GUILD,
                "events": [{"event_id": str(event.pk), "occasion_id": "501"}],
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
        settings = override_settings(
            PROMOTION_SYNC=_binding(self.org, self.event),
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

    def payload(self) -> dict[str, Any]:
        return {
            "source": "contact_log",
            "guild_id": GUILD,
            "scan_started_at": format_timestamp(timezone.now()),
            "range": {"after": "9000", "through": "9001"},
            "skipped_ids": [],
            "entries": [
                {
                    "source_contact_id": "9001",
                    "target_discord_id": self.recipient.discordId,
                    "promoter_discord_id": None,
                    "recorded_at": "2026-11-01T10:00:00Z",
                    "contact_date_ny": "2026-11-01",
                    "contact_method": "DISCORD_DM",
                    "contact_reason": "EVENT_INVITE",
                    "occasion_id": "501",
                    "event_date": None,
                    "forced": False,
                }
            ],
        }

    def send(self) -> PromoSend:
        return record_promo_send(
            sender=self.promoter,
            event=Event.objects.nocache().get(pk=self.event.pk),
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

    def test_send_after_import_is_rejected(self) -> None:
        import_contact_receipts(self.org, self.payload())
        with self.assertRaises(ContactAlreadyRecorded):
            self.send()
        self.assertFalse(PromoSend.objects.exists())


class SendFirstRaceTests(_RaceBase):
    def test_send_first_keeps_both_histories_and_voids_the_local_point(self) -> None:
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
