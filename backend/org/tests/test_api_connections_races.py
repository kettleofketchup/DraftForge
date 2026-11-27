import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest import skipUnless

from django.db import connection, connections, transaction
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from app.models import CustomUser
from common.game import GameType
from org.api_connections.lifecycle import ConnectionConflict, issue_connection_key
from org.api_connections.mutations import MmrMutationContext, MmrRevisionConflict
from org.api_tokens.sync import SyncResult, sync_mmrs
from org.features import FeatureKey, set_org_feature
from org.mmr import mark_org_mmr_verified, merge_org_mmrs, set_org_mmr
from org.models import (
    Organization,
    OrgApiConnection,
    OrgApiToken,
    OrgMmrRevisionCounter,
    OrgMmrSyncState,
    OrgUser,
    OrgUserGameMmr,
)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class ConnectionKeyRaceTests(TransactionTestCase):
    def test_concurrent_issue_rotate_single_usable_credential(self) -> None:
        owner = CustomUser.objects.create_user(username="race-admin")
        org = Organization.objects.create(name="Race Org", owner=owner)
        set_org_feature(org, FeatureKey.MMR_SYNC, enabled=True, actor=None)
        for rotate in (False, True):
            with self.subTest(rotate=rotate):
                connection_row = OrgApiConnection.objects.create(
                    organization=org,
                    name="Race",
                    operations=["mmr:read"],
                    enabled=True,
                    inbound_enabled=True,
                )
                barrier = threading.Barrier(2, timeout=10)

                def worker(rotate_key: bool) -> tuple[int | None, str]:
                    try:
                        snapshot = OrgApiConnection.objects.get(pk=connection_row.pk)
                        actor = CustomUser.objects.get(pk=owner.pk)
                        barrier.wait()
                        try:
                            token, raw = issue_connection_key(
                                snapshot, actor=actor, rotate=rotate_key
                            )
                            return token.pk, raw
                        except ConnectionConflict as exc:
                            self.assertEqual(exc.status_code, 409)
                            self.assertEqual(
                                str(exc.detail["code"]), "configuration_changed"
                            )
                            return None, "configuration_changed"
                    finally:
                        connections.close_all()

                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(worker, False), pool.submit(worker, rotate)]
                    results = [future.result(timeout=30) for future in futures]
                winners = [(pk, raw) for pk, raw in results if pk is not None]
                self.assertEqual(len(winners), 1, results)
                self.assertEqual(sum(pk is None for pk, _ in results), 1)
                self.assertEqual(
                    OrgApiToken.objects.filter(
                        connection=connection_row,
                        revoked_at__isnull=True,
                        legacy_credential=False,
                    ).count(),
                    1,
                )
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"Bearer {winners[0][1]}")
                self.assertEqual(
                    client.get(f"/api/organizations/{org.pk}/mmr-sync/").status_code,
                    200,
                )


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class MmrMutationRaceTests(TransactionTestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="mmr-race-admin")
        self.user = CustomUser.objects.create_user(username="mmr-race-player")
        self.org = Organization.objects.create(name="MMR Race", owner=self.owner)
        self.member = OrgUser.objects.create(organization=self.org, user=self.user)
        self.game = GameType.DOTA2

    def test_first_row_writes_share_membership_lock(self) -> None:
        barrier = threading.Barrier(2, timeout=10)

        def write(value: int) -> None:
            try:
                member = OrgUser.objects.get(pk=self.member.pk)
                barrier.wait()
                set_org_mmr(member, self.game, value, mark_verified=False)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(write, value) for value in (4000, 5000)]
            for future in futures:
                future.result(timeout=30)
        state = OrgMmrSyncState.objects.get(org_user=self.member, game_type=self.game)
        self.assertEqual(state.revision, 2)
        self.assertEqual(
            OrgUserGameMmr.objects.get(org_user=self.member, game_type=self.game).mmr,
            state.value,
        )
        self.assertEqual(
            OrgMmrRevisionCounter.objects.get(
                organization=self.org, game_type=self.game
            ).revision,
            2,
        )

    def test_verify_during_import_advances_revision(self) -> None:
        set_org_mmr(self.member, self.game, 4000, mark_verified=False)
        expected = OrgMmrSyncState.objects.get(
            org_user=self.member, game_type=self.game
        ).revision
        ready = threading.Event()

        def import_value() -> str:
            try:
                member = OrgUser.objects.get(pk=self.member.pk)
                ready.set()
                try:
                    set_org_mmr(
                        member,
                        self.game,
                        5000,
                        mark_verified=False,
                        sync_context=MmrMutationContext(expected_revision=expected),
                    )
                except MmrRevisionConflict:
                    return "conflict"
                return "applied"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                OrgUser.objects.select_for_update().get(pk=self.member.pk)
                future = pool.submit(import_value)
                self.assertTrue(ready.wait(timeout=10))
                mark_org_mmr_verified(self.member, self.game, self.owner)
            self.assertEqual(future.result(timeout=30), "conflict")
        state = OrgMmrSyncState.objects.get(org_user=self.member, game_type=self.game)
        self.assertGreater(state.revision, expected)
        self.assertEqual(state.value, 4000)
        self.assertIsNotNone(state.verified_at)

    def test_inbound_identity_matching_rereads_after_membership_lock(self) -> None:
        self.user.steam_account_id = 12345
        self.user.save(update_fields=["steam_account_id"])
        attempted = threading.Event()

        def import_value() -> SyncResult:
            def observe(
                execute: Callable[..., Any],
                sql: str,
                params: Any,
                many: bool,
                context: dict[str, Any],
            ) -> Any:
                if '"org_orguser"' in sql and "FOR UPDATE" in sql:
                    attempted.set()
                return execute(sql, params, many, context)

            try:
                with connections["default"].execute_wrapper(observe):
                    return sync_mmrs(
                        self.org,
                        self.owner,
                        [{"steam_id": 12345, "mmr": 5000}],
                        mark_verified=False,
                    )
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                OrgUser.objects.select_for_update().get(pk=self.member.pk)
                future = pool.submit(import_value)
                self.assertTrue(attempted.wait(timeout=10))
                self.user.steam_account_id = 22222
                self.user.save(update_fields=["steam_account_id"])
            result = future.result(timeout=30)
        self.assertEqual(result.updated, 0)
        self.assertEqual(len(result.unmatched), 1)
        self.assertFalse(OrgUserGameMmr.objects.filter(org_user=self.member).exists())

    def test_membership_delete_locks_before_collecting_concurrent_mmr(self) -> None:
        self._delete_while_writing(account=False)

    def test_account_delete_locks_before_collecting_concurrent_mmr(self) -> None:
        self._delete_while_writing(account=True)

    def test_org_delete_locks_before_collecting_concurrent_mmr(self) -> None:
        self._delete_while_writing(account=False, organization=True)

    def _delete_while_writing(
        self, *, account: bool, organization: bool = False
    ) -> None:
        attempted = threading.Event()

        def remove() -> None:
            def observe(
                execute: Callable[..., Any],
                sql: str,
                params: Any,
                many: bool,
                context: dict[str, Any],
            ) -> Any:
                if sql.startswith('DELETE FROM "org_orguser" ') or (
                    '"org_orguser"' in sql and "FOR UPDATE" in sql
                ):
                    attempted.set()
                return execute(sql, params, many, context)

            try:
                with connections["default"].execute_wrapper(observe):
                    if organization:
                        self.org.delete()
                    elif account:
                        client = APIClient()
                        actor = CustomUser.objects.create_superuser(
                            username="delete-race-admin", password="testpass"
                        )
                        client.force_authenticate(actor)
                        response = client.delete(f"/api/users/{self.user.pk}/")
                        self.assertEqual(response.status_code, 204)
                    else:
                        OrgUser.objects.filter(pk=self.member.pk).delete()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                OrgUser.objects.select_for_update().get(pk=self.member.pk)
                future = pool.submit(remove)
                self.assertTrue(attempted.wait(timeout=10))
                set_org_mmr(self.member, self.game, 5000, mark_verified=False)
            future.result(timeout=30)
        self.assertFalse(OrgUser.objects.filter(pk=self.member.pk).exists())
        self.assertFalse(
            OrgMmrSyncState.objects.filter(org_user_id=self.member.pk).exists()
        )

    def test_rejoin_and_merge_never_reuse_revision(self) -> None:
        set_org_mmr(self.member, self.game, 4000, mark_verified=False)
        before = OrgMmrSyncState.objects.get(
            org_user=self.member, game_type=self.game
        ).revision
        stale = OrgUser.objects.get(pk=self.member.pk)
        self.member.delete()
        self.member = OrgUser.objects.create(organization=self.org, user=self.user)
        set_org_mmr(self.member, self.game, 4500, mark_verified=False)
        keeper_user = CustomUser.objects.create_user(username="mmr-race-keeper")
        keeper = OrgUser.objects.create(organization=self.org, user=keeper_user)
        barrier = threading.Barrier(2, timeout=10)

        def merge() -> None:
            try:
                barrier.wait()
                merge_org_mmrs(self.member, keeper)
            finally:
                connections.close_all()

        def stale_write() -> None:
            try:
                barrier.wait()
                with self.assertRaises(OrgUser.DoesNotExist):
                    set_org_mmr(stale, self.game, 6000, mark_verified=False)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(merge), pool.submit(stale_write)]
            for future in futures:
                future.result(timeout=30)
        state = OrgMmrSyncState.objects.get(org_user=keeper, game_type=self.game)
        self.assertGreater(state.revision, before)
        self.assertEqual(state.value, 4500)
